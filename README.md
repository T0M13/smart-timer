<p align="center">
  <img src="icon.png" alt="Smart Timer" width="128" height="128">
</p>

<h1 align="center">Smart Timer</h1>

<p align="center">
  A Home Assistant custom integration that adds timers, auto-off, and scheduling to <strong>any</strong> HA device (switches, lights, fans, covers, etc.).
</p>

---

## Features

- **Turn Off In** — set minutes, device turns off after countdown
- **Turn On In** — set minutes, device turns on after countdown
- **Auto-Off Duration** — set once, device auto-turns-off every time it turns on
- **Timer Active** — binary sensor showing if a timer is running
- **Time Remaining** — live countdown sensor (MM:SS format)
- **Scheduling** — recurring on/off rules by time and day of week
- **Lovelace Card** — toggle, preset buttons, auto-off input, schedule management

Everything works directly from the device page — no YAML, no Developer Tools needed.

## Installation

### HACS (recommended)
1. Add this repository as a custom repository in HACS
2. Search for "Smart Timer" and install
3. Restart Home Assistant

### Manual
1. Copy `custom_components/smart_timer/` to your HA `config/custom_components/` directory
2. Copy `smart-timer-card.js` to `config/www/`
3. Restart Home Assistant
4. Add the card resource: Settings → Dashboards → Resources → Add `/local/smart-timer-card.js` (JavaScript Module)

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Smart Timer**
3. Select a device to manage
4. The integration creates entities on the device page:

| Entity | Type | Description |
|--------|------|-------------|
| `number.<device>_turn_off_in` | Number | Set minutes → starts turn-off countdown, resets to 0 when done |
| `number.<device>_turn_on_in` | Number | Set minutes → starts turn-on countdown, resets to 0 when done |
| `number.<device>_auto_off` | Number | Persistent auto-off duration (0 = disabled). Device auto-turns-off every time it turns on |
| `binary_sensor.<device>_timer_active` | Binary Sensor | ON while a timer is running |
| `sensor.<device>_time_remaining` | Sensor | Live countdown display (MM:SS) |
| `sensor.<device>_next_schedule` | Sensor | Next scheduled action time, full schedule list in attributes |

## Lovelace Card

```yaml
type: custom:smart-timer-card
entity: switch.living_room_light
name: Living Room  # optional
presets: [15, 30, 60, 120]  # optional, timer preset buttons in minutes
show_schedules: true  # optional, default true
```

## Services

### `smart_timer.start_timer`
Start a one-shot countdown timer.
```yaml
service: smart_timer.start_timer
data:
  entity_id: switch.living_room_light
  minutes: 30
  action: turn_off  # or turn_on
```

### `smart_timer.cancel_timer`
Cancel an active timer.

### `smart_timer.add_schedule`
Add a recurring schedule.
```yaml
service: smart_timer.add_schedule
data:
  entity_id: switch.living_room_light
  action: turn_on
  time: "07:00"
  days: ["0", "1", "2", "3", "4"]  # Mon-Fri (optional, empty = every day)
```

### `smart_timer.remove_schedule`
Remove a schedule by ID.

## Compared to other plugins

| Feature | Other Timer | Smart Timer |
|---------|----------|-------------|
| Auto-off timer | Yes | Yes |
| Turn-off-in timer | No | Yes |
| Turn-on-in timer | No | Yes |
| Scheduling | No | Yes |
| Lovelace card | No | Yes |
| Persists across restarts | No | Yes |
| Works from device page | No | Yes |

## License

MIT
