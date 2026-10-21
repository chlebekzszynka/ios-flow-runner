"""Wykonywanie kroków nawigacji opisanych w konfiguracji.

Moduł nie importuje Appium: element szuka obiekt zgodny z :class:`Finder`.
W przebiegu to sesja Appium, w testach — atrapa.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol

from ios_flow.locators import Locator


class ElementNotFound(Exception):
    """Element nie pojawił się na ekranie w zadanym czasie."""


class NavigationError(RuntimeError):
    """Obowiązkowy krok nawigacji się nie powiódł."""


class Clickable(Protocol):
    def click(self) -> None: ...


class Finder(Protocol):
    def find(self, locator: Locator, timeout_s: float) -> Clickable:
        """Zwraca element albo rzuca :class:`ElementNotFound`."""
        ...


@dataclass(frozen=True)
class Step:
    """Jeden krok nawigacji: znajdź element i dotknij go."""

    description: str
    locator: Locator
    wait_s: float = 10.0
    pause_s: float = 1.0
    optional: bool = False

    @property
    def is_variable(self) -> bool:
        return self.locator.has_placeholder

    def substitute(self, text: str) -> Step:
        if not self.is_variable:
            return self
        return replace(self, locator=self.locator.substitute(text))


class StepStatus(StrEnum):
    CLICKED = "kliknięty"
    SKIPPED = "pominięty"


@dataclass(frozen=True)
class StepResult:
    description: str
    status: StepStatus


def split_at_variable(steps: Sequence[Step]) -> tuple[list[Step], Step | None, list[Step]]:
    """Dzieli kroki na: przed krokiem zmiennym, sam krok zmienny, po nim.

    Bez kroku zmiennego: ``(wszystkie, None, [])``.
    """
    for index, step in enumerate(steps):
        if step.is_variable:
            return list(steps[:index]), step, list(steps[index + 1 :])
    return list(steps), None, []


def substitute_all(steps: Sequence[Step], text: str) -> list[Step]:
    """Wstawia ``text`` w miejsce {zmienna} we wszystkich krokach."""
    return [step.substitute(text) for step in steps]


def run_steps(
    finder: Finder,
    steps: Sequence[Step],
    log: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
) -> list[StepResult]:
    """Wykonuje kroki po kolei.

    Brak elementu w kroku opcjonalnym pomija krok. Brak elementu
    w kroku obowiązkowym przerywa przebieg wyjątkiem :class:`NavigationError`.
    """
    results: list[StepResult] = []
    total = len(steps)
    for number, step in enumerate(steps, start=1):
        log(f"Krok {number}/{total}: {step.description}")
        try:
            element = finder.find(step.locator, step.wait_s)
        except ElementNotFound:
            if step.optional:
                log("  pominięty: elementu nie ma na ekranie (krok opcjonalny)")
                results.append(StepResult(step.description, StepStatus.SKIPPED))
                continue
            raise NavigationError(
                f"Krok {number}/{total} „{step.description}”: element nie pojawił się "
                f"w ciągu {step.wait_s:g} s.\n"
                f"  Lokator: {step.locator.describe()}\n"
                "  Co zrobić: sprawdź na ekranie, czy poprzedni krok doprowadził tam, "
                "gdzie trzeba, i porównaj atrybuty elementu poleceniem "
                "python -m ios_flow.inspect <konfiguracja>. Jeśli element bywa "
                'nieobecny z założenia, oznacz krok jako "opcjonalny": true.'
            ) from None
        element.click()
        results.append(StepResult(step.description, StepStatus.CLICKED))
        sleep(step.pause_s)
    return results
