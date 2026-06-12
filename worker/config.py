from datetime import datetime, timezone, timedelta

# Bangladesh Time is UTC+6
BST = timezone(timedelta(hours=6))

# Event Boundaries
EVENT_START_BST = datetime(2026, 6, 12, 0, 0, 0, tzinfo=BST)
EVENT_END_BST = datetime(2026, 6, 12, 23, 59, 59, tzinfo=BST)

EVENT_START_UTC = EVENT_START_BST.astimezone(timezone.utc)
EVENT_END_UTC = EVENT_END_BST.astimezone(timezone.utc)

def is_within_event(dt: datetime) -> bool:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return EVENT_START_BST <= dt <= EVENT_END_BST
