"""Lokatory iOS: opis z konfiguracji -> zapytanie dla Appium.

Zasada: dopasowanie etykiet i nazw jest zawsze dokładne (``==``), nigdy
``CONTAINS``. Etykieta ``20%`` nie może trafić w ``20%HM`` ani ``20%VM``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

ELEMENT_TYPE_PREFIX = "XCUIElementType"

# Separator, którym iOS skleja części etykiety, np. "iOS Version, 27.0"
# albo przedrostek stanu: "Selected, English".
LABEL_SEPARATOR = ", "

# Znacznik miejsca, w które wstawia się wartość podaną z wiersza poleceń.
PLACEHOLDER = "{zmienna}"

# Strategie wyszukiwania Appium (te same napisy co w AppiumBy).
STRATEGY_PREDICATE = "-ios predicate string"
STRATEGY_CLASS_CHAIN = "-ios class chain"
STRATEGY_XPATH = "xpath"


class LocatorKind(StrEnum):
    """Typ lokatora w konfiguracji (pole ``lokator.typ``)."""

    ID = "id"
    LABEL = "etykieta"
    PREDICATE = "predykat"
    CLASS_CHAIN = "class_chain"
    XPATH = "xpath"


# Typy, w których wolno użyć {zmienna}: tu umiemy poprawnie zabezpieczyć wartość.
KINDS_WITH_PLACEHOLDER = (LocatorKind.ID, LocatorKind.LABEL, LocatorKind.PREDICATE)


@dataclass(frozen=True)
class Locator:
    """Lokator elementu opisany w konfiguracji."""

    kind: LocatorKind
    value: str
    element_type: str | None = None
    state_prefixes: tuple[str, ...] = ()
    allow_suffix: bool = False

    @property
    def has_placeholder(self) -> bool:
        return PLACEHOLDER in self.value

    def substitute(self, text: str) -> Locator:
        """Wstawia ``text`` w miejsce {zmienna}.

        Dla surowego predykatu wartość jest od razu zabezpieczana, bo trafia
        do wnętrza apostrofów. Dla ``id`` i ``etykieta`` zabezpieczenie
        następuje przy budowaniu predykatu.
        """
        if not self.has_placeholder:
            return self
        inserted = escape_literal(text) if self.kind is LocatorKind.PREDICATE else text
        return replace(self, value=self.value.replace(PLACEHOLDER, inserted))

    def describe(self) -> str:
        """Krótki opis do komunikatów diagnostycznych."""
        strategy, selector = to_query(self)
        return f"{self.kind.value} → {strategy}: {selector}"


def escape_literal(text: str) -> str:
    """Zabezpiecza tekst do wstawienia między apostrofy w predykacie iOS."""
    return text.replace("\\", "\\\\").replace("'", "\\'")


def full_element_type(element_type: str) -> str:
    """``Button`` -> ``XCUIElementTypeButton``; pełna nazwa zostaje bez zmian."""
    if element_type.startswith(ELEMENT_TYPE_PREFIX):
        return element_type
    return ELEMENT_TYPE_PREFIX + element_type


def short_element_type(element_type: str) -> str:
    """``XCUIElementTypeButton`` -> ``Button``."""
    return element_type.removeprefix(ELEMENT_TYPE_PREFIX)


def label_variants(text: str, state_prefixes: tuple[str, ...] = ()) -> list[str]:
    """Etykieta bez stanu oraz z każdym z przedrostków stanu."""
    return [text] + [f"{prefix}{LABEL_SEPARATOR}{text}" for prefix in state_prefixes]


def _with_type(predicate: str, element_type: str | None) -> str:
    if not element_type:
        return predicate
    return f"type == '{full_element_type(element_type)}' AND {predicate}"


def label_predicate(
    text: str,
    element_type: str | None = None,
    state_prefixes: tuple[str, ...] = (),
    allow_suffix: bool = False,
) -> str:
    """Predykat dokładnie dopasowujący etykietę.

    ``allow_suffix`` dopuszcza dalszą część etykiety po separatorze
    (``Name`` trafi w ``Name, iPhone``), ale nadal nie trafi w ``NameX``.
    """
    clauses: list[str] = []
    for variant in label_variants(text, state_prefixes):
        literal = escape_literal(variant)
        clauses.append(f"label == '{literal}'")
        if allow_suffix:
            clauses.append(f"label BEGINSWITH '{literal}{LABEL_SEPARATOR}'")
    predicate = " OR ".join(clauses)
    if len(clauses) > 1:
        predicate = f"({predicate})"
    return _with_type(predicate, element_type)


def label_matches(
    label: str | None,
    text: str,
    state_prefixes: tuple[str, ...] = (),
    allow_suffix: bool = False,
) -> bool:
    """Lokalny odpowiednik :func:`label_predicate` — ta sama semantyka w Pythonie."""
    if label is None:
        return False
    for variant in label_variants(text, state_prefixes):
        if label == variant:
            return True
        if allow_suffix and label.startswith(variant + LABEL_SEPARATOR):
            return True
    return False


def name_predicate(name: str, element_type: str | None = None) -> str:
    """Predykat dokładnie dopasowujący identyfikator (atrybut ``name``)."""
    return _with_type(f"name == '{escape_literal(name)}'", element_type)


def to_query(locator: Locator) -> tuple[str, str]:
    """Zamienia lokator na parę (strategia Appium, selektor)."""
    match locator.kind:
        case LocatorKind.ID:
            return STRATEGY_PREDICATE, name_predicate(locator.value, locator.element_type)
        case LocatorKind.LABEL:
            return STRATEGY_PREDICATE, label_predicate(
                locator.value,
                locator.element_type,
                locator.state_prefixes,
                locator.allow_suffix,
            )
        case LocatorKind.PREDICATE:
            if not locator.element_type:
                return STRATEGY_PREDICATE, locator.value
            # Nawias chroni surowy predykat z OR przed złym wiązaniem z AND.
            return STRATEGY_PREDICATE, _with_type(f"({locator.value})", locator.element_type)
        case LocatorKind.CLASS_CHAIN:
            return STRATEGY_CLASS_CHAIN, locator.value
        case LocatorKind.XPATH:
            return STRATEGY_XPATH, locator.value
    raise ValueError(f"Nieobsługiwany typ lokatora: {locator.kind}")
