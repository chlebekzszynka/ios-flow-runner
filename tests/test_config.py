"""Ładowanie i walidacja konfiguracji: czytelne błędy z podpowiedziami."""

import json
import re
from pathlib import Path

import pytest

from ios_flow.config import (
    DEFAULT_SERVER_URL,
    ConfigError,
    Mode,
    load_config,
    parse_config,
)
from ios_flow.locators import LocatorKind

CONFIGS = Path(__file__).parent.parent / "configs"


def problems_of(data) -> list[str]:
    with pytest.raises(ConfigError) as error:
        parse_config(data, "test.json")
    return error.value.problems


class TestValidConfig:
    def test_simulator_config_parsed(self, simulator_data):
        config = parse_config(simulator_data, "test.json")
        assert config.mode is Mode.SIMULATOR
        assert config.simulator is not None
        assert config.simulator.device_name == "iPhone 17"
        assert config.device is None
        assert config.server_url == DEFAULT_SERVER_URL
        assert [s.description for s in config.steps] == ["Ogólne", "To urządzenie"]
        assert config.steps[0].locator.kind is LocatorKind.ID
        assert config.fields[0].key == "wersja_systemu"
        assert config.fields[0].attribute == "label"

    def test_device_config_parsed(self, device_data):
        config = parse_config(device_data, "test.json")
        assert config.mode is Mode.DEVICE
        assert config.device is not None
        assert config.device.team_id == "ABCDE12345"
        assert config.simulator is None

    def test_defaults(self, device_data):
        config = parse_config(device_data, "test.json")
        assert config.session.snapshot_max_depth == 50
        assert config.session.new_command_timeout == 300
        assert config.session.restart_app is True
        assert config.output.directory == "artifacts"
        assert config.steps == []

    def test_comment_keys_ignored(self, simulator_data):
        simulator_data["_opis"] = "komentarz"
        simulator_data["symulator"]["_skad"] = "xcrun simctl list"
        parse_config(simulator_data, "test.json")

    def test_step_description_defaults_to_locator_value(self, simulator_data):
        del simulator_data["kroki"][0]["opis"]
        config = parse_config(simulator_data, "test.json")
        assert config.steps[0].description == "com.apple.settings.general"


class TestMissingFields:
    @pytest.mark.parametrize(
        ("field", "hint"),
        [
            ("udid", "idevice_id -l"),
            ("team_id", "security find-identity -v -p codesigning"),
            ("wda_bundle_id", "WebDriverAgentRunner"),
            ("signing_id", "Apple Development"),
        ],
    )
    def test_device_field_missing_names_field_and_source(self, device_data, field, hint):
        del device_data["urzadzenie"][field]
        problems = problems_of(device_data)
        assert len(problems) == 1
        assert problems[0].startswith(f"urzadzenie.{field}: brak wartości")
        assert hint in problems[0]

    @pytest.mark.parametrize(
        ("field", "hint"),
        [("nazwa_urzadzenia", "xcrun simctl list devices"), ("wersja_ios", "-- iOS")],
    )
    def test_simulator_field_missing(self, simulator_data, field, hint):
        simulator_data["symulator"][field] = ""
        problems = problems_of(simulator_data)
        assert problems[0].startswith(f"symulator.{field}: brak wartości")
        assert hint in problems[0]

    def test_all_problems_reported_at_once(self, device_data):
        device_data["urzadzenie"] = {"signing_id": "Apple Development"}
        del device_data["bundle_id"]
        problems = problems_of(device_data)
        assert [p.split(":")[0] for p in problems] == [
            "bundle_id",
            "urzadzenie.udid",
            "urzadzenie.team_id",
            "urzadzenie.wda_bundle_id",
        ]

    def test_whole_mode_section_missing(self, simulator_data):
        del simulator_data["symulator"]
        problems = problems_of(simulator_data)
        assert any(p.startswith("symulator.nazwa_urzadzenia") for p in problems)

    def test_missing_mode(self, simulator_data):
        del simulator_data["tryb"]
        problems = problems_of(simulator_data)
        assert problems == ['tryb: brak wartości. Skąd wziąć: wpisz "symulator" albo "urzadzenie"']

    def test_unknown_mode(self, simulator_data):
        simulator_data["tryb"] = "telefon"
        assert "nieznany tryb 'telefon'" in problems_of(simulator_data)[0]

    def test_error_message_lists_problems(self, device_data):
        del device_data["urzadzenie"]["udid"]
        with pytest.raises(ConfigError) as error:
            parse_config(device_data, "moj.json")
        text = str(error.value)
        assert text.startswith("Konfiguracja moj.json ma błędy (1):")
        assert "\n  - urzadzenie.udid: brak wartości" in text


class TestOtherSections:
    def test_mode_section_of_other_mode_not_required(self, simulator_data):
        # Tryb symulator nie wymaga pól telefonu i odwrotnie.
        assert parse_config(simulator_data, "x").device is None

    def test_unknown_key_reported_as_typo(self, simulator_data):
        simulator_data["kroki"][0]["opcjonalne"] = True
        problems = problems_of(simulator_data)
        assert problems[0].startswith("kroki[1].opcjonalne: nieznane pole")
        assert "opcjonalny" in problems[0]

    def test_unknown_locator_type(self, simulator_data):
        simulator_data["kroki"][0]["lokator"]["typ"] = "css"
        problems = problems_of(simulator_data)
        assert "nieznany typ lokatora 'css'" in problems[0]
        assert "etykieta" in problems[0]

    def test_bad_regex(self, simulator_data):
        simulator_data["odczyt"]["wersja_systemu"]["wzorzec"] = "(niedomkniety"
        assert "błędne wyrażenie regularne" in problems_of(simulator_data)[0]

    def test_bad_attribute(self, simulator_data):
        simulator_data["odczyt"]["wersja_systemu"]["atrybut"] = "text"
        assert "nieznany atrybut 'text'" in problems_of(simulator_data)[0]

    def test_negative_wait(self, simulator_data):
        simulator_data["kroki"][0]["czekaj_s"] = -1
        assert "kroki[1].czekaj_s" in problems_of(simulator_data)[0]

    def test_placeholder_only_once(self, simulator_data):
        for step in simulator_data["kroki"]:
            step["lokator"] = {"typ": "etykieta", "wartosc": "{zmienna}"}
        assert any("najwyżej w jednym kroku" in p for p in problems_of(simulator_data))

    def test_placeholder_not_allowed_in_xpath(self, simulator_data):
        xpath = "//*[@name='{zmienna}']"
        simulator_data["kroki"][0]["lokator"] = {"typ": "xpath", "wartosc": xpath}
        assert "{zmienna} wolno użyć tylko" in problems_of(simulator_data)[0]

    def test_state_prefix_only_for_label(self, simulator_data):
        simulator_data["kroki"][0]["lokator"]["przedrostki_stanu"] = ["Selected"]
        assert 'tylko z typem "etykieta"' in problems_of(simulator_data)[0]

    def test_list_section(self, simulator_data):
        simulator_data["lista"] = {
            "nazwa_elementu": "VariantRow",
            "przedrostki_stanu": ["Selected"],
            "pomijaj_zawierajace": ["text for screen reader"],
            "max_przewiniec": 5,
        }
        config = parse_config(simulator_data, "x")
        assert config.list_spec is not None
        assert config.list_spec.rule.element_type == "Button"
        assert config.list_spec.rule.state_prefixes == ("Selected",)
        assert config.list_spec.max_scrolls == 5

    def test_variable_step_detected(self, simulator_data):
        simulator_data["kroki"][1]["lokator"] = {"typ": "etykieta", "wartosc": "{zmienna}"}
        assert parse_config(simulator_data, "x").has_variable_step


class TestLoadFile:
    def test_missing_file_points_to_examples(self, tmp_path):
        with pytest.raises(ConfigError) as error:
            load_config(tmp_path / "brak.json")
        assert "configs/przyklad-symulator.json" in str(error.value)

    def test_invalid_json_shows_position(self, tmp_path):
        file = tmp_path / "zly.json"
        file.write_text('{\n  "tryb": "symulator",\n}', encoding="utf-8")
        with pytest.raises(ConfigError) as error:
            load_config(file)
        # Numer wiersza zależy od wersji Pythona (3.13+ wskazuje przecinek w wierszu 2).
        assert re.search(r"niepoprawny JSON w wierszu [23], kolumnie \d+", str(error.value))

    def test_not_an_object(self, tmp_path):
        file = tmp_path / "lista.json"
        file.write_text(json.dumps([1, 2]), encoding="utf-8")
        with pytest.raises(ConfigError, match="obiekt JSON"):
            load_config(file)


class TestShippedConfigs:
    def test_simulator_example_is_valid(self):
        config = load_config(CONFIGS / "przyklad-symulator.json")
        assert config.mode is Mode.SIMULATOR
        assert config.bundle_id == "com.apple.Preferences"
        assert config.list_spec is not None
        assert {f.key for f in config.fields} >= {"wersja_systemu", "nazwa_urzadzenia"}

    def test_device_template_lists_exactly_the_empty_fields(self):
        with pytest.raises(ConfigError) as error:
            load_config(CONFIGS / "szablon-urzadzenie.json")
        fields = [p.split(":")[0] for p in error.value.problems]
        assert fields == ["urzadzenie.udid", "urzadzenie.team_id", "urzadzenie.wda_bundle_id"]
