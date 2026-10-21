"""Przebieg od początku do końca na atrapie urządzenia oraz ścieżki CLI bez Appium."""

import argparse
import json
from pathlib import Path

import pytest
from conftest import FakeDevice

from ios_flow.config import FieldSpec, load_config, parse_config
from ios_flow.locators import Locator, LocatorKind
from ios_flow.run import EXIT_ERROR, EXIT_INCOMPLETE, EXIT_OK, main, read_fields, run_flow

CONFIGS = Path(__file__).parent.parent / "configs"
ROW_VALUE = r"^[^,]+,\s*(?P<wartosc>.+)$"


def args(**overrides) -> argparse.Namespace:
    values = {"zmienna": None, "lista": False, "wynik": None, "sprawdz": False}
    values.update(overrides)
    return argparse.Namespace(**values)


def quiet(_message: str) -> None:
    pass


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("ios_flow.navigate.time.sleep", lambda _s: None)


class TestReadFields:
    def test_values_and_raw_texts(self):
        device = FakeDevice("to_urzadzenie_1.xml")
        fields = [
            FieldSpec(
                "wersja",
                Locator(LocatorKind.ID, "SW_VERSION_SPECIFIER", "Button"),
                pattern=ROW_VALUE,
            ),
            FieldSpec(
                "nazwa", Locator(LocatorKind.ID, "NAME_CELL_ID", "Button"), pattern=ROW_VALUE
            ),
        ]
        values, raw = read_fields(device, fields, log=quiet)
        assert values == {"wersja": "27.0", "nazwa": "iPhone"}
        assert raw == {"wersja": "iOS Version, 27.0", "nazwa": "Name, iPhone"}

    def test_missing_element_gives_none(self):
        device = FakeDevice("ogolne.xml")
        fields = [FieldSpec("wersja", Locator(LocatorKind.ID, "SW_VERSION_SPECIFIER"))]
        values, raw = read_fields(device, fields, log=quiet)
        assert values == {"wersja": None}
        assert raw == {"wersja": None}

    def test_pattern_mismatch_gives_none_and_keeps_raw(self):
        device = FakeDevice("to_urzadzenie_1.xml")
        fields = [FieldSpec("x", Locator(LocatorKind.ID, "CERT_TRUST_SETTINGS"), pattern=ROW_VALUE)]
        values, raw = read_fields(device, fields, log=quiet)
        assert values == {"x": None}
        assert raw == {"x": "Certificate Trust Settings"}


class TestRunFlow:
    def test_example_config_end_to_end(self, tmp_path, settings_device):
        config = load_config(CONFIGS / "przyklad-symulator.json")
        base = tmp_path / "wynik"
        code = run_flow(settings_device, config, args(), base)

        assert code == EXIT_OK
        assert settings_device.restarts == 1
        assert settings_device.clicks == [
            "com.apple.settings.general",
            "com.apple.settings.general.about",
        ]
        result = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
        assert result["odczyt"] == {
            "wersja_systemu": "27.0",
            "nazwa_urzadzenia": "iPhone",
            "model": "iPhone 17",
        }
        assert result["zrzut_ekranu"] == str(base.with_suffix(".png"))
        assert base.with_suffix(".png").exists()
        assert result["rozpoczeto"] and result["zakonczono"]
        assert "iOS Version" in result["teksty_na_ekranie"]
        assert [k["wynik"] for k in result["kroki"]] == ["kliknięty", "kliknięty"]

    def test_unreadable_field_gives_incomplete_exit_code(self, tmp_path, simulator_data):
        simulator_data["odczyt"]["brak"] = {
            "lokator": {"typ": "id", "wartosc": "NOPE"},
            "czekaj_s": 0.1,
        }
        config = parse_config(simulator_data, "x.json")
        device = FakeDevice(
            "ustawienia_glowny.xml",
            {
                ("ustawienia_glowny.xml", "com.apple.settings.general"): "ogolne.xml",
                ("ogolne.xml", "com.apple.settings.general.about"): "to_urzadzenie_1.xml",
            },
        )
        code = run_flow(device, config, args(), tmp_path / "w")
        assert code == EXIT_INCOMPLETE
        result = json.loads((tmp_path / "w.json").read_text(encoding="utf-8"))
        assert result["odczyt"] == {"wersja_systemu": "27.0", "brak": None}

    def test_list_mode_collects_rows_across_scrolls(self, tmp_path):
        config = load_config(CONFIGS / "przyklad-symulator.json")
        device = FakeDevice(
            "ustawienia_glowny.xml",
            {
                ("ustawienia_glowny.xml", "com.apple.settings.general"): "ogolne.xml",
                ("ogolne.xml", "com.apple.settings.general.about"): "to_urzadzenie_1.xml",
            },
            scroll_pages=["to_urzadzenie_2.xml"],
        )
        code = run_flow(device, config, args(lista=True), tmp_path / "l")
        assert code == EXIT_OK
        result = json.loads((tmp_path / "l.json").read_text(encoding="utf-8"))
        names = [row["nazwa"] for row in result["lista"]]
        assert names[0] == "Name"
        assert "Bluetooth" in names
        assert len(names) == len(set(names))
        assert "odczyt" not in result

    def test_variable_substituted_from_cli(self, tmp_path, simulator_data, settings_device):
        simulator_data["kroki"][1]["lokator"] = {
            "typ": "etykieta",
            "wartosc": "{zmienna}",
            "element": "Button",
        }
        config = parse_config(simulator_data, "x.json")
        code = run_flow(settings_device, config, args(zmienna="About"), tmp_path / "v")
        assert code == EXIT_OK
        assert settings_device.screen == "to_urzadzenie_1.xml"


class TestCli:
    def test_check_prints_capabilities_without_appium(self, capsys):
        code = main([str(CONFIGS / "przyklad-symulator.json"), "--sprawdz"])
        out = capsys.readouterr().out
        assert code == EXIT_OK
        assert '"appium:deviceName": "iPhone 17"' in out
        assert "appium:udid" not in out

    def test_invalid_config_returns_error_with_details(self, capsys):
        code = main([str(CONFIGS / "szablon-urzadzenie.json"), "--sprawdz"])
        err = capsys.readouterr().err
        assert code == EXIT_ERROR
        assert "urzadzenie.udid: brak wartości" in err

    def test_list_mode_requires_list_section(self, tmp_path, simulator_data, capsys):
        file = tmp_path / "bez_listy.json"
        file.write_text(json.dumps(simulator_data), encoding="utf-8")
        assert main([str(file), "--lista"]) == EXIT_ERROR
        assert 'nie ma sekcji "lista"' in capsys.readouterr().err

    def test_variable_step_requires_value(self, tmp_path, simulator_data, capsys):
        simulator_data["kroki"][1]["lokator"] = {"typ": "etykieta", "wartosc": "{zmienna}"}
        file = tmp_path / "zmienna.json"
        file.write_text(json.dumps(simulator_data), encoding="utf-8")
        assert main([str(file)]) == EXIT_ERROR
        assert "--zmienna" in capsys.readouterr().err


def test_version_banner(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out == (
        'iOS Flow Runner 1.0 "Pierwsza Kromka"\n'
        "Non-vegetarian build, sponsored by chlebek z szynką\n"
    )
