"""Capabilities dla trybu symulatora i urządzenia — bez łączenia z Appium."""

import pytest

from ios_flow.config import parse_config
from ios_flow.driver import build_capabilities, connection_tips

DEVICE_ONLY = (
    "appium:udid",
    "appium:xcodeOrgId",
    "appium:xcodeSigningId",
    "appium:updatedWDABundleId",
)
SIMULATOR_ONLY = ("appium:deviceName", "appium:platformVersion")
COMMON = ("appium:waitForQuiescence", "appium:snapshotMaxDepth", "appium:newCommandTimeout")


@pytest.fixture
def simulator_caps(simulator_data):
    return build_capabilities(parse_config(simulator_data, "x"))


@pytest.fixture
def device_caps(device_data):
    return build_capabilities(parse_config(device_data, "x"))


class TestSimulatorMode:
    def test_has_device_name_and_version(self, simulator_caps):
        assert simulator_caps["appium:deviceName"] == "iPhone 17"
        assert simulator_caps["appium:platformVersion"] == "27.0"

    def test_has_no_signing_or_udid(self, simulator_caps):
        for key in DEVICE_ONLY:
            assert key not in simulator_caps

    def test_device_section_ignored_in_simulator_mode(self, simulator_data, device_data):
        simulator_data["urzadzenie"] = device_data["urzadzenie"]
        caps = build_capabilities(parse_config(simulator_data, "x"))
        for key in DEVICE_ONLY:
            assert key not in caps


class TestDeviceMode:
    def test_has_udid_and_signing(self, device_caps):
        assert device_caps["appium:udid"] == "TEST-UDID-0001"
        assert device_caps["appium:xcodeOrgId"] == "ABCDE12345"
        assert device_caps["appium:xcodeSigningId"] == "Apple Development"
        assert device_caps["appium:updatedWDABundleId"] == "com.example.wda"

    def test_has_no_device_name(self, device_caps):
        for key in SIMULATOR_ONLY:
            assert key not in device_caps


@pytest.mark.parametrize("caps_fixture", ["simulator_caps", "device_caps"])
class TestCommon:
    def test_common_keys_present(self, caps_fixture, request):
        caps = request.getfixturevalue(caps_fixture)
        for key in COMMON:
            assert key in caps

    def test_quiescence_disabled(self, caps_fixture, request):
        assert request.getfixturevalue(caps_fixture)["appium:waitForQuiescence"] is False

    def test_platform_and_automation(self, caps_fixture, request):
        caps = request.getfixturevalue(caps_fixture)
        assert caps["platformName"] == "iOS"
        assert caps["appium:automationName"] == "XCUITest"


class TestSessionSettings:
    def test_values_from_config(self, simulator_data):
        simulator_data["sesja"] = {"snapshot_max_depth": 70, "new_command_timeout": 900}
        caps = build_capabilities(parse_config(simulator_data, "x"))
        assert caps["appium:snapshotMaxDepth"] == 70
        assert caps["appium:newCommandTimeout"] == 900

    def test_extra_capabilities_get_prefix(self, device_data):
        device_data["sesja"] = {
            "dodatkowe_capabilities": {"showXcodeLog": True, "appium:wdaLaunchTimeout": 240000}
        }
        caps = build_capabilities(parse_config(device_data, "x"))
        assert caps["appium:showXcodeLog"] is True
        assert caps["appium:wdaLaunchTimeout"] == 240000


class TestConnectionTips:
    def test_simulator_tips_mention_simctl(self, simulator_data):
        tips = connection_tips(parse_config(simulator_data, "x"))
        assert "xcrun simctl list devices available" in tips
        assert "8100" not in tips

    def test_device_tips_mention_wda_port_and_xcode_log(self, device_data):
        tips = connection_tips(parse_config(device_data, "x"))
        assert "8100" in tips
        assert "showXcodeLog" in tips
