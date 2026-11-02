"""A running autorepeat control survives a transient invalid input, but not a lasting one."""

import time

import pytest

from custom_components.solax_modbus.const import AUTOREPEAT_INVALID_INPUT_GRACE, BUTTONREPEAT_LOOP, BUTTONREPEAT_POST

from .test_vpp_poll_cadence import prime, setup_vpp

KEY = "powercontrolmode8_trigger"


@pytest.fixture(autouse=True)
def real_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undo the suite-wide immediate stop and use the shipped grace window."""
    monkeypatch.setattr("custom_components.solax_modbus.AUTOREPEAT_INVALID_INPUT_GRACE", AUTOREPEAT_INVALID_INPUT_GRACE)


@pytest.mark.asyncio
async def test_transient_invalid_input_holds_running_control() -> None:
    hub, power, settings, values, function = setup_vpp()
    await prime(hub, power, settings)
    await hub._refresh_interval_group_once(power)
    calls = function.call_count
    writes = hub.async_write_registers_multi.await_count
    held = hub.async_write_registers_multi.call_args.kwargs["payload"]
    values["meter_1_measured_power"] = None
    await hub._refresh_interval_group_once(power)
    assert function.call_count == calls  # nothing is recomputed from missing data
    assert hub.data["_repeatUntil"][KEY] > time.time()
    assert hub.data["remotecontrol_current_pushmode_power"] == 210
    # The last command is replayed as a keepalive, and no Disabled write ends the control.
    assert hub.async_write_registers_multi.await_count == writes + 1
    assert hub.async_write_registers_multi.call_args.kwargs["payload"] == held
    assert KEY in hub._autorepeat_in_grace


@pytest.mark.asyncio
async def test_control_resumes_when_input_recovers() -> None:
    hub, power, settings, values, function = setup_vpp()
    await prime(hub, power, settings)
    await hub._refresh_interval_group_once(power)
    good = values["meter_1_measured_power"]
    values["meter_1_measured_power"] = None
    await hub._refresh_interval_group_once(power)
    assert KEY in hub._autorepeat_in_grace
    values["meter_1_measured_power"] = good
    await hub._refresh_interval_group_once(power)
    assert KEY not in hub._autorepeat_in_grace
    assert function.call_args.args[0] == BUTTONREPEAT_LOOP
    assert hub.data["_repeatUntil"][KEY] > time.time()


@pytest.mark.asyncio
async def test_lasting_invalid_input_stops_after_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    hub, power, settings, values, function = setup_vpp()
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    await prime(hub, power, settings)
    await hub._refresh_interval_group_once(power)
    values["meter_1_measured_power"] = None
    now[0] += AUTOREPEAT_INVALID_INPUT_GRACE - 1
    await hub._refresh_interval_group_once(power)
    assert function.call_args.args[0] != BUTTONREPEAT_POST
    assert hub.data["_repeatUntil"][KEY] > 0
    now[0] += 2
    await hub._refresh_interval_group_once(power)
    assert function.call_args.args[0] == BUTTONREPEAT_POST
    assert hub.data["_repeatUntil"][KEY] == 0
    assert hub.data["remotecontrol_current_pushmode_power"] is None
    assert hub.async_write_registers_multi.call_args.kwargs["payload"] == [("remotecontrol_power_control_mode", "Disabled")]
    assert KEY not in hub._autorepeat_inputs_ok_at
    assert KEY not in hub._autorepeat_in_grace


@pytest.mark.asyncio
async def test_zero_grace_restores_immediate_stop(monkeypatch: pytest.MonkeyPatch, real_grace: None) -> None:
    monkeypatch.setattr("custom_components.solax_modbus.AUTOREPEAT_INVALID_INPUT_GRACE", 0.0)
    hub, power, settings, values, function = setup_vpp()
    await prime(hub, power, settings)
    await hub._refresh_interval_group_once(power)
    values["meter_1_measured_power"] = None
    await hub._refresh_interval_group_once(power)
    assert function.call_args.args[0] == BUTTONREPEAT_POST
    assert hub.data["_repeatUntil"][KEY] == 0
