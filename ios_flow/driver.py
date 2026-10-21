"""Sesja Appium: capabilities dla obu trybów i cienka nakładka na sterownik.

:func:`build_capabilities` to czysta funkcja — testy sprawdzają ją bez Appium.
Biblioteka Appium jest importowana dopiero w :func:`connect`.
"""

from __future__ import annotations

import contextlib
import time
from pathlib import Path
from typing import Any

from ios_flow.config import Config, Mode
from ios_flow.locators import Locator, to_query
from ios_flow.navigate import ElementNotFound

APPIUM_PREFIX = "appium:"


class SessionError(RuntimeError):
    """Nie udało się otworzyć sesji albo połączenie z Appium zostało zerwane."""


def build_capabilities(config: Config) -> dict[str, Any]:
    """Capabilities W3C dla trybu z konfiguracji."""
    session = config.session
    caps: dict[str, Any] = {
        "platformName": "iOS",
        "appium:automationName": "XCUITest",
        "appium:bundleId": config.bundle_id,
        "appium:noReset": True,
        # Aplikacje z animacjami nigdy nie osiągają stanu wyciszenia;
        # z true sesja potrafi czekać w nieskończoność na starcie i przy każdej akcji.
        "appium:waitForQuiescence": False,
        "appium:snapshotMaxDepth": session.snapshot_max_depth,
        "appium:newCommandTimeout": session.new_command_timeout,
    }

    if config.mode is Mode.SIMULATOR:
        assert config.simulator is not None
        caps["appium:deviceName"] = config.simulator.device_name
        caps["appium:platformVersion"] = config.simulator.platform_version
    else:
        assert config.device is not None
        caps["appium:udid"] = config.device.udid
        caps["appium:xcodeOrgId"] = config.device.team_id
        caps["appium:xcodeSigningId"] = config.device.signing_id
        caps["appium:updatedWDABundleId"] = config.device.wda_bundle_id

    for key, value in session.extra_capabilities.items():
        name = key if key == "platformName" or ":" in key else APPIUM_PREFIX + key
        caps[name] = value
    return caps


def connection_tips(config: Config) -> str:
    """Co sprawdzić, gdy sesja nie wstaje — zależnie od trybu."""
    tips = [
        f"czy serwer Appium działa pod adresem {config.server_url} (komenda: appium)",
        "czy driver jest zainstalowany (appium driver list --installed pokazuje xcuitest)",
    ]
    if config.mode is Mode.SIMULATOR:
        assert config.simulator is not None
        tips.append(
            f'czy symulator "{config.simulator.device_name}" z iOS '
            f"{config.simulator.platform_version} istnieje (xcrun simctl list devices available)"
        )
    else:
        tips += [
            "czy telefon jest podłączony, odblokowany i ufa temu Macowi (idevice_id -l)",
            "czy WebDriverAgent nie działa równolegle z Xcode (dwie instancje walczą o port 8100)",
            'pełny log budowania WDA: dodaj "showXcodeLog": true w sesja.dodatkowe_capabilities',
        ]
    return "Sprawdź:\n" + "\n".join(f"  - {tip}" for tip in tips)


class AppiumSession:
    """Otwarta sesja. Spełnia protokół ``Finder`` z :mod:`ios_flow.navigate`."""

    def __init__(self, driver: Any, config: Config) -> None:
        self.driver = driver
        self.config = config

    def find(self, locator: Locator, timeout_s: float) -> Any:
        from selenium.common.exceptions import TimeoutException
        from selenium.webdriver.support.ui import WebDriverWait

        strategy, selector = to_query(locator)
        try:
            return WebDriverWait(self.driver, timeout_s).until(
                lambda driver: driver.find_element(strategy, selector)
            )
        except TimeoutException:
            raise ElementNotFound(locator.describe()) from None

    def attribute(self, element: Any, name: str) -> str | None:
        from selenium.common.exceptions import WebDriverException

        try:
            return element.get_attribute(name)
        except WebDriverException:
            return None

    def page_source(self) -> str:
        return self.driver.page_source

    def scroll_down(self) -> bool:
        from selenium.common.exceptions import WebDriverException

        try:
            self.driver.execute_script("mobile: scroll", {"direction": "down"})
        except WebDriverException:
            return False
        time.sleep(1.0)
        return True

    def restart_app(self) -> None:
        """Zamyka i otwiera aplikację, żeby każdy przebieg zaczynał się tak samo."""
        self.driver.terminate_app(self.config.bundle_id)
        time.sleep(1.0)
        self.driver.activate_app(self.config.bundle_id)
        time.sleep(2.0)

    def screenshot(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.driver.get_screenshot_as_file(str(path))
        return path

    def quit(self) -> None:
        from selenium.common.exceptions import WebDriverException

        with contextlib.suppress(WebDriverException):
            self.driver.quit()


def connect(config: Config, extra: dict[str, Any] | None = None) -> AppiumSession:
    """Otwiera sesję Appium. Rzuca :class:`SessionError` z podpowiedziami."""
    try:
        from appium import webdriver
        from appium.options.ios import XCUITestOptions
        from selenium.common.exceptions import WebDriverException
        from urllib3.exceptions import HTTPError as ConnectionProblem
    except ImportError as error:
        raise SessionError(
            "Brak biblioteki Appium. Zainstaluj zależności: pip install -r requirements.txt"
        ) from error

    caps = build_capabilities(config)
    caps.update(extra or {})
    options = XCUITestOptions().load_capabilities(caps)
    try:
        driver = webdriver.Remote(config.server_url, options=options)
    except WebDriverException as error:
        message = (error.msg or str(error)).strip()
        raise SessionError(
            f"Nie udało się otworzyć sesji Appium: {message}\n{connection_tips(config)}"
        ) from error
    except (OSError, ConnectionProblem) as error:
        raise SessionError(
            f"Brak połączenia z serwerem Appium ({error}).\n{connection_tips(config)}"
        ) from error
    return AppiumSession(driver, config)
