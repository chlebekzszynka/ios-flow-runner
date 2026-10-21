"""Odczyt danych z drzewa: wartości, stan, pomocnicze elementy, scalanie list."""

import re

import pytest
from conftest import FakeDevice, load_fixture

from ios_flow.extract import (
    ListItem,
    ListRule,
    TreeParseError,
    collect_list,
    is_screen_reader_helper,
    items_on_screen,
    merge_new,
    parse_tree,
    parse_value,
    strip_state_prefix,
    visible_texts,
)

ROW_VALUE = r"^[^,]+,\s*(?P<wartosc>.+)$"
ROW_NAME_VALUE = r"^(?P<nazwa>[^,]+),\s*(?P<wartosc>.+)$"


def label_of(fixture: str, element_type: str, name: str) -> str | None:
    for element in parse_tree(load_fixture(fixture)):
        if element.element_type == element_type and element.name == name:
            return element.label
    raise AssertionError(f"Brak {element_type} {name} w {fixture}")


class TestParseTree:
    def test_reads_type_and_attributes(self):
        elements = parse_tree(load_fixture("ogolne.xml"))
        about = next(e for e in elements if e.name == "com.apple.settings.general.about")
        assert about.element_type == "Button"
        assert about.label == "About"
        assert about.visible is True

    def test_invisible_flag(self):
        elements = parse_tree(load_fixture("ogolne.xml"))
        hidden_title = [e for e in elements if e.element_type == "StaticText" and not e.visible]
        assert [e.label for e in hidden_title] == ["General"]

    def test_xml_entities_decoded(self):
        elements = parse_tree(load_fixture("ustawienia_glowny.xml"))
        assert any(e.label == "Home Screen & App Library" for e in elements)

    def test_broken_xml_gives_readable_error(self):
        with pytest.raises(TreeParseError, match="nie jest poprawnym XML-em"):
            parse_tree("<AppiumAUT><XCUIElementTypeButton")


class TestParseValue:
    def test_version_from_row_label(self):
        label = label_of("to_urzadzenie_1.xml", "Button", "SW_VERSION_SPECIFIER")
        assert parse_value(label, ROW_VALUE) == "27.0"

    def test_device_name_from_row_label(self):
        label = label_of("to_urzadzenie_1.xml", "Button", "NAME_CELL_ID")
        assert parse_value(label, ROW_VALUE) == "iPhone"

    def test_value_containing_comma_read_from_button(self):
        # Etykieta komórki rozbija przecinek dziesiętny ("494, 38 GB"), przycisk nie.
        button = label_of("to_urzadzenie_1.xml", "Button", "User Data Capacity")
        cell = label_of("to_urzadzenie_1.xml", "Cell", "User Data Capacity")
        assert parse_value(button, ROW_VALUE) == "494,38 GB"
        assert parse_value(cell, ROW_VALUE) == "494, 38 GB"

    def test_first_group_when_no_named_group(self):
        assert parse_value("iOS Version, 27.0", r"(\d+\.\d+)") == "27.0"

    def test_whole_match_when_no_groups(self):
        assert parse_value("Model Number, A3258ZE/A", r"[A-Z]\d{4}[A-Z]{2}/A") == "A3258ZE/A"

    def test_no_pattern_returns_stripped_text(self):
        assert parse_value("  iPhone 17 ", None) == "iPhone 17"

    def test_no_match_returns_none(self):
        assert parse_value("Certificate Trust Settings", ROW_VALUE) is None

    def test_missing_text_returns_none(self):
        assert parse_value(None, ROW_VALUE) is None

    def test_precompiled_pattern(self):
        assert parse_value("Songs, 0", re.compile(ROW_VALUE)) == "0"


class TestStatePrefix:
    def test_prefix_removed_and_reported(self):
        assert strip_state_prefix("Selected, 20%VM", ["Selected"]) == ("20%VM", "Selected")

    def test_label_without_prefix_unchanged(self):
        assert strip_state_prefix("20%HM", ["Selected"]) == ("20%HM", None)

    def test_prefix_must_be_whole_segment(self):
        assert strip_state_prefix("Selectedness, X", ["Selected"]) == ("Selectedness, X", None)

    def test_first_matching_prefix_wins(self):
        assert strip_state_prefix("Active, X", ["Selected", "Active"]) == ("X", "Active")


class TestScreenReaderHelpers:
    PHRASES = ("text for screen reader", "double tap")

    def test_helper_detected_case_insensitive(self):
        label = "Text for screen reader: double tap to choose a variant"
        assert is_screen_reader_helper(label, self.PHRASES)

    def test_normal_label_kept(self):
        assert not is_screen_reader_helper("20%HM, Until 2030-01-31", self.PHRASES)

    def test_empty_label_is_not_helper(self):
        assert not is_screen_reader_helper(None, self.PHRASES)
        assert not is_screen_reader_helper("", self.PHRASES)

    def test_helpers_dropped_from_list(self):
        rule = ListRule(element_name="VariantRow", helper_phrases=("text for screen reader",))
        names = [i.name for i in items_on_screen(load_fixture("lista_wariantow.xml"), rule)]
        assert not any("screen reader" in name for name in names)


class TestItemsOnScreen:
    def test_about_rows_split_into_name_and_value(self):
        rule = ListRule(pattern=ROW_NAME_VALUE, require_match=True)
        items = items_on_screen(load_fixture("to_urzadzenie_1.xml"), rule)
        assert items[0] == ListItem("Name", "iPhone")
        assert ListItem("Capacity", "494,38 GB") in items
        # BackButton ("General") i "chevron" nie mają przecinka — odrzucone.
        assert all(item.name not in ("General", "chevron") for item in items)

    def test_variant_list_full_rule(self):
        rule = ListRule(
            element_name="VariantRow",
            pattern=r"^(?P<nazwa>[^,]+)(?:,\s*Until\s+(?P<wartosc>\d{4}-\d{2}-\d{2}))?$",
            state_prefixes=("Selected",),
            helper_phrases=("text for screen reader",),
        )
        items = items_on_screen(load_fixture("lista_wariantow.xml"), rule)
        assert items == [
            ListItem("20%"),
            ListItem("20%HM", "2030-01-31"),
            ListItem("20%VM", "2030-02-28", state="Selected"),
            ListItem("Tom's Option"),
        ]

    def test_exact_element_name_skips_deeper_paths(self):
        rule = ListRule(element_name="VariantRow")
        labels = [i.name for i in items_on_screen(load_fixture("lista_wariantow.xml"), rule)]
        assert "More info" not in labels

    def test_invisible_skipped_by_default(self):
        rule = ListRule(element_name="VariantRow")
        names = [i.name for i in items_on_screen(load_fixture("lista_wariantow.xml"), rule)]
        assert "30%" not in names
        everything = ListRule(element_name="VariantRow", only_visible=False)
        names = [i.name for i in items_on_screen(load_fixture("lista_wariantow.xml"), everything)]
        assert "30%" in names


class TestMerge:
    def test_merge_adds_only_new_and_keeps_order(self):
        collected: dict[str, ListItem] = {}
        assert merge_new(collected, [ListItem("A"), ListItem("B")]) == 2
        assert merge_new(collected, [ListItem("B"), ListItem("C"), ListItem("A")]) == 1
        assert list(collected) == ["A", "B", "C"]

    def test_first_occurrence_wins(self):
        collected: dict[str, ListItem] = {}
        merge_new(collected, [ListItem("A", "1")])
        merge_new(collected, [ListItem("A", "2")])
        assert collected["A"].value == "1"

    def test_two_scroll_positions_merged_without_duplicates(self):
        rule = ListRule(pattern=ROW_NAME_VALUE, require_match=True)
        device = FakeDevice("to_urzadzenie_1.xml", scroll_pages=["to_urzadzenie_2.xml"])
        items = collect_list(device.page_source, device.scroll_down, rule, max_scrolls=10)
        names = [item.name for item in items]
        assert len(names) == len(set(names))
        # "Name" widać tylko na pierwszym ekranie, Wi-Fi i Bluetooth tylko na drugim.
        assert names[0] == "Name"
        assert names[-2:] == ["Wi-Fi Address", "Bluetooth"]
        assert len(names) == 13

    def test_stops_after_two_scrolls_without_new_items(self):
        rule = ListRule(pattern=ROW_NAME_VALUE, require_match=True)
        device = FakeDevice("to_urzadzenie_1.xml", scroll_pages=["to_urzadzenie_2.xml"])
        collect_list(device.page_source, device.scroll_down, rule, max_scrolls=10)
        # ekran 1: nowe; ekran 2: nowe; ekran 3 i 4 (koniec listy): brak nowych -> stop
        assert device.scrolls == 1
        assert device.scroll_calls == 3

    def test_respects_max_scrolls(self):
        scrolls: list[int] = []
        pages = iter(["to_urzadzenie_1.xml", "to_urzadzenie_2.xml"] * 5)

        def scroll() -> bool:
            scrolls.append(1)
            return True

        rule = ListRule(pattern=ROW_NAME_VALUE, require_match=True)
        collect_list(lambda: load_fixture(next(pages)), scroll, rule, max_scrolls=1)
        assert len(scrolls) == 1

    def test_stops_when_scroll_fails(self):
        rule = ListRule(pattern=ROW_NAME_VALUE, require_match=True)
        items = collect_list(
            lambda: load_fixture("to_urzadzenie_1.xml"), lambda: False, rule, max_scrolls=10
        )
        assert len(items) == 11


class TestVisibleTexts:
    def test_only_visible_static_texts_without_duplicates(self):
        texts = visible_texts(load_fixture("ogolne.xml"))
        assert texts == ["About", "Keyboard", "Language & Region"]

    def test_long_texts_cut(self):
        texts = visible_texts(load_fixture("to_urzadzenie_1.xml"), limit=5)
        assert "Seri…" in texts
