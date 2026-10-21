"""Uruchomienie przepływu z pliku konfiguracyjnego.

Przykłady:
    python -m ios_flow.run configs/przyklad-symulator.json
    python -m ios_flow.run configs/przyklad-symulator.json --sprawdz
    python -m ios_flow.run configs/przyklad-symulator.json --lista
    python -m ios_flow.run moja.json --zmienna "Nazwa pozycji"

Kody wyjścia: 0 — sukces, 1 — błąd (konfiguracja, sesja, nawigacja),
2 — przebieg doszedł do końca, ale nie wszystkie pola udało się odczytać.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from ios_flow import version_banner
from ios_flow.config import Config, ConfigError, FieldSpec, load_config
from ios_flow.extract import TreeParseError, collect_list, parse_value, visible_texts
from ios_flow.locators import PLACEHOLDER
from ios_flow.navigate import (
    ElementNotFound,
    Finder,
    NavigationError,
    run_steps,
    split_at_variable,
    substitute_all,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INCOMPLETE = 2


def log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class FieldReader(Finder, Protocol):
    """Sesja, z której da się też czytać atrybuty elementów."""

    def attribute(self, element: Any, name: str) -> str | None: ...


def read_fields(
    session: FieldReader,
    fields: Sequence[FieldSpec],
    log: Callable[[str], None] = log,
) -> tuple[dict[str, str | None], dict[str, str | None]]:
    """Odczytuje pola z bieżącego ekranu. Zwraca (wartości, surowe teksty)."""
    values: dict[str, str | None] = {}
    raw: dict[str, str | None] = {}
    for spec in fields:
        try:
            element = session.find(spec.locator, spec.wait_s)
        except ElementNotFound:
            log(f"Pole „{spec.key}”: nie znalazłem elementu ({spec.locator.describe()})")
            values[spec.key] = raw[spec.key] = None
            continue
        text = session.attribute(element, spec.attribute)
        raw[spec.key] = text
        values[spec.key] = parse_value(text, spec.pattern)
        if values[spec.key] is None:
            log(f"Pole „{spec.key}”: tekst {text!r} nie pasuje do wzorca {spec.pattern!r}")
        else:
            log(f"Pole „{spec.key}”: {values[spec.key]}")
    return values, raw


class _VersionAction(argparse.Action):
    """Wypisuje wersję bez przeformatowania (wbudowana akcja zlewa wiersze w jeden)."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        print(version_banner())
        parser.exit()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ios_flow.run",
        description="Przechodzi ścieżkę z pliku konfiguracyjnego i zapisuje odczytane dane.",
        epilog="Kody wyjścia: 0 sukces, 1 błąd, 2 nie wszystkie pola odczytane.",
    )
    parser.add_argument(
        "--version",
        action=_VersionAction,
        nargs=0,
        help="pokaż wersję i zakończ",
    )
    parser.add_argument(
        "konfiguracja", help="ścieżka do pliku JSON, np. configs/przyklad-symulator.json"
    )
    parser.add_argument("--zmienna", help=f"tekst wstawiany w miejsce {PLACEHOLDER} w krokach")
    parser.add_argument(
        "--lista",
        action="store_true",
        help='zbierz listę pozycji (sekcja "lista") zamiast odczytywać pola',
    )
    parser.add_argument("--wynik", help="ścieżka pliku wynikowego JSON")
    parser.add_argument(
        "--sprawdz",
        action="store_true",
        help="tylko sprawdź konfigurację i pokaż capabilities, bez łączenia z Appium",
    )
    return parser


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _save_failure_evidence(session: Any, base: Path) -> None:
    """Przy błędzie zapisuje zrzut ekranu i drzewo — do diagnozy po fakcie."""
    try:
        session.screenshot(base.with_name(base.name + "_blad.png"))
        xml_path = base.with_name(base.name + "_blad.xml")
        xml_path.write_text(session.page_source(), encoding="utf-8")
        log(f"Zrzut ekranu i drzewo elementów z chwili błędu: {xml_path.parent}/")
    except Exception as error:  # noqa: BLE001 — diagnostyka nie może przykryć błędu głównego
        log(f"Nie udało się zapisać materiałów diagnostycznych: {error}")


def run_flow(session: Any, config: Config, args: argparse.Namespace, base: Path) -> int:
    """Właściwy przebieg na otwartej sesji. Zwraca kod wyjścia."""
    result: dict[str, Any] = {
        "przeplyw": config.name,
        "konfiguracja": config.source,
        "tryb": config.mode.value,
        "aplikacja": config.bundle_id,
        "rozpoczeto": now_iso(),
    }
    if args.zmienna is not None:
        result["zmienna"] = args.zmienna

    if config.session.restart_app:
        log("Restartuję aplikację")
        session.restart_app()

    steps = substitute_all(config.steps, args.zmienna) if args.zmienna else config.steps
    if args.lista:
        before, variable_step, _after = split_at_variable(steps)
        if variable_step is not None:
            log(f"Tryb listy: wykonuję kroki przed krokiem z {PLACEHOLDER}")
        step_results = run_steps(session, before, log=log)
        assert config.list_spec is not None
        items = collect_list(
            session.page_source,
            session.scroll_down,
            config.list_spec.rule,
            config.list_spec.max_scrolls,
            log=log,
        )
        result["lista"] = [
            {"nazwa": item.name, "wartosc": item.value, "stan": item.state} for item in items
        ]
        complete = bool(items)
        if not items:
            log('Nie znalazłem żadnej pozycji listy. Sprawdź sekcję "lista" w konfiguracji.')
        for item in items:
            log(f"  {item.name}: {item.value or '-'}" + (f" [{item.state}]" if item.state else ""))
    else:
        step_results = run_steps(session, steps, log=log)
        values, raw = read_fields(session, config.fields)
        result["odczyt"] = values
        result["surowe"] = raw
        complete = all(value is not None for value in values.values())

    result["kroki"] = [{"opis": r.description, "wynik": r.status.value} for r in step_results]

    # Drzewo pobierane dopiero teraz, po znalezieniu elementów docelowych:
    # wcześniejszy zrzut mógłby nie zawierać elementów, które ładują się wolniej.
    try:
        result["teksty_na_ekranie"] = visible_texts(session.page_source())
    except TreeParseError as error:
        log(str(error))
        result["teksty_na_ekranie"] = []

    result["zrzut_ekranu"] = None
    if config.output.screenshot:
        shot = session.screenshot(base.with_suffix(".png"))
        result["zrzut_ekranu"] = str(shot)
        log(f"Zrzut ekranu: {shot}")

    result["zakonczono"] = now_iso()
    out_path = Path(args.wynik) if args.wynik else base.with_suffix(".json")
    _write_json(out_path, result)
    log(f"Zapisano: {out_path}")

    if not complete:
        log("UWAGA: nie wszystkie dane udało się odczytać. Teksty widoczne na ekranie:")
        for text in result["teksty_na_ekranie"]:
            log(f"  | {text}")
        return EXIT_INCOMPLETE
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = load_config(args.konfiguracja)
    except ConfigError as error:
        print(error, file=sys.stderr)
        return EXIT_ERROR

    if args.lista and config.list_spec is None:
        print(
            f'Konfiguracja {config.source} nie ma sekcji "lista", a użyto --lista.\n'
            'Dodaj sekcję "lista" (opis w README, rozdział Konfiguracja) '
            "albo uruchom bez --lista.",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if config.has_variable_step and args.zmienna is None and not args.lista:
        print(
            f'Jeden z kroków zawiera {PLACEHOLDER}. Podaj wartość: --zmienna "tekst".',
            file=sys.stderr,
        )
        return EXIT_ERROR

    from ios_flow.driver import SessionError, build_capabilities, connect

    if args.sprawdz:
        print(f"Konfiguracja {config.source} jest poprawna (tryb: {config.mode.value}).")
        print("Capabilities, które zostaną wysłane do Appium:")
        print(json.dumps(build_capabilities(config), indent=2, ensure_ascii=False))
        return EXIT_OK

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = Path(config.output.directory) / f"{Path(config.source).stem}_{stamp}"

    log(f"Przepływ: {config.name} (tryb: {config.mode.value})")
    log(f"Łączę z Appium: {config.server_url}")
    try:
        session = connect(config)
    except SessionError as error:
        log(f"BŁĄD: {error}")
        return EXIT_ERROR
    log("Sesja otwarta")

    from selenium.common.exceptions import WebDriverException

    try:
        return run_flow(session, config, args, base)
    except NavigationError as error:
        log(f"BŁĄD: {error}")
        _save_failure_evidence(session, base)
        return EXIT_ERROR
    except WebDriverException as error:
        log(f"BŁĄD sesji Appium: {(error.msg or str(error)).strip()}")
        log("Sesja mogła wygasnąć (newCommandTimeout) albo WebDriverAgent przestał odpowiadać.")
        return EXIT_ERROR
    finally:
        session.quit()
        log("Sesja zamknięta")


if __name__ == "__main__":
    sys.exit(main())
