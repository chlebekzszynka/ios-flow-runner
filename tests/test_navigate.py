"""Kroki nawigacji: kolejność, kroki opcjonalne, krok zmienny."""

import pytest
from conftest import FakeDevice

from ios_flow.locators import Locator, LocatorKind
from ios_flow.navigate import (
    NavigationError,
    Step,
    StepStatus,
    run_steps,
    split_at_variable,
    substitute_all,
)


def by_id(name: str, *, optional: bool = False, description: str | None = None) -> Step:
    return Step(
        description or name,
        Locator(LocatorKind.ID, name, "Button"),
        wait_s=0.1,
        pause_s=0,
        optional=optional,
    )


GENERAL = by_id("com.apple.settings.general", description="Ogólne")
ABOUT = by_id("com.apple.settings.general.about", description="To urządzenie")
VARIABLE = Step("Pozycja listy", Locator(LocatorKind.LABEL, "{zmienna}", "Button"))


def no_sleep(_seconds: float) -> None:
    pass


class TestRunSteps:
    def test_steps_reach_target_screen(self, settings_device: FakeDevice):
        results = run_steps(settings_device, [GENERAL, ABOUT], log=lambda _m: None, sleep=no_sleep)
        assert settings_device.screen == "to_urzadzenie_1.xml"
        assert [r.status for r in results] == [StepStatus.CLICKED, StepStatus.CLICKED]

    def test_missing_optional_step_is_skipped(self, settings_device: FakeDevice):
        popup = by_id("com.example.dismissPopup", optional=True, description="Zamknij okienko")
        logs: list[str] = []
        results = run_steps(
            settings_device, [popup, GENERAL, ABOUT], log=logs.append, sleep=no_sleep
        )
        assert settings_device.screen == "to_urzadzenie_1.xml"
        assert results[0].status is StepStatus.SKIPPED
        assert results[1].status is StepStatus.CLICKED
        assert any("pominięty" in line for line in logs)

    def test_present_optional_step_is_clicked(self, settings_device: FakeDevice):
        optional_general = by_id("com.apple.settings.general", optional=True)
        results = run_steps(
            settings_device, [optional_general], log=lambda _m: None, sleep=no_sleep
        )
        assert results[0].status is StepStatus.CLICKED
        assert settings_device.screen == "ogolne.xml"

    def test_missing_required_step_stops_run_with_hint(self, settings_device: FakeDevice):
        missing = by_id("com.example.nothing", description="Nieistniejący przycisk")
        with pytest.raises(NavigationError) as error:
            run_steps(
                settings_device, [GENERAL, missing, ABOUT], log=lambda _m: None, sleep=no_sleep
            )
        message = str(error.value)
        assert "Krok 2/3" in message
        assert "Nieistniejący przycisk" in message
        assert "name == 'com.example.nothing'" in message
        assert "python -m ios_flow.inspect" in message
        assert "opcjonalny" in message
        # Trzeci krok nie został wykonany.
        assert settings_device.screen == "ogolne.xml"

    def test_pause_after_each_click(self, settings_device: FakeDevice):
        pauses: list[float] = []
        step = Step("Ogólne", GENERAL.locator, pause_s=1.5)
        run_steps(settings_device, [step], log=lambda _m: None, sleep=pauses.append)
        assert pauses == [1.5]


class TestSplitAtVariable:
    def test_split_before_and_after(self):
        before, variable, after = split_at_variable([GENERAL, VARIABLE, ABOUT])
        assert before == [GENERAL]
        assert variable is VARIABLE
        assert after == [ABOUT]

    def test_variable_first(self):
        before, variable, after = split_at_variable([VARIABLE, ABOUT])
        assert before == []
        assert variable is VARIABLE
        assert after == [ABOUT]

    def test_variable_last(self):
        before, variable, after = split_at_variable([GENERAL, ABOUT, VARIABLE])
        assert before == [GENERAL, ABOUT]
        assert after == []

    def test_without_variable_everything_is_before(self):
        before, variable, after = split_at_variable([GENERAL, ABOUT])
        assert before == [GENERAL, ABOUT]
        assert variable is None
        assert after == []

    def test_substitution_fills_only_variable_step(self):
        steps = substitute_all([GENERAL, VARIABLE], "Keyboard")
        assert steps[0] is GENERAL
        assert steps[1].locator.value == "Keyboard"
        assert not steps[1].is_variable

    def test_substituted_step_runs_on_fixture(self, settings_device: FakeDevice):
        variable = Step("Pozycja", Locator(LocatorKind.LABEL, "{zmienna}", "Button"), pause_s=0)
        steps = substitute_all([GENERAL, variable], "About")
        run_steps(settings_device, steps, log=lambda _m: None, sleep=no_sleep)
        assert settings_device.screen == "to_urzadzenie_1.xml"
