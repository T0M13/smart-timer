from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import datetime, timedelta

import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Context, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_time_change,
    async_track_time_interval,
)

from .const import ACTION_TURN_OFF, ACTION_TURN_ON, DOMAIN

_LOGGER = logging.getLogger(__name__)

_INACTIVE_STATES = frozenset({
    STATE_OFF, STATE_UNAVAILABLE, STATE_UNKNOWN,
    "closed", "closing", "idle", "docked", "standby",
})

RECOVERY_GRACE_SECONDS = 15


def signal_update(entity_id: str) -> str:
    return f"{DOMAIN}_update_{entity_id}"


def _is_active(state_obj) -> bool:
    return bool(state_obj and state_obj.state not in _INACTIVE_STATES)


async def _execute_action(hass: HomeAssistant, entity_id: str, action: str) -> None:
    domain = entity_id.split(".")[0]
    if action == ACTION_TURN_ON:
        if domain == "cover":
            await hass.services.async_call("cover", "open_cover", {"entity_id": entity_id}, context=Context())
        else:
            await hass.services.async_call("homeassistant", "turn_on", {"entity_id": entity_id}, context=Context())
    else:
        if domain == "cover":
            await hass.services.async_call("cover", "close_cover", {"entity_id": entity_id}, context=Context())
        elif domain == "vacuum":
            await hass.services.async_call("vacuum", "return_to_base", {"entity_id": entity_id}, context=Context())
        else:
            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": entity_id}, context=Context())


class SmartTimerCoordinator:
    """Manages timer, schedule, away mode, and runtime tracking for one device."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, entity_id: str) -> None:
        self.hass = hass
        self.entry = entry
        self.entity_id = entity_id
        self.slug = entity_id.split(".")[-1]

        self.device_info: DeviceInfo | None = None

        # Recovery flag
        self.is_recovering = True
        self.recover_task: asyncio.Task | None = None

        # Timer state
        self.timer_action: str | None = None  # "turn_on" or "turn_off"
        self.timer_expiry: datetime | None = None
        self._unsub_timer: CALLBACK_TYPE | None = None

        # Auto-off
        self.auto_off_minutes: float = 0.0
        self.number_entity = None

        # Runtime tracking
        self.runtime_seconds_today: float = 0.0
        self.runtime_date: str | None = None
        self.last_on_time: datetime | None = None
        self._unsub_runtime_tick: CALLBACK_TYPE | None = None

        # Schedules
        self.schedules: list[dict] = []
        self._unsub_schedules: list[CALLBACK_TYPE] = []

        # Away mode
        self.away_enabled: bool = False
        self.away_start: str = "18:00"
        self.away_end: str = "23:00"
        self.away_min_on: int = 10
        self.away_max_on: int = 45
        self.away_min_off: int = 5
        self.away_max_off: int = 30
        self._unsub_away: CALLBACK_TYPE | None = None
        self._unsub_away_window: list[CALLBACK_TYPE] = []

    # ----------------------------------------------------------------
    # Setup / teardown
    # ----------------------------------------------------------------

    async def async_setup(self) -> None:
        self._link_device()
        await self._async_load()
        self._check_runtime_date()
        if _is_active(self.hass.states.get(self.entity_id)):
            if self.last_on_time is None:
                self.last_on_time = dt_util.now()
            self._start_runtime_tick()

    def _link_device(self) -> None:
        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)
        target = ent_reg.async_get(self.entity_id)
        if target and target.device_id:
            phys = dev_reg.async_get(target.device_id)
            if phys:
                self.device_info = DeviceInfo(identifiers=phys.identifiers)
                return
        readable = self.slug.replace("_", " ").title()
        ids = {(DOMAIN, self.entry.entry_id)}
        dev_reg.async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers=ids,
            name=readable,
        )
        self.device_info = DeviceInfo(identifiers=ids, name=readable)

    async def async_unload(self) -> None:
        if self.recover_task:
            self.recover_task.cancel()
            self.recover_task = None
        self._cancel_timer()
        self._cancel_schedules()
        self._cancel_away()
        self._stop_runtime_tick()
        self._flush_runtime()
        await self._async_save()

    @callback
    def handle_shutdown(self, event: Event) -> None:
        self._cancel_timer()
        self._cancel_schedules()
        self._cancel_away()
        self._stop_runtime_tick()

    # ----------------------------------------------------------------
    # Timer control
    # ----------------------------------------------------------------

    async def async_start_timer(self, minutes: float, action: str = ACTION_TURN_OFF) -> None:
        self._cancel_timer()
        if minutes <= 0:
            await self._async_clear_timer()
            return
        self.timer_action = action
        self.timer_expiry = dt_util.now() + timedelta(minutes=minutes)
        self._unsub_timer = async_track_point_in_time(
            self.hass, self._async_timer_expired, self.timer_expiry
        )
        self._notify_update()
        await self._async_save()

    async def async_start_timer_from_expiry(self, expiry_iso: str, action: str) -> None:
        """Resume a timer from a persisted expiry timestamp."""
        expiry = dt_util.parse_datetime(expiry_iso)
        if not expiry or expiry <= dt_util.now():
            await self._async_clear_timer()
            return
        self._cancel_timer()
        self.timer_action = action
        self.timer_expiry = expiry
        self._unsub_timer = async_track_point_in_time(
            self.hass, self._async_timer_expired, self.timer_expiry
        )
        self._notify_update()

    async def async_cancel_timer(self) -> None:
        await self._async_clear_timer()
        await self._async_save()

    async def _async_timer_expired(self, now: datetime) -> None:
        self._unsub_timer = None
        action = self.timer_action or ACTION_TURN_OFF
        entity_id = self.entity_id
        self.timer_action = None
        self.timer_expiry = None
        self._notify_update()
        await self._async_save()
        await _execute_action(self.hass, entity_id, action)
        self.hass.bus.async_fire("smart_timer_expired", {
            "entity_id": entity_id,
            "action": action,
        })

    def _cancel_timer(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

    async def _async_clear_timer(self) -> None:
        self._cancel_timer()
        self.timer_action = None
        self.timer_expiry = None
        self._notify_update()

    # ----------------------------------------------------------------
    # Auto-off (reacts to device state changes)
    # ----------------------------------------------------------------

    @property
    def auto_off_value(self) -> float:
        if self.number_entity and self.number_entity.hass:
            return float(self.number_entity.native_value or 0.0)
        return self.auto_off_minutes

    async def async_handle_state_change(self, event: Event) -> None:
        if self.is_recovering:
            return
        new_s = event.data.get("new_state")
        old_s = event.data.get("old_state")
        if new_s and old_s and new_s.state == old_s.state:
            return

        was_active = _is_active(old_s)
        now_active = _is_active(new_s)

        if now_active and not was_active:
            # Device turned on
            self.last_on_time = dt_util.now()
            self._start_runtime_tick()
            self._notify_update()
            # Start auto-off if configured
            auto_off = self.auto_off_value
            if auto_off > 0 and self.timer_expiry is None:
                await self.async_start_timer(auto_off, ACTION_TURN_OFF)
        elif was_active and not now_active:
            # Device turned off
            self._flush_runtime()
            self._stop_runtime_tick()
            self._notify_update()
            await self._async_save()
            # Cancel any running timer
            if self._unsub_timer:
                await self._async_clear_timer()
                await self._async_save()

    # ----------------------------------------------------------------
    # Schedule engine
    # ----------------------------------------------------------------

    async def async_add_schedule(
        self, action: str, time_str: str, days: list[int] | None = None, enabled: bool = True
    ) -> str:
        schedule_id = uuid.uuid4().hex[:8]
        schedule = {
            "id": schedule_id,
            "action": action,
            "time": time_str,
            "days": days or [],
            "enabled": enabled,
        }
        self.schedules.append(schedule)
        self._setup_single_schedule(schedule)
        await self._async_save()
        self._notify_update()
        return schedule_id

    async def async_remove_schedule(self, schedule_id: str) -> bool:
        found = None
        for i, s in enumerate(self.schedules):
            if s["id"] == schedule_id:
                found = i
                break
        if found is None:
            return False
        self.schedules.pop(found)
        self._cancel_schedules()
        self._setup_all_schedules()
        await self._async_save()
        self._notify_update()
        return True

    def _setup_all_schedules(self) -> None:
        for s in self.schedules:
            if s.get("enabled", True):
                self._setup_single_schedule(s)

    def _setup_single_schedule(self, schedule: dict) -> None:
        parts = schedule["time"].split(":")
        if len(parts) != 2:
            return
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except ValueError:
            return

        @callback
        def _fire(now: datetime, sched=schedule) -> None:
            if sched.get("days"):
                today = now.weekday()
                if today not in [int(d) for d in sched["days"]]:
                    return
            self.hass.async_create_task(
                _execute_action(self.hass, self.entity_id, sched["action"])
            )
            self.hass.bus.async_fire("smart_timer_schedule_fired", {
                "entity_id": self.entity_id,
                "schedule_id": sched["id"],
                "action": sched["action"],
            })

        unsub = async_track_time_change(self.hass, _fire, hour=hour, minute=minute, second=0)
        self._unsub_schedules.append(unsub)

    def _cancel_schedules(self) -> None:
        for unsub in self._unsub_schedules:
            unsub()
        self._unsub_schedules.clear()

    def get_next_schedule_time(self) -> datetime | None:
        """Calculate the next schedule fire time."""
        if not self.schedules:
            return None
        now = dt_util.now()
        earliest = None
        for s in self.schedules:
            if not s.get("enabled", True):
                continue
            parts = s["time"].split(":")
            if len(parts) != 2:
                continue
            try:
                hour, minute = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            # Check day-of-week
            if s.get("days"):
                int_days = [int(d) for d in s["days"]]
                for _ in range(8):
                    if candidate.weekday() in int_days:
                        break
                    candidate += timedelta(days=1)
                else:
                    continue
            if earliest is None or candidate < earliest:
                earliest = candidate
        return earliest

    # ----------------------------------------------------------------
    # Away mode
    # ----------------------------------------------------------------

    async def async_set_away_mode(
        self,
        enabled: bool,
        start_time: str | None = None,
        end_time: str | None = None,
        min_on: int | None = None,
        max_on: int | None = None,
        min_off: int | None = None,
        max_off: int | None = None,
    ) -> None:
        self.away_enabled = enabled
        if start_time is not None:
            self.away_start = start_time
        if end_time is not None:
            self.away_end = end_time
        if min_on is not None:
            self.away_min_on = min_on
        if max_on is not None:
            self.away_max_on = max_on
        if min_off is not None:
            self.away_min_off = min_off
        if max_off is not None:
            self.away_max_off = max_off

        self._cancel_away()
        if enabled:
            self._start_away_mode()
        else:
            # Turn off device if away mode was controlling it
            if _is_active(self.hass.states.get(self.entity_id)):
                pass  # Don't force off — user might have turned it on intentionally
        await self._async_save()
        self._notify_update()

    def _start_away_mode(self) -> None:
        if not self.away_enabled:
            return
        if self._in_away_window():
            self._schedule_away_action()
        # Set up window start/end listeners
        s_parts = self.away_start.split(":")
        e_parts = self.away_end.split(":")
        if len(s_parts) == 2 and len(e_parts) == 2:
            try:
                sh, sm = int(s_parts[0]), int(s_parts[1])
                eh, em = int(e_parts[0]), int(e_parts[1])
            except ValueError:
                return

            @callback
            def _window_start(now: datetime) -> None:
                if self.away_enabled:
                    self._schedule_away_action()

            @callback
            def _window_end(now: datetime) -> None:
                self._cancel_away_action()
                # Turn off at window end
                if _is_active(self.hass.states.get(self.entity_id)):
                    self.hass.async_create_task(
                        _execute_action(self.hass, self.entity_id, ACTION_TURN_OFF)
                    )

            self._unsub_away_window.append(
                async_track_time_change(self.hass, _window_start, hour=sh, minute=sm, second=0)
            )
            self._unsub_away_window.append(
                async_track_time_change(self.hass, _window_end, hour=eh, minute=em, second=0)
            )

    def _in_away_window(self) -> bool:
        now = dt_util.now()
        try:
            sp = self.away_start.split(":")
            ep = self.away_end.split(":")
            start = now.replace(hour=int(sp[0]), minute=int(sp[1]), second=0, microsecond=0)
            end = now.replace(hour=int(ep[0]), minute=int(ep[1]), second=0, microsecond=0)
        except (ValueError, IndexError):
            return False
        if end <= start:
            # Crosses midnight
            return now >= start or now < end
        return start <= now < end

    def _schedule_away_action(self) -> None:
        self._cancel_away_action()
        is_on = _is_active(self.hass.states.get(self.entity_id))
        if is_on:
            delay = random.randint(self.away_min_on, max(self.away_min_on, self.away_max_on))
            action = ACTION_TURN_OFF
        else:
            delay = random.randint(self.away_min_off, max(self.away_min_off, self.away_max_off))
            action = ACTION_TURN_ON
        fire_at = dt_util.now() + timedelta(minutes=delay)

        @callback
        def _away_fire(now: datetime) -> None:
            self._unsub_away = None
            if not self.away_enabled or not self._in_away_window():
                return
            self.hass.async_create_task(
                _execute_action(self.hass, self.entity_id, action)
            )
            # Schedule next cycle after a brief pause for state to update
            self.hass.async_create_task(self._async_away_next_cycle())

        self._unsub_away = async_track_point_in_time(self.hass, _away_fire, fire_at)

    async def _async_away_next_cycle(self) -> None:
        await asyncio.sleep(2)
        if self.away_enabled and self._in_away_window():
            self._schedule_away_action()

    def _cancel_away_action(self) -> None:
        if self._unsub_away:
            self._unsub_away()
            self._unsub_away = None

    def _cancel_away(self) -> None:
        self._cancel_away_action()
        for unsub in self._unsub_away_window:
            unsub()
        self._unsub_away_window.clear()

    # ----------------------------------------------------------------
    # Runtime tracking
    # ----------------------------------------------------------------

    def _check_runtime_date(self) -> None:
        today = dt_util.now().strftime("%Y-%m-%d")
        if self.runtime_date != today:
            self.runtime_seconds_today = 0.0
            self.runtime_date = today

    def _flush_runtime(self) -> None:
        """Accumulate on-time since last_on_time into today's total."""
        self._check_runtime_date()
        if self.last_on_time:
            elapsed = (dt_util.now() - self.last_on_time).total_seconds()
            self.runtime_seconds_today += max(0, elapsed)
            self.last_on_time = None

    def _start_runtime_tick(self) -> None:
        if self._unsub_runtime_tick:
            return

        @callback
        def _tick(now: datetime) -> None:
            self._check_runtime_date()
            self._notify_update()

        self._unsub_runtime_tick = async_track_time_interval(
            self.hass, _tick, timedelta(seconds=60)
        )

    def _stop_runtime_tick(self) -> None:
        if self._unsub_runtime_tick:
            self._unsub_runtime_tick()
            self._unsub_runtime_tick = None

    @property
    def current_runtime_seconds(self) -> float:
        """Get total runtime including current active session."""
        self._check_runtime_date()
        total = self.runtime_seconds_today
        if self.last_on_time:
            total += max(0, (dt_util.now() - self.last_on_time).total_seconds())
        return total

    @property
    def runtime_display(self) -> str:
        secs = int(self.current_runtime_seconds)
        hours = secs // 3600
        mins = (secs % 3600) // 60
        if hours > 0:
            return f"{hours}h {mins}m"
        return f"{mins}m"

    # ----------------------------------------------------------------
    # Persistence
    # ----------------------------------------------------------------

    async def _async_load(self) -> None:
        store = self.hass.data[DOMAIN]["store"]
        raw = await store.async_load() or {}
        devices = raw.get("devices", {})
        data = devices.get(self.entity_id, {})
        if not data:
            return

        # Timer
        timer = data.get("timer")
        if timer and timer.get("expiry"):
            self.timer_action = timer.get("action", ACTION_TURN_OFF)
            # Expiry is resumed in async_recover

        # Schedules
        self.schedules = data.get("schedules", [])

        # Away mode
        away = data.get("away", {})
        self.away_enabled = away.get("enabled", False)
        self.away_start = away.get("start_time", "18:00")
        self.away_end = away.get("end_time", "23:00")
        self.away_min_on = away.get("min_on", 10)
        self.away_max_on = away.get("max_on", 45)
        self.away_min_off = away.get("min_off", 5)
        self.away_max_off = away.get("max_off", 30)

        # Runtime
        rt = data.get("runtime", {})
        self.runtime_seconds_today = rt.get("seconds", 0.0)
        self.runtime_date = rt.get("date")
        lo = rt.get("last_on")
        if lo:
            self.last_on_time = dt_util.parse_datetime(lo)

    async def _async_save(self) -> None:
        if self.hass.is_stopping:
            return
        async with self.hass.data[DOMAIN]["save_lock"]:
            store = self.hass.data[DOMAIN]["store"]
            raw = await store.async_load() or {}
            devices = raw.get("devices", {})

            self._flush_runtime() if _is_active(self.hass.states.get(self.entity_id)) else None
            # Re-set last_on if device is still active after flush
            if _is_active(self.hass.states.get(self.entity_id)):
                self.last_on_time = dt_util.now()

            devices[self.entity_id] = {
                "timer": {
                    "action": self.timer_action,
                    "expiry": self.timer_expiry.isoformat() if self.timer_expiry else None,
                } if self.timer_expiry else None,
                "schedules": self.schedules,
                "away": {
                    "enabled": self.away_enabled,
                    "start_time": self.away_start,
                    "end_time": self.away_end,
                    "min_on": self.away_min_on,
                    "max_on": self.away_max_on,
                    "min_off": self.away_min_off,
                    "max_off": self.away_max_off,
                },
                "runtime": {
                    "seconds": self.runtime_seconds_today,
                    "date": self.runtime_date or dt_util.now().strftime("%Y-%m-%d"),
                    "last_on": self.last_on_time.isoformat() if self.last_on_time else None,
                },
            }
            raw["devices"] = devices
            await store.async_save(raw)

    # ----------------------------------------------------------------
    # Recovery
    # ----------------------------------------------------------------

    async def async_recover(self) -> None:
        try:
            store = self.hass.data[DOMAIN]["store"]
            raw = await store.async_load() or {}
            data = raw.get("devices", {}).get(self.entity_id, {})
            timer = data.get("timer")

            if timer and timer.get("expiry"):
                await asyncio.sleep(RECOVERY_GRACE_SECONDS)
                expiry_str = timer["expiry"]
                action = timer.get("action", ACTION_TURN_OFF)
                expiry = dt_util.parse_datetime(expiry_str)
                if expiry and expiry > dt_util.now():
                    await self.async_start_timer_from_expiry(expiry_str, action)
                else:
                    # Timer expired during downtime
                    state = self.hass.states.get(self.entity_id)
                    if expiry and _is_active(state) and action == ACTION_TURN_OFF:
                        await _execute_action(self.hass, self.entity_id, action)
                    await self._async_clear_timer()
                    await self._async_save()

            # Set up schedules and away mode
            self._setup_all_schedules()
            if self.away_enabled:
                self._start_away_mode()
        finally:
            self.is_recovering = False

    # ----------------------------------------------------------------
    # Notifications
    # ----------------------------------------------------------------

    def _notify_update(self) -> None:
        async_dispatcher_send(self.hass, signal_update(self.entity_id))
