from __future__ import annotations

import asyncio
import logging

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CoreState, HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .const import (
    ACTION_TURN_OFF,
    CONF_ENTITY_ID,
    DOMAIN,
    PLATFORMS,
    STORAGE_KEY,
    STORAGE_VERSION,
    VERSION,
)
from .coordinator import SmartTimerCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _find_coordinator(hass: HomeAssistant, entity_id: str) -> SmartTimerCoordinator:
    for coord in hass.data.get(DOMAIN, {}).get("coordinators", {}).values():
        if coord.entity_id == entity_id:
            return coord
    raise ServiceValidationError(
        f"{entity_id} is not managed by Smart Timer."
    )


async def async_setup(hass: HomeAssistant, config) -> bool:
    _LOGGER.debug("Smart Timer %s: registering services", VERSION)

    async def handle_start_timer(call: ServiceCall) -> None:
        coord = _find_coordinator(hass, call.data["entity_id"])
        action = call.data.get("action", ACTION_TURN_OFF)
        await coord.async_start_timer(call.data["minutes"], action)

    async def handle_cancel_timer(call: ServiceCall) -> None:
        coord = _find_coordinator(hass, call.data["entity_id"])
        await coord.async_cancel_timer()

    async def handle_add_schedule(call: ServiceCall) -> None:
        coord = _find_coordinator(hass, call.data["entity_id"])
        days = call.data.get("days")
        if days:
            days = [int(d) for d in days]
        await coord.async_add_schedule(
            action=call.data["action"],
            time_str=call.data["time"],
            days=days,
        )

    async def handle_remove_schedule(call: ServiceCall) -> None:
        coord = _find_coordinator(hass, call.data["entity_id"])
        removed = await coord.async_remove_schedule(call.data["schedule_id"])
        if not removed:
            raise ServiceValidationError(
                f"Schedule {call.data['schedule_id']} not found."
            )

    async def handle_toggle_schedule(call: ServiceCall) -> None:
        coord = _find_coordinator(hass, call.data["entity_id"])
        enabled = call.data.get("enabled")
        toggled = await coord.async_toggle_schedule(call.data["schedule_id"], enabled)
        if not toggled:
            raise ServiceValidationError(
                f"Schedule {call.data['schedule_id']} not found."
            )

    hass.services.async_register(DOMAIN, "start_timer", handle_start_timer)
    hass.services.async_register(DOMAIN, "cancel_timer", handle_cancel_timer)
    hass.services.async_register(DOMAIN, "add_schedule", handle_add_schedule)
    hass.services.async_register(DOMAIN, "remove_schedule", handle_remove_schedule)
    hass.services.async_register(DOMAIN, "toggle_schedule", handle_toggle_schedule)

    return True


VALID_UNIQUE_SUFFIXES = frozenset({
    "auto_off", "turn_off_in", "turn_on_in",
    "timer_active", "time_remaining", "next_schedule",
    "schedule_action", "schedule_time", "schedule_days",
    "add_schedule", "remove_last_schedule",
})

# Schedule switch entities use "sched_" prefix, handled separately
def _is_valid_unique_id(uid: str, prefix: str) -> bool:
    suffix = uid[len(prefix):]
    return suffix in VALID_UNIQUE_SUFFIXES or suffix.startswith("sched_")


def _cleanup_orphaned_entities(
    hass: HomeAssistant, entry: ConfigEntry, slug: str
) -> None:
    """Remove entities from previous versions that no longer exist."""
    ent_reg = er.async_get(hass)
    prefix = f"{DOMAIN}_{slug}_"
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        uid = ent.unique_id or ""
        if uid.startswith(prefix):
            if not _is_valid_unique_id(uid, prefix):
                _LOGGER.info("Removing orphaned entity %s (%s)", ent.entity_id, uid)
                ent_reg.async_remove(ent.entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.setdefault(DOMAIN, {
        "store": Store(hass, STORAGE_VERSION, STORAGE_KEY),
        "save_lock": asyncio.Lock(),
        "coordinators": {},
    })

    entity_id = entry.data.get(CONF_ENTITY_ID)
    if not entity_id:
        _LOGGER.error("Smart Timer: entry %s has no entity_id", entry.entry_id)
        return False

    coordinator = SmartTimerCoordinator(hass, entry, entity_id)
    domain_data["coordinators"][entry.entry_id] = coordinator

    await coordinator.async_setup()

    # Clean up orphaned entities from older versions
    _cleanup_orphaned_entities(hass, entry, coordinator.slug)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    def _schedule_recover() -> None:
        coordinator.recover_task = hass.async_create_background_task(
            coordinator.async_recover(), name=f"smart_timer_recover_{entry.entry_id}"
        )

    if hass.state == CoreState.running:
        _schedule_recover()
    else:
        async def _on_started(event) -> None:
            _schedule_recover()
        entry.async_on_unload(
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_started)
        )

    entry.async_on_unload(
        async_track_state_change_event(
            hass, [entity_id], coordinator.async_handle_state_change
        )
    )

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, coordinator.handle_shutdown)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = hass.data[DOMAIN]["coordinators"].get(entry.entry_id)
    if coordinator:
        await coordinator.async_unload()

    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN]["coordinators"].pop(entry.entry_id, None)
    return ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    domain_data = hass.data.get(DOMAIN)
    if not domain_data:
        return
    entity_id = entry.data.get(CONF_ENTITY_ID)
    if not entity_id:
        return
    # Clean up persisted timer/schedule data
    async with domain_data["save_lock"]:
        store = domain_data["store"]
        raw = await store.async_load() or {}
        devices = raw.get("devices", {})
        if entity_id in devices:
            del devices[entity_id]
            raw["devices"] = devices
            await store.async_save(raw)
    # Clean up restore_state data for our entities
    slug = entity_id.split(".")[-1]
    restore_key = "core.restore_state"
    restore_store = Store(hass, 1, restore_key)
    try:
        restore_data = await restore_store.async_load()
        if restore_data and isinstance(restore_data, list):
            slug_prefix = f"{slug}_"
            filtered = [
                e for e in restore_data
                if not any(
                    (e.get("state", {}).get("entity_id") or "").endswith(eid)
                    for eid in [f"{slug_prefix}{s}" for s in VALID_UNIQUE_SUFFIXES]
                )
            ]
            if len(filtered) < len(restore_data):
                await restore_store.async_save(filtered)
                _LOGGER.info("Cleaned up restore_state for %s", entity_id)
    except Exception:
        pass
