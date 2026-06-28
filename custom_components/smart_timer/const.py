DOMAIN = "smart_timer"
VERSION = "1.2.0"

STORAGE_KEY = "smart_timer.data"
STORAGE_VERSION = 1

PLATFORMS = ["number", "binary_sensor", "sensor", "switch", "select", "text", "button"]

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

DAY_PARSE = {
    "mon": 0, "mo": 0, "monday": 0,
    "tue": 1, "tu": 1, "tuesday": 1,
    "wed": 2, "we": 2, "wednesday": 2,
    "thu": 3, "th": 3, "thursday": 3,
    "fri": 4, "fr": 4, "friday": 4,
    "sat": 5, "sa": 5, "saturday": 5,
    "sun": 6, "su": 6, "sunday": 6,
}


def parse_days(text: str) -> list[int]:
    """Parse day text like 'Mon,Tue,Fri' or 'Weekdays' into day numbers."""
    text = text.strip().lower()
    if not text or text in ("every day", "*", "all", "daily"):
        return []
    if text in ("weekdays", "weekday", "work", "workdays"):
        return [0, 1, 2, 3, 4]
    if text in ("weekend", "weekends"):
        return [5, 6]
    days = []
    for part in text.replace(" ", "").split(","):
        d = DAY_PARSE.get(part)
        if d is not None and d not in days:
            days.append(d)
    days.sort()
    return days


def format_days(days: list[int]) -> str:
    """Format day numbers to readable string."""
    if not days:
        return "Every Day"
    return ", ".join(DAY_NAMES[d] for d in sorted(days) if 0 <= d <= 6)

CONF_ENTITY_ID = "entity_id"

ACTION_TURN_ON = "turn_on"
ACTION_TURN_OFF = "turn_off"
