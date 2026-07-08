from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from app.common.utils import parse_and_validate_time_window
from app.tools.base import BaseTool

class TimeWindowInput(BaseModel):
    start: str = Field(..., description="ISO-8601 start timestamp.")
    end: str = Field(..., description="ISO-8601 end timestamp.")
    shift_minutes: int | None = Field(default=None, description="Optional minutes to shift/expand the window bounds.")

class TimeWindowResponse(BaseModel):
    start: str
    end: str

class TimeWindowTool(BaseTool):
    """
    Diagnostic tool to calculate, validate, and shift chronological time window bounds.
    """
    name: str = "time_window_adjuster"
    description: str = (
        "Validates start and end timestamps and shifts/expands the time window "
        "boundaries by a specified offset."
    )
    args_model: type[BaseModel] = TimeWindowInput

    def run(self, start: str, end: str, shift_minutes: int | None = None) -> TimeWindowResponse:
        start_dt, end_dt = parse_and_validate_time_window(start, end)

        if shift_minutes:
            start_dt = start_dt - timedelta(minutes=shift_minutes)
            end_dt = end_dt + timedelta(minutes=shift_minutes)

        return TimeWindowResponse(
            start=start_dt.isoformat().replace("+00:00", "Z"),
            end=end_dt.isoformat().replace("+00:00", "Z")
        )
