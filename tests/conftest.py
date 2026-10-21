"""Wspólne narzędzia testów: wczytywanie fikstur i atrapa urządzenia.

Atrapa przechodzi między zapisanymi ekranami po kliknięciu elementu,
więc da się sprawdzić cały przebieg bez Appium, symulatora i telefonu.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from ios_flow.extract import ElementInfo, parse_tree
from ios_flow.locators import LocatorKind, label_matches, short_element_type
from ios_flow.navigate import ElementNotFound

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def element_matches(element: ElementInfo, locator: Any) -> bool:
    """Lokalna ocena lokatorów ``id`` i ``etykieta`` — ta sama semantyka co predykat."""
    if locator.element_type and element.element_type != short_element_type(locator.element_type):
        return False
    if locator.kind is LocatorKind.ID:
        return element.name == locator.value
    if locator.kind is LocatorKind.LABEL:
        return label_matches(
            element.label, locator.value, locator.state_prefixes, locator.allow_suffix
        )
    raise NotImplementedError(f"Atrapa nie ocenia lokatorów typu {locator.kind}")


class FakeElement:
    def __init__(self, device: FakeDevice, info: ElementInfo) -> None:
        self.device = device
        self.info = info

    def click(self) -> None:
        self.device.clicks.append(self.info.name or self.info.label or "")
        target = self.device.transitions.get((self.device.screen, self.info.name))
        if target is not None:
            self.device.screen = target


class FakeDevice:
    """Atrapa sesji Appium: ekrany to fikstury XML, kliknięcia zmieniają ekran."""

    def __init__(
        self,
        start: str,
        transitions: dict[tuple[str, str | None], str] | None = None,
        scroll_pages: list[str] | None = None,
    ) -> None:
        self.start = start
        self.screen = start
        self.transitions = transitions or {}
        self.scroll_pages = scroll_pages or []
        self.clicks: list[str] = []
        self.scrolls = 0
        self.scroll_calls = 0
        self.restarts = 0
        self.screenshots: list[Path] = []
        self.closed = False

    def page_source(self) -> str:
        return load_fixture(self.screen)

    def find(self, locator: Any, timeout_s: float) -> FakeElement:
        for element in parse_tree(self.page_source()):
            if element_matches(element, locator):
                return FakeElement(self, element)
        raise ElementNotFound(locator.describe())

    def attribute(self, element: FakeElement, name: str) -> str | None:
        return getattr(element.info, name, None)

    def scroll_down(self) -> bool:
        self.scroll_calls += 1
        if self.scrolls >= len(self.scroll_pages):
            return True  # jak iOS: przewinięcie na końcu listy nie zgłasza błędu
        self.screen = self.scroll_pages[self.scrolls]
        self.scrolls += 1
        return True

    def restart_app(self) -> None:
        self.restarts += 1
        self.screen = self.start

    def screenshot(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG atrapa")
        self.screenshots.append(path)
        return path

    def quit(self) -> None:
        self.closed = True


SETTINGS_TRANSITIONS: dict[tuple[str, str | None], str] = {
    ("ustawienia_glowny.xml", "com.apple.settings.general"): "ogolne.xml",
    ("ogolne.xml", "com.apple.settings.general.about"): "to_urzadzenie_1.xml",
}

SIMULATOR_CONFIG: dict[str, Any] = {
    "nazwa": "Test",
    "tryb": "symulator",
    "bundle_id": "com.apple.Preferences",
    "symulator": {"nazwa_urzadzenia": "iPhone 17", "wersja_ios": "27.0"},
    "kroki": [
        {
            "opis": "Ogólne",
            "lokator": {"typ": "id", "wartosc": "com.apple.settings.general", "element": "Button"},
        },
        {
            "opis": "To urządzenie",
            "lokator": {
                "typ": "id",
                "wartosc": "com.apple.settings.general.about",
                "element": "Button",
            },
        },
    ],
    "odczyt": {
        "wersja_systemu": {
            "lokator": {"typ": "id", "wartosc": "SW_VERSION_SPECIFIER", "element": "Button"},
            "wzorzec": "^[^,]+,\\s*(?P<wartosc>.+)$",
        },
    },
}

DEVICE_CONFIG: dict[str, Any] = {
    "tryb": "urzadzenie",
    "bundle_id": "com.example.app",
    "urzadzenie": {
        "udid": "TEST-UDID-0001",
        "team_id": "ABCDE12345",
        "signing_id": "Apple Development",
        "wda_bundle_id": "com.example.wda",
    },
}


@pytest.fixture
def simulator_data() -> dict[str, Any]:
    return copy.deepcopy(SIMULATOR_CONFIG)


@pytest.fixture
def device_data() -> dict[str, Any]:
    return copy.deepcopy(DEVICE_CONFIG)


@pytest.fixture
def settings_device() -> FakeDevice:
    return FakeDevice("ustawienia_glowny.xml", dict(SETTINGS_TRANSITIONS))
