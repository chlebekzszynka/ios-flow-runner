"""Odczyt danych z drzewa elementów iOS (XML zwracany przez ``page_source``).

Wszystko tutaj działa na tekście i XML-u, bez połączenia z Appium,
więc da się to testować na zapisanych drzewach z ``tests/fixtures``.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ios_flow.locators import LABEL_SEPARATOR, short_element_type

# Nazwa grupy w wyrażeniu regularnym, z której bierzemy wartość.
VALUE_GROUP = "wartosc"
# Nazwa grupy z nazwą pozycji listy.
NAME_GROUP = "nazwa"

# Ile kolejnych przewinięć bez nowych pozycji oznacza koniec listy.
IDLE_SCROLLS_LIMIT = 2


class TreeParseError(ValueError):
    """Drzewo elementów nie jest poprawnym XML-em."""


@dataclass(frozen=True)
class ElementInfo:
    """Jeden element z drzewa, tylko atrybuty potrzebne do lokatorów."""

    element_type: str
    name: str | None
    label: str | None
    value: str | None
    visible: bool

    @property
    def text(self) -> str | None:
        """Tekst elementu: value, a gdy go brak — label, potem name."""
        return self.value or self.label or self.name


def parse_tree(xml: str) -> list[ElementInfo]:
    """Zamienia XML z ``page_source`` na płaską listę elementów (w kolejności drzewa)."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        raise TreeParseError(f"Drzewo elementów nie jest poprawnym XML-em: {error}") from error

    elements: list[ElementInfo] = []
    for node in root.iter():
        if not node.tag.startswith("XCUIElementType"):
            continue
        elements.append(
            ElementInfo(
                element_type=short_element_type(node.tag),
                name=node.get("name"),
                label=node.get("label"),
                value=node.get("value"),
                visible=node.get("visible") == "true",
            )
        )
    return elements


def parse_value(text: str | None, pattern: str | re.Pattern[str] | None) -> str | None:
    """Wyciąga wartość z tekstu elementu wyrażeniem regularnym.

    Kolejność: grupa ``(?P<wartosc>...)``, pierwsza grupa, całe dopasowanie.
    Bez wzorca zwraca cały tekst. Pusty wynik to ``None``.
    """
    if text is None:
        return None
    if pattern is None:
        return text.strip() or None

    regex = re.compile(pattern) if isinstance(pattern, str) else pattern
    match = regex.search(text)
    if match is None:
        return None
    if VALUE_GROUP in regex.groupindex:
        found = match.group(VALUE_GROUP)
    elif regex.groups:
        found = match.group(1)
    else:
        found = match.group(0)
    if found is None:
        return None
    return found.strip() or None


def strip_state_prefix(label: str, prefixes: Iterable[str]) -> tuple[str, str | None]:
    """Usuwa przedrostek stanu z etykiety.

    ``"Selected, English"`` z przedrostkiem ``Selected`` -> ``("English", "Selected")``.
    Przedrostek musi być pełnym członem przed separatorem: ``"Selectedness"`` zostaje.
    """
    for prefix in prefixes:
        head = prefix + LABEL_SEPARATOR
        if label.startswith(head):
            return label[len(head) :].strip(), prefix
    return label, None


def is_screen_reader_helper(label: str | None, phrases: Iterable[str]) -> bool:
    """Czy element jest tylko podpowiedzią dla czytnika ekranu (VoiceOver)."""
    if not label:
        return False
    lowered = label.casefold()
    return any(phrase.casefold() in lowered for phrase in phrases)


def visible_texts(xml: str, limit: int = 160) -> list[str]:
    """Teksty widocznych elementów StaticText, bez powtórzeń — do diagnostyki."""
    texts: list[str] = []
    for element in parse_tree(xml):
        if element.element_type != "StaticText" or not element.visible:
            continue
        text = (element.text or "").strip()
        if not text:
            continue
        if len(text) > limit:
            text = text[: limit - 1] + "…"
        if text not in texts:
            texts.append(text)
    return texts


@dataclass(frozen=True)
class ListRule:
    """Jak rozpoznać pozycje listy na ekranie (sekcja ``lista`` w konfiguracji)."""

    element_type: str = "Button"
    element_name: str | None = None
    pattern: str | None = None
    require_match: bool = False
    state_prefixes: tuple[str, ...] = ()
    helper_phrases: tuple[str, ...] = ()
    only_visible: bool = True


@dataclass(frozen=True)
class ListItem:
    """Pozycja listy odczytana z ekranu."""

    name: str
    value: str | None = None
    state: str | None = None


def items_on_screen(xml: str, rule: ListRule) -> list[ListItem]:
    """Pozycje listy widoczne w jednym zrzucie drzewa."""
    regex = re.compile(rule.pattern) if rule.pattern else None
    wanted_type = short_element_type(rule.element_type)
    items: list[ListItem] = []

    for element in parse_tree(xml):
        if element.element_type != wanted_type:
            continue
        if rule.element_name is not None and element.name != rule.element_name:
            continue
        if rule.only_visible and not element.visible:
            continue
        label = (element.label or "").strip()
        if not label or is_screen_reader_helper(label, rule.helper_phrases):
            continue

        # Najpierw stan, potem wzorzec: "Selected, English, Primary" -> "English, Primary".
        label, state = strip_state_prefix(label, rule.state_prefixes)
        name, value = label, None
        if regex is not None:
            match = regex.search(label)
            if match is None:
                if rule.require_match:
                    continue
            else:
                if NAME_GROUP in regex.groupindex and match.group(NAME_GROUP):
                    name = match.group(NAME_GROUP).strip()
                if VALUE_GROUP in regex.groupindex and match.group(VALUE_GROUP):
                    value = match.group(VALUE_GROUP).strip()
        if name:
            items.append(ListItem(name=name, value=value, state=state))
    return items


def merge_new(collected: dict[str, ListItem], items: Iterable[ListItem]) -> int:
    """Dokłada do ``collected`` pozycje, których jeszcze nie było. Zwraca ich liczbę.

    Kluczem jest nazwa; kolejność pierwszego wystąpienia zostaje zachowana.
    """
    added = 0
    for item in items:
        if item.name not in collected:
            collected[item.name] = item
            added += 1
    return added


def collect_list(
    read_screen: Callable[[], str],
    scroll: Callable[[], bool],
    rule: ListRule,
    max_scrolls: int = 20,
    log: Callable[[str], None] = lambda _message: None,
) -> list[ListItem]:
    """Zbiera całą listę, przewijając ekran, aż przestaną pojawiać się nowe pozycje.

    ``read_screen`` zwraca aktualny XML, ``scroll`` przewija w dół
    i zwraca ``False``, gdy przewinąć się nie da.
    """
    collected: dict[str, ListItem] = {}
    idle = 0
    for number in range(1, max_scrolls + 2):
        added = merge_new(collected, items_on_screen(read_screen(), rule))
        log(f"Ekran {number}: nowych pozycji {added}, łącznie {len(collected)}")
        idle = idle + 1 if added == 0 else 0
        if idle >= IDLE_SCROLLS_LIMIT or number > max_scrolls:
            break
        if not scroll():
            break
    return list(collected.values())
