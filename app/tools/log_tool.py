from pydantic import BaseModel, Field
from app.schemas.telemetry import LogRecord
from app.services.telemetry.log_repository import LogRepository
from app.tools.base import BaseTool

class LogSearchInput(BaseModel):
    service: str | None = Field(default=None, description="Filter logs by service name.")
    pattern: str | None = Field(default=None, description="Regex/string query to match message content.")
    start: str | None = Field(default=None, description="ISO-8601 window start filter.")
    end: str | None = Field(default=None, description="ISO-8601 window end filter.")

class LogSearchResponse(BaseModel):
    logs: list[LogRecord] = Field(default_factory=list, description="List of matched log records.")

class LogSearchTool(BaseTool):
    """
    Diagnostic tool to query, search, and filter incident log records.
    """
    name: str = "log_pattern_search"
    description: str = (
        "Queries and filters logs by service, time window, and message regex patterns. "
        "Returns a list of matched logs."
    )
    args_model: type[BaseModel] = LogSearchInput

    def __init__(self, log_repo: LogRepository):
        self.log_repo = log_repo

    def run(
        self,
        service: str | None = None,
        pattern: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> LogSearchResponse:
        logs = self.log_repo.get_logs()

        # Apply service filter if provided
        if service:
            logs = self.log_repo.filter_by_service(service)

        # Apply time window filters if provided
        if start or end:
            # Fallback to full bounds if only one is specified
            start_str = start if start else "1970-01-01T00:00:00Z"
            end_str = end if end else "2100-01-01T00:00:00Z"
            logs = self.log_repo.filter_by_time_window(start_str, end_str)
            # Re-apply service filter if we restarted from full bounds
            if service:
                logs = [l for l in logs if l.service == service]

        # Apply pattern matching
        if pattern:
            # We filter the current list using repository pattern matching helper
            # To be efficient, we can search on the subset or run it directly
            # Let's search on the filtered set
            import re
            regex = re.compile(pattern, re.IGNORECASE)
            logs = [l for l in logs if regex.search(l.message)]

        return LogSearchResponse(logs=logs)
