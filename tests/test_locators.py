"""Budowanie predykatów iOS: dokładne dopasowanie i zabezpieczanie znaków."""

import pytest
from conftest import element_matches, load_fixture

from ios_flow.extract import parse_tree
from ios_flow.locators import (
    STRATEGY_CLASS_CHAIN,
    STRATEGY_PREDICATE,
    STRATEGY_XPATH,
    Locator,
    LocatorKind,
    escape_literal,
    full_element_type,
    label_matches,
    label_predicate,
    name_predicate,
    to_query,
)


class TestExactMatch:
    def test_predicate_uses_equality_not_contains(self):
        predicate = label_predicate("20%")
        assert predicate == "label == '20%'"
        assert "CONTAINS" not in predicate

    @pytest.mark.parametrize("variant", ["20%HM", "20%VM", "20%HM, Until 2030-01-31", "120%"])
    def test_exact_label_does_not_match_variants(self, variant):
        assert not label_matches(variant, "20%")
        assert not label_matches(variant, "20%", allow_suffix=True)

    def test_suffix_requires_separator(self):
        # "20%HM" zaczyna się od "20%", ale nie od "20%, " — więc nie pasuje.
        assert label_matches("20%, Until 2030-01-31", "20%", allow_suffix=True)
        assert not label_matches("20%HM, Until 2030-01-31", "20%", allow_suffix=True)
        assert label_predicate("20%", allow_suffix=True) == (
            "(label == '20%' OR label BEGINSWITH '20%, ')"
        )

    def test_on_fixture_only_exact_row_matches(self):
        elements = parse_tree(load_fixture("lista_wariantow.xml"))
        locator = Locator(LocatorKind.LABEL, "20%", "Button", allow_suffix=True)
        hits = [e.label for e in elements if element_matches(e, locator)]
        assert hits == ["20%"]

    def test_variant_with_state_prefix_found_exactly(self):
        elements = parse_tree(load_fixture("lista_wariantow.xml"))
        locator = Locator(
            LocatorKind.LABEL, "20%VM", "Button", state_prefixes=("Selected",), allow_suffix=True
        )
        hits = [e.label for e in elements if element_matches(e, locator)]
        assert hits == ["Selected, 20%VM, Until 2030-02-28"]

    def test_state_prefix_variants_in_predicate(self):
        predicate = label_predicate("20%VM", "Button", state_prefixes=("Selected",))
        assert predicate == (
            "type == 'XCUIElementTypeButton' AND (label == '20%VM' OR label == 'Selected, 20%VM')"
        )


class TestEscaping:
    def test_apostrophe_is_escaped(self):
        assert escape_literal("Tom's Option") == "Tom\\'s Option"
        assert label_predicate("Tom's Option") == "label == 'Tom\\'s Option'"

    def test_backslash_escaped_before_apostrophe(self):
        # Kolejność ma znaczenie: najpierw \, potem ', inaczej \' zamieni się w \\'.
        assert escape_literal("a\\'b") == "a\\\\\\'b"

    def test_apostrophe_cannot_close_literal(self):
        hostile = "x' OR label CONTAINS '"
        predicate = name_predicate(hostile)
        assert predicate == "name == 'x\\' OR label CONTAINS \\''"

    def test_fixture_label_with_apostrophe_still_matches(self):
        elements = parse_tree(load_fixture("lista_wariantow.xml"))
        locator = Locator(LocatorKind.LABEL, "Tom's Option", "Button")
        assert [e.label for e in elements if element_matches(e, locator)] == ["Tom's Option"]


class TestPlaceholder:
    def test_label_value_inserted_raw_and_escaped_later(self):
        locator = Locator(LocatorKind.LABEL, "{zmienna}", "Button").substitute("Tom's")
        assert locator.value == "Tom's"
        assert to_query(locator)[1] == "type == 'XCUIElementTypeButton' AND label == 'Tom\\'s'"

    def test_raw_predicate_value_escaped_on_insert(self):
        locator = Locator(LocatorKind.PREDICATE, "label == '{zmienna}'").substitute("Tom's")
        assert locator.value == "label == 'Tom\\'s'"

    def test_locator_without_placeholder_unchanged(self):
        locator = Locator(LocatorKind.ID, "BackButton")
        assert locator.substitute("cokolwiek") is locator


class TestQuery:
    def test_id_becomes_exact_name_predicate_with_type(self):
        locator = Locator(LocatorKind.ID, "SW_VERSION_SPECIFIER", "Button")
        assert to_query(locator) == (
            STRATEGY_PREDICATE,
            "type == 'XCUIElementTypeButton' AND name == 'SW_VERSION_SPECIFIER'",
        )

    def test_raw_predicate_wrapped_in_parentheses_with_type(self):
        locator = Locator(LocatorKind.PREDICATE, "label == 'A' OR label == 'B'", "Cell")
        assert to_query(locator)[1] == (
            "type == 'XCUIElementTypeCell' AND (label == 'A' OR label == 'B')"
        )

    def test_class_chain_and_xpath_passed_through(self):
        chain = "**/XCUIElementTypeCell[`name == 'X'`]"
        assert to_query(Locator(LocatorKind.CLASS_CHAIN, chain)) == (STRATEGY_CLASS_CHAIN, chain)
        xpath = "//XCUIElementTypeButton[@name='X']"
        assert to_query(Locator(LocatorKind.XPATH, xpath)) == (STRATEGY_XPATH, xpath)

    def test_element_type_short_and_full_names(self):
        assert full_element_type("Button") == "XCUIElementTypeButton"
        assert full_element_type("XCUIElementTypeButton") == "XCUIElementTypeButton"

    def test_cell_and_button_share_name_type_disambiguates(self):
        # Na ekranie To urządzenie komórka i przycisk mają ten sam identyfikator.
        elements = parse_tree(load_fixture("to_urzadzenie_1.xml"))
        any_type = Locator(LocatorKind.ID, "User Data Capacity")
        button = Locator(LocatorKind.ID, "User Data Capacity", "Button")
        assert [e.element_type for e in elements if element_matches(e, any_type)] == [
            "Cell",
            "Button",
        ]
        assert [e.label for e in elements if element_matches(e, button)] == ["Capacity, 494,38 GB"]
