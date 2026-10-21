"""Podgląd elementów bieżącego ekranu — pomoc przy ustalaniu lokatorów.

Przykłady:
    python -m ios_flow.inspect configs/przyklad-symulator.json
    python -m ios_flow.inspect configs/przyklad-symulator.json --wszystkie
    python -m ios_flow.inspect configs/przyklad-symulator.json --szukaj wersja
    python -m ios_flow.inspect configs/przyklad-symulator.json --zapisz-xml ekran.xml
    python -m ios_flow.inspect --z-pliku tests/fixtures/to_urzadzenie_1.xml

Z konfiguracją łączy się z Appium i NIE restartuje aplikacji: pokazuje
ekran, który jest w tej chwili widoczny. Z ``--z-pliku`` działa bez Appium.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from ios_flow.extract import ElementInfo, TreeParseError, parse_tree

# Typy, w które zwykle się klika albo wpisuje — domyślny filtr.
INTERACTIVE_TYPES = (
    "Button",
    "Cell",
    "Link",
    "Switch",
    "TextField",
    "SecureTextField",
    "SearchField",
    "SegmentedControl",
)


def select_elements(
    elements: Sequence[ElementInfo],
    show_all: bool = False,
    search: str | None = None,
) -> list[ElementInfo]:
    """Elementy warte pokazania: widoczne, z jakimkolwiek tekstem, bez powtórzeń."""
    selected: list[ElementInfo] = []
    needle = search.casefold() if search else None
    for element in elements:
        if not element.visible or not (element.name or element.label or element.value):
            continue
        if not show_all and element.element_type not in INTERACTIVE_TYPES:
            continue
        if needle is not None:
            haystack = " ".join(filter(None, (element.name, element.label, element.value)))
            if needle not in haystack.casefold():
                continue
        if element not in selected:
            selected.append(element)
    return selected


def suggest_locator(element: ElementInfo) -> dict[str, str]:
    """Propozycja lokatora do konfiguracji.

    Identyfikator (``name``) różny od etykiety zwykle nadał programista —
    nie zależy od języka systemu, więc ma pierwszeństwo. Gdy ``name`` jest
    tylko kopią etykiety, proponujemy dokładne dopasowanie etykiety.
    """
    if element.name and element.name != element.label:
        return {"typ": "id", "wartosc": element.name, "element": element.element_type}
    text = element.label or element.name or element.value or ""
    return {"typ": "etykieta", "wartosc": text, "element": element.element_type}


def _cut(text: str | None, limit: int) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_table(elements: Sequence[ElementInfo]) -> str:
    if not elements:
        return "Nic nie znalazłem. Spróbuj z --wszystkie albo bez --szukaj."
    lines = [
        f"{'#':<3} {'TYP':<12} {'NAME (identyfikator)':<36} {'LABEL (etykieta)':<30} VALUE",
        "-" * 100,
    ]
    for number, element in enumerate(elements, start=1):
        lines.append(
            f"{number:<3} {_cut(element.element_type, 12):<12} {_cut(element.name, 36):<36} "
            f"{_cut(element.label, 30):<30} {_cut(element.value, 20)}"
        )
    lines.append("")
    lines.append(f"Razem: {len(elements)}. Propozycje lokatorów do pliku konfiguracyjnego:")
    for number, element in enumerate(elements, start=1):
        snippet = json.dumps(suggest_locator(element), ensure_ascii=False)
        lines.append(f'{number:<3} "lokator": {snippet}')
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ios_flow.inspect",
        description="Pokazuje elementy bieżącego ekranu i proponuje lokatory.",
    )
    parser.add_argument("konfiguracja", nargs="?", help="plik JSON (tryb, urządzenie, aplikacja)")
    parser.add_argument("--wszystkie", action="store_true", help="pokaż też teksty i kontenery")
    parser.add_argument("--szukaj", help="tylko elementy zawierające ten fragment tekstu")
    parser.add_argument("--zapisz-xml", help="zapisz pełne drzewo elementów do pliku")
    parser.add_argument("--z-pliku", help="czytaj drzewo z pliku XML zamiast z urządzenia")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.z_pliku:
        xml = Path(args.z_pliku).read_text(encoding="utf-8")
    elif args.konfiguracja:
        from ios_flow.config import ConfigError, load_config
        from ios_flow.driver import SessionError, connect

        try:
            config = load_config(args.konfiguracja)
            # Bez ponownego uruchamiania aplikacji — interesuje nas bieżący ekran.
            session = connect(
                config,
                extra={"appium:forceAppLaunch": False, "appium:shouldTerminateApp": False},
            )
        except (ConfigError, SessionError) as error:
            print(error, file=sys.stderr)
            return 1
        try:
            xml = session.page_source()
        finally:
            session.quit()
    else:
        print("Podaj plik konfiguracyjny albo --z-pliku <drzewo.xml>.", file=sys.stderr)
        return 1

    if args.zapisz_xml:
        Path(args.zapisz_xml).write_text(xml, encoding="utf-8")
        print(f"Drzewo zapisane do: {args.zapisz_xml}")

    try:
        elements = parse_tree(xml)
    except TreeParseError as error:
        print(error, file=sys.stderr)
        return 1
    print(format_table(select_elements(elements, args.wszystkie, args.szukaj)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
