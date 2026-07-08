from pydantic import BaseModel, field_validator, model_validator
from datetime import datetime

class TimeWindow(BaseModel):
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def validate_iso_format(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"Invalid ISO-8601 datetime string: {v}")
        return v

    @model_validator(mode="after")
    def validate_chronology(self) -> "TimeWindow":
        start_dt = datetime.fromisoformat(self.start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(self.end.replace("Z", "+00:00"))
        if start_dt > end_dt:
            raise ValueError(f"Start time ({self.start}) must be before or equal to end time ({self.end})")
        return self
