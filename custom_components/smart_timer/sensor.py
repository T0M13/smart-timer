from __future__ import annotations

from datetime import datetime, timedelta

import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .coordinator import SmartTimerCoordinator, signal_update

_RUNTIME_REFRESH = timedelta(seconds=60)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SmartTimerCoordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    async_add_entities([
        TimeRemainingSensor(coordinator),
        DailyRuntimeSensor(coordinator),
        NextScheduleSensor(coordinator),
    ])


class TimeRemainingSensor(SensorEntity):
    """Shows the countdown remaining on the active timer."""

    _attr_has_entity_name = True
    _attr_translation_key = "time_remaining"
    _attr_should_poll = False
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: SmartTimerCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{coordinator.slug}_time_remaining"
        self._attr_device_info = coordinator.device_info
        self.entity_id = f"sensor.{coordinator.slug}_time_remaining"
        self._unsub_interval = None

    @property
    def native_value(self) -> str:
        expiry = self._coordinator.timer_expiry
        if not expiry:
            return "idle"
        diff = expiry - dt_util.now()
        secs = max(0, int(diff.total_seconds()))
        hours = secs // 3600
        mins = (secs % 3600) // 60
        s = secs % 60
        if hours > 0:
            return f"{hours}:{mins:02d}:{s:02d}"
        return f"{mins}:{s:02d}"

    @property
    def extra_state_attributes(self) -> dict:
        return {"action": self._coordinator.timer_action}

    async def async_added_to_hass(self) -> None:
        def _start() -> None:
            if self._unsub_interval is None:
                self._unsub_interval = async_track_time_interval(
                    self.hass, self._tick, timedelta(seconds=15)
                )

        def _stop() -> None:
            if self._unsub_interval is not None:
                self._unsub_interval()
                self._unsub_interval = None

        @callback
        def _update() -> None:
            self.async_write_ha_state()
            if self._coordinator.timer_expiry:
                _start()
            else:
                _stop()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._coordinator.entity_id), _update
            )
        )
        self.async_on_remove(_stop)
        if self._coordinator.timer_expiry:
            _start()

    @callback
    def _tick(self, now: datetime) -> None:
        self.async_write_ha_state()


class DailyRuntimeSensor(SensorEntity):
    """Shows how long the device has been on today."""

    _attr_has_entity_name = True
    _attr_translation_key = "daily_runtime"
    _attr_should_poll = False
    _attr_icon = "mdi:chart-timeline-variant"

    def __init__(self, coordinator: SmartTimerCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{coordinator.slug}_daily_runtime"
        self._attr_device_info = coordinator.device_info
        self.entity_id = f"sensor.{coordinator.slug}_daily_runtime"
        self._unsub_interval = None

    @property
    def native_value(self) -> str:
        return self._coordinator.runtime_display

    @property
    def extra_state_attributes(self) -> dict:
        return {"seconds": round(self._coordinator.current_runtime_seconds)}

    async def async_added_to_hass(self) -> None:
        @callback
        def _update() -> None:
            self.async_write_ha_state()

        @callback
        def _tick(now: datetime) -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._coordinator.entity_id), _update
            )
        )
        # Periodic refresh for live runtime counter
        self._unsub_interval = async_track_time_interval(
            self.hass, _tick, _RUNTIME_REFRESH
        )
        self.async_on_remove(lambda: self._unsub_interval() if self._unsub_interval else None)


class NextScheduleSensor(SensorEntity):
    """Shows the next scheduled action time."""

    _attr_has_entity_name = True
    _attr_translation_key = "next_schedule"
    _attr_should_poll = False
    _attr_icon = "mdi:calendar-clock"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SmartTimerCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{coordinator.slug}_next_schedule"
        self._attr_device_info = coordinator.device_info
        self.entity_id = f"sensor.{coordinator.slug}_next_schedule"
        self._unsub_interval = None

    @property
    def native_value(self) -> str | None:
        next_time = self._coordinator.get_next_schedule_time()
        if not next_time:
            return "none"
        return next_time.strftime("%H:%M")

    @property
    def extra_state_attributes(self) -> dict:
        schedules = self._coordinator.schedules
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        formatted = []
        for s in schedules:
            days_str = ", ".join(day_names[int(d)] for d in s.get("days", [])) or "every day"
            formatted.append({
                "id": s["id"],
                "action": s["action"],
                "time": s["time"],
                "days": days_str,
                "enabled": s.get("enabled", True),
            })
        return {
            "schedules": formatted,
            "schedule_count": len(schedules),
            "away_mode": self._coordinator.away_enabled,
        }

    async def async_added_to_hass(self) -> None:
        @callback
        def _update() -> None:
            self.async_write_ha_state()

        @callback
        def _tick(now: datetime) -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._coordinator.entity_id), _update
            )
        )
        # Refresh every 5 minutes so "next schedule" stays current
        self._unsub_interval = async_track_time_interval(
            self.hass, _tick, timedelta(minutes=5)
        )
        self.async_on_remove(lambda: self._unsub_interval() if self._unsub_interval else None)
