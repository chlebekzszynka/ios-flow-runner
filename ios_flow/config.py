"""Ładowanie i walidacja pliku konfiguracyjnego JSON.

Walidacja zbiera wszystkie problemy naraz i dla każdego brakującego pola
podpowiada, skąd wziąć wartość. Klucze zaczynające się od ``_`` są
komentarzami i są pomijane.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from ios_flow.extract import ListRule
from ios_flow.locators import KINDS_WITH_PLACEHOLDER, PLACEHOLDER, Locator, LocatorKind
from ios_flow.navigate import Step

DEFAULT_SERVER_URL = "http://127.0.0.1:4723"
READABLE_ATTRIBUTES = ("label", "value", "name")


class Mode(StrEnum):
    SIMULATOR = "symulator"
    DEVICE = "urzadzenie"


# Skąd wziąć wartość pola — dołączane do komunikatu o braku.
HINTS: dict[str, str] = {
    "tryb": 'wpisz "symulator" albo "urzadzenie"',
    "bundle_id": (
        "symulator: xcrun simctl listapps booted; telefon: ideviceinstaller list "
        "(np. com.apple.Preferences dla Ustawień)"
    ),
    "symulator.nazwa_urzadzenia": (
        'nazwa z listy xcrun simctl list devices available, np. "iPhone 17"'
    ),
    "symulator.wersja_ios": (
        'nagłówek sekcji w tej samej liście, np. "-- iOS 27.0 --" oznacza "27.0"'
    ),
    "urzadzenie.udid": "idevice_id -l (telefon podłączony kablem i odblokowany)",
    "urzadzenie.team_id": (
        "security find-identity -v -p codesigning — 10 znaków w nawiasie na końcu wiersza"
    ),
    "urzadzenie.signing_id": 'zwykle "Apple Development"',
    "urzadzenie.wda_bundle_id": (
        "Bundle Identifier ustawiony w Xcode dla celu WebDriverAgentRunner"
    ),
}

ALLOWED_KEYS: dict[str, tuple[str, ...]] = {
    "": (
        "nazwa",
        "tryb",
        "serwer_appium",
        "bundle_id",
        "symulator",
        "urzadzenie",
        "sesja",
        "kroki",
        "odczyt",
        "lista",
        "wynik",
    ),
    "symulator": ("nazwa_urzadzenia", "wersja_ios"),
    "urzadzenie": ("udid", "team_id", "signing_id", "wda_bundle_id"),
    "sesja": (
        "snapshot_max_depth",
        "new_command_timeout",
        "restart_aplikacji",
        "dodatkowe_capabilities",
    ),
    "lokator": ("typ", "wartosc", "element", "przedrostki_stanu", "z_dopiskiem"),
    "krok": ("opis", "lokator", "czekaj_s", "pauza_s", "opcjonalny"),
    "pole": ("lokator", "atrybut", "wzorzec", "czekaj_s"),
    "lista": (
        "element",
        "nazwa_elementu",
        "wzorzec",
        "tylko_pasujace",
        "przedrostki_stanu",
        "pomijaj_zawierajace",
        "max_przewiniec",
    ),
    "wynik": ("katalog", "zrzut_ekranu"),
}


class ConfigError(ValueError):
    """Konfiguracja jest niekompletna albo błędna. ``problems`` to lista opisów."""

    def __init__(self, source: str, problems: list[str]) -> None:
        self.source = source
        self.problems = problems
        lines = [f"Konfiguracja {source} ma błędy ({len(problems)}):"]
        lines += [f"  - {problem}" for problem in problems]
        super().__init__("\n".join(lines))


@dataclass(frozen=True)
class SimulatorSettings:
    device_name: str
    platform_version: str


@dataclass(frozen=True)
class DeviceSettings:
    udid: str
    team_id: str
    signing_id: str
    wda_bundle_id: str


@dataclass(frozen=True)
class SessionSettings:
    snapshot_max_depth: int = 50
    new_command_timeout: int = 300
    restart_app: bool = True
    extra_capabilities: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FieldSpec:
    """Pole do odczytania na ostatnim ekranie."""

    key: str
    locator: Locator
    attribute: str = "label"
    pattern: str | None = None
    wait_s: float = 10.0


@dataclass(frozen=True)
class ListSpec:
    rule: ListRule
    max_scrolls: int = 20


@dataclass(frozen=True)
class OutputSettings:
    directory: str = "artifacts"
    screenshot: bool = True


@dataclass(frozen=True)
class Config:
    source: str
    name: str
    mode: Mode
    server_url: str
    bundle_id: str
    simulator: SimulatorSettings | None
    device: DeviceSettings | None
    session: SessionSettings
    steps: list[Step]
    fields: list[FieldSpec]
    list_spec: ListSpec | None
    output: OutputSettings

    @property
    def has_variable_step(self) -> bool:
        return any(step.is_variable for step in self.steps)


class _Reader:
    """Pomocnik walidacji: czyta pola i zbiera problemy zamiast rzucać od razu."""

    def __init__(self) -> None:
        self.problems: list[str] = []

    def problem(self, path: str, message: str) -> None:
        self.problems.append(f"{path}: {message}")

    def missing(self, path: str) -> None:
        hint = HINTS.get(path)
        suffix = f" Skąd wziąć: {hint}" if hint else ""
        self.problem(path, f"brak wartości.{suffix}")

    def check_keys(self, data: dict[str, Any], kind: str, path: str) -> None:
        allowed = ALLOWED_KEYS[kind]
        for key in data:
            if key.startswith("_") or key in allowed:
                continue
            where = f"{path}.{key}" if path else key
            self.problem(where, f"nieznane pole. Dozwolone: {', '.join(allowed)}")

    def section(self, data: dict[str, Any], key: str, path: str = "") -> dict[str, Any] | None:
        where = f"{path}.{key}" if path else key
        value = data.get(key)
        if value is None:
            return None
        if not isinstance(value, dict):
            self.problem(where, "oczekiwany obiekt {...}")
            return None
        return value

    def text(self, data: dict[str, Any], key: str, path: str, required: bool = True) -> str:
        where = f"{path}.{key}" if path else key
        value = data.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            if required:
                self.missing(where)
            return ""
        if not isinstance(value, str):
            self.problem(where, "oczekiwany tekst w cudzysłowie")
            return ""
        return value.strip()

    def number(
        self, data: dict[str, Any], key: str, path: str, default: float, integer: bool = False
    ) -> Any:
        where = f"{path}.{key}" if path else key
        value = data.get(key, default)
        valid = isinstance(value, int) if integer else isinstance(value, int | float)
        if isinstance(value, bool) or not valid or value <= 0:
            kind = "liczba całkowita" if integer else "liczba"
            self.problem(where, f"oczekiwana {kind} większa od zera, jest: {value!r}")
            return default
        return value

    def flag(self, data: dict[str, Any], key: str, path: str, default: bool) -> bool:
        value = data.get(key, default)
        if not isinstance(value, bool):
            self.problem(f"{path}.{key}", f"oczekiwane true albo false, jest: {value!r}")
            return default
        return value

    def texts(self, data: dict[str, Any], key: str, path: str) -> tuple[str, ...]:
        value = data.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
            self.problem(f"{path}.{key}", 'oczekiwana lista niepustych tekstów ["..."]')
            return ()
        return tuple(value)

    def pattern(self, data: dict[str, Any], key: str, path: str) -> str | None:
        value = data.get(key)
        if value is None:
            return None
        if not isinstance(value, str) or not value:
            self.problem(f"{path}.{key}", "oczekiwane wyrażenie regularne w cudzysłowie")
            return None
        try:
            re.compile(value)
        except re.error as error:
            self.problem(f"{path}.{key}", f"błędne wyrażenie regularne: {error}")
            return None
        return value

    def locator(self, data: Any, path: str) -> Locator | None:
        if not isinstance(data, dict):
            self.problem(path, 'brak lokatora. Przykład: {"typ": "id", "wartosc": "..."}')
            return None
        self.check_keys(data, "lokator", path)
        raw_kind = data.get("typ")
        kinds = ", ".join(kind.value for kind in LocatorKind)
        try:
            kind = LocatorKind(raw_kind)
        except ValueError:
            self.problem(f"{path}.typ", f"nieznany typ lokatora {raw_kind!r}. Dozwolone: {kinds}")
            return None
        value = self.text(data, "wartosc", path)
        if not value:
            return None
        if PLACEHOLDER in value and kind not in KINDS_WITH_PLACEHOLDER:
            allowed = ", ".join(k.value for k in KINDS_WITH_PLACEHOLDER)
            self.problem(path, f"{PLACEHOLDER} wolno użyć tylko w lokatorach typu: {allowed}")
        element_type = self.text(data, "element", path, required=False) or None
        prefixes = self.texts(data, "przedrostki_stanu", path)
        allow_suffix = self.flag(data, "z_dopiskiem", path, default=False)
        if (prefixes or allow_suffix) and kind is not LocatorKind.LABEL:
            self.problem(path, 'przedrostki_stanu i z_dopiskiem działają tylko z typem "etykieta"')
        return Locator(kind, value, element_type, prefixes, allow_suffix)


def _parse_steps(reader: _Reader, raw: Any) -> list[Step]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        reader.problem("kroki", "oczekiwana lista kroków [...]")
        return []
    steps: list[Step] = []
    for number, data in enumerate(raw, start=1):
        path = f"kroki[{number}]"
        if not isinstance(data, dict):
            reader.problem(path, "oczekiwany obiekt {...}")
            continue
        reader.check_keys(data, "krok", path)
        locator = reader.locator(data.get("lokator"), f"{path}.lokator")
        description = reader.text(data, "opis", path, required=False)
        wait_s = reader.number(data, "czekaj_s", path, default=10.0)
        pause_s = reader.number(data, "pauza_s", path, default=1.0)
        optional = reader.flag(data, "opcjonalny", path, default=False)
        if locator is not None:
            steps.append(Step(description or locator.value, locator, wait_s, pause_s, optional))
    if sum(step.is_variable for step in steps) > 1:
        reader.problem("kroki", f"{PLACEHOLDER} może wystąpić najwyżej w jednym kroku")
    return steps


def _parse_fields(reader: _Reader, raw: Any) -> list[FieldSpec]:
    if raw is None:
        return []
    if not isinstance(raw, dict):
        reader.problem("odczyt", 'oczekiwany obiekt {"nazwa_pola": {...}}')
        return []
    fields: list[FieldSpec] = []
    for key, data in raw.items():
        if key.startswith("_"):
            continue
        path = f"odczyt.{key}"
        if not isinstance(data, dict):
            reader.problem(path, "oczekiwany obiekt {...}")
            continue
        reader.check_keys(data, "pole", path)
        locator = reader.locator(data.get("lokator"), f"{path}.lokator")
        attribute = data.get("atrybut", "label")
        if attribute not in READABLE_ATTRIBUTES:
            reader.problem(
                f"{path}.atrybut",
                f"nieznany atrybut {attribute!r}. Dozwolone: {', '.join(READABLE_ATTRIBUTES)}",
            )
        pattern = reader.pattern(data, "wzorzec", path)
        wait_s = reader.number(data, "czekaj_s", path, default=10.0)
        if locator is not None:
            fields.append(FieldSpec(key, locator, attribute, pattern, wait_s))
    return fields


def _parse_list(reader: _Reader, data: dict[str, Any] | None) -> ListSpec | None:
    if data is None:
        return None
    reader.check_keys(data, "lista", "lista")
    rule = ListRule(
        element_type=reader.text(data, "element", "lista", required=False) or "Button",
        element_name=reader.text(data, "nazwa_elementu", "lista", required=False) or None,
        pattern=reader.pattern(data, "wzorzec", "lista"),
        require_match=reader.flag(data, "tylko_pasujace", "lista", default=False),
        state_prefixes=reader.texts(data, "przedrostki_stanu", "lista"),
        helper_phrases=reader.texts(data, "pomijaj_zawierajace", "lista"),
    )
    max_scrolls = reader.number(data, "max_przewiniec", "lista", default=20, integer=True)
    return ListSpec(rule, max_scrolls)


def parse_config(data: Any, source: str = "<konfiguracja>") -> Config:
    """Waliduje słownik z JSON-a i buduje :class:`Config`. Rzuca :class:`ConfigError`."""
    if not isinstance(data, dict):
        raise ConfigError(source, ["plik musi zawierać obiekt JSON {...}"])

    reader = _Reader()
    reader.check_keys(data, "", "")

    raw_mode = data.get("tryb")
    mode: Mode | None = None
    if raw_mode is None or raw_mode == "":
        reader.missing("tryb")
    else:
        try:
            mode = Mode(raw_mode)
        except ValueError:
            reader.problem("tryb", f"nieznany tryb {raw_mode!r}. {HINTS['tryb'].capitalize()}")

    bundle_id = reader.text(data, "bundle_id", "")
    server_url = reader.text(data, "serwer_appium", "", required=False) or DEFAULT_SERVER_URL

    simulator: SimulatorSettings | None = None
    device: DeviceSettings | None = None
    if mode is Mode.SIMULATOR:
        section = reader.section(data, "symulator") or {}
        reader.check_keys(section, "symulator", "symulator")
        simulator = SimulatorSettings(
            device_name=reader.text(section, "nazwa_urzadzenia", "symulator"),
            platform_version=reader.text(section, "wersja_ios", "symulator"),
        )
    elif mode is Mode.DEVICE:
        section = reader.section(data, "urzadzenie") or {}
        reader.check_keys(section, "urzadzenie", "urzadzenie")
        device = DeviceSettings(
            udid=reader.text(section, "udid", "urzadzenie"),
            team_id=reader.text(section, "team_id", "urzadzenie"),
            signing_id=reader.text(section, "signing_id", "urzadzenie"),
            wda_bundle_id=reader.text(section, "wda_bundle_id", "urzadzenie"),
        )

    session_data = reader.section(data, "sesja") or {}
    reader.check_keys(session_data, "sesja", "sesja")
    extra = session_data.get("dodatkowe_capabilities", {})
    if not isinstance(extra, dict):
        reader.problem("sesja.dodatkowe_capabilities", "oczekiwany obiekt {...}")
        extra = {}
    session = SessionSettings(
        snapshot_max_depth=reader.number(
            session_data, "snapshot_max_depth", "sesja", default=50, integer=True
        ),
        new_command_timeout=reader.number(
            session_data, "new_command_timeout", "sesja", default=300, integer=True
        ),
        restart_app=reader.flag(session_data, "restart_aplikacji", "sesja", default=True),
        extra_capabilities={k: v for k, v in extra.items() if not k.startswith("_")},
    )

    steps = _parse_steps(reader, data.get("kroki"))
    fields = _parse_fields(reader, data.get("odczyt"))
    list_spec = _parse_list(reader, reader.section(data, "lista"))

    output_data = reader.section(data, "wynik") or {}
    reader.check_keys(output_data, "wynik", "wynik")
    output = OutputSettings(
        directory=reader.text(output_data, "katalog", "wynik", required=False) or "artifacts",
        screenshot=reader.flag(output_data, "zrzut_ekranu", "wynik", default=True),
    )

    if reader.problems or mode is None:
        raise ConfigError(source, reader.problems)

    return Config(
        source=source,
        name=reader.text(data, "nazwa", "", required=False) or Path(source).stem,
        mode=mode,
        server_url=server_url,
        bundle_id=bundle_id,
        simulator=simulator,
        device=device,
        session=session,
        steps=steps,
        fields=fields,
        list_spec=list_spec,
        output=output,
    )


def load_config(path: str | Path) -> Config:
    """Wczytuje i waliduje plik konfiguracyjny."""
    file = Path(path)
    if not file.is_file():
        raise ConfigError(
            str(file),
            [
                "nie ma takiego pliku. Gotowy przykład: configs/przyklad-symulator.json; "
                "dla telefonu skopiuj configs/szablon-urzadzenie.json i uzupełnij pola"
            ],
        )
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(
            str(file),
            [f"niepoprawny JSON w wierszu {error.lineno}, kolumnie {error.colno}: {error.msg}"],
        ) from error
    return parse_config(data, str(file))
