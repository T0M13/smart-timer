# Smart Timer

A Home Assistant custom integration that replaces the Tapo app's timer, scheduling, and away mode features — works with **any** HA device (switches, lights, fans, covers, etc.).

## Features

- **Auto-Off Timer** — automatically turn off a device after a set duration every time it turns on
- **One-Shot Timers** — turn a device off or on after X minutes (via service call or card)
- **Scheduling** — recurring on/off rules by time and day of week
- **Away Mode** — random on/off within a time window to simulate presence
- **Runtime Tracking** — daily on-time counter, resets at midnight
- **Lovelace Card** — polished UI card with countdown, quick timers, schedule management

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

1. Go to Settings → Devices & Services → Add Integration
2. Search for "Smart Timer"
3. Select a device to manage
4. The integration creates entities on the device card:
   - `number.<device>_auto_off` — auto-off duration (0 = disabled)
   - `binary_sensor.<device>_timer_active` — is a timer running?
   - `sensor.<device>_time_remaining` — countdown display
   - `sensor.<device>_daily_runtime` — today's on-time
   - `sensor.<device>_next_schedule` — next scheduled action
   - `switch.<device>_away_mode` — away mode toggle

## Lovelace Card

```yaml
type: custom:smart-timer-card
entity: switch.living_room_light
name: Living Room  # optional
presets: [15, 30, 60, 120]  # optional, timer preset buttons in minutes
show_schedules: true  # optional, default true
show_away: true  # optional, default true
show_runtime: true  # optional, default true
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

### `smart_timer.set_away_mode`
Configure away mode.
```yaml
service: smart_timer.set_away_mode
data:
  entity_id: switch.living_room_light
  enabled: true
  start_time: "18:00"
  end_time: "23:00"
  min_on_minutes: 10
  max_on_minutes: 45
  min_off_minutes: 5
  max_off_minutes: 30
```

## Events

- `smart_timer_expired` — fired when a timer expires (contains `entity_id` and `action`)
- `smart_timer_schedule_fired` — fired when a schedule executes

## Compared to time_off

| Feature | time_off | Smart Timer |
|---------|----------|-------------|
| Auto-off timer | Yes | Yes |
| Turn-on timer | No | Yes |
| Scheduling | No | Yes |
| Away mode | No | Yes |
| Runtime tracking | No | Yes |
| Lovelace card | No | Yes |
| Persists across restarts | Yes | Yes |
