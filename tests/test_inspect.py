"""Podgląd elementów ekranu na zapisanych drzewach."""

from pathlib import Path

from conftest import load_fixture

from ios_flow.extract import parse_tree
from ios_flow.inspect import format_table, main, select_elements, suggest_locator

FIXTURES = Path(__file__).parent / "fixtures"


def test_default_shows_interactive_visible_elements():
    elements = select_elements(parse_tree(load_fixture("ogolne.xml")))
    assert [e.name for e in elements] == [
        "BackButton",
        "com.apple.settings.general.about",
        "com.apple.settings.general.keyboard",
        "com.apple.settings.general.languageAndRegion",
    ]


def test_search_is_case_insensitive_over_all_attributes():
    elements = select_elements(parse_tree(load_fixture("to_urzadzenie_1.xml")), search="VERSION")
    assert {e.element_type for e in elements} == {"Cell", "Button"}
    assert all(e.name == "SW_VERSION_SPECIFIER" for e in elements)


def test_show_all_includes_static_texts():
    elements = select_elements(parse_tree(load_fixture("ogolne.xml")), show_all=True)
    assert any(e.element_type == "StaticText" for e in elements)


def test_suggests_id_when_name_differs_from_label():
    element = next(
        e
        for e in parse_tree(load_fixture("ogolne.xml"))
        if e.name == "com.apple.settings.general.about"
    )
    assert suggest_locator(element) == {
        "typ": "id",
        "wartosc": "com.apple.settings.general.about",
        "element": "Button",
    }


def test_suggests_label_when_name_copies_label():
    element = next(
        e
        for e in parse_tree(load_fixture("ogolne.xml"))
        if e.element_type == "StaticText" and e.label == "About"
    )
    assert suggest_locator(element)["typ"] == "etykieta"


def test_empty_result_has_hint():
    assert "--wszystkie" in format_table([])


def test_cli_reads_saved_tree_without_appium(capsys):
    assert main(["--z-pliku", str(FIXTURES / "ogolne.xml")]) == 0
    out = capsys.readouterr().out
    assert "com.apple.settings.general.about" in out
    assert '"lokator": {"typ": "id"' in out
