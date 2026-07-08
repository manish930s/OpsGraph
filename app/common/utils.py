from datetime import datetime
from app.common.exceptions import ValidationError

def parse_and_validate_time_window(start: str, end: str) -> tuple[datetime, datetime]:
    """
    Parses start and end ISO-8601 strings into datetime objects and asserts chronology.
    Raises ValidationError if any checks fail.
    """
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValidationError(f"Invalid time window format: {e}")

    if start_dt > end_dt:
        raise ValidationError(f"Start time ({start}) must be before or equal to end time ({end})")

    return start_dt, end_dt
