import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # --- PROJECT PATHS ---
    WORKSPACE_DIR: Path = Field(default=Path(__file__).resolve().parents[1])
    SCENARIO_DIR: Path = Field(default=Path(__file__).resolve().parents[1] / "data/scenarios/definitions")
    KNOWLEDGE_DIR: Path = Field(default=Path(__file__).resolve().parents[1] / "data/knowledge")
    GENERATED_DATA_DIR: Path = Field(default=Path(__file__).resolve().parents[1] / "data/generated")

    # --- GEMINI EMBEDDINGS ---
    GEMINI_API_KEY: str | None = Field(default=None)

    # --- VECTOR DB (QDRANT) ---
    QDRANT_URL: str | None = Field(default=None)
    QDRANT_API_KEY: str | None = Field(default=None)
    QDRANT_COLLECTION: str = Field(default="opsgraph_knowledge")

    # --- MODEL GATEWAY ---
    LLM_BASE_URL: str | None = Field(default=None)
    LLM_API_KEY: str | None = Field(default=None)
    LLM_MODEL: str = Field(default="llama-3.3-70b-versatile")
    LLM_PROVIDER: str = Field(default="mock")

    # --- REASONING ENGINE (GROQ / OTHER) ---
    GROQ_API_KEY: str | None = Field(default=None)
    GROQ_MODEL: str = Field(default="llama-3.3-70b-versatile")
    GROQ_FALLBACK_API_KEY: str | None = Field(default=None)

    # --- LLM GATEWAY (PORTKEY) ---
    PORTKEY_API_KEY: str | None = Field(default=None)
    GROQ_SLUG: str = Field(default="rag")
    GROQ_SLUG_2: str = Field(default="brag")

    # --- OBSERVABILITY ---
    LANGSMITH_TRACING: str = Field(default="true")
    LANGSMITH_API_KEY: str | None = Field(default=None)
    LANGSMITH_PROJECT: str = Field(default="opsgraph_ai")
    LANGSMITH_ENDPOINT: str = Field(default="https://api.smith.langchain.com")
    LOGFIRE_TOKEN: str | None = Field(default=None)

    # --- PERFORMANCE BUDGETS ---
    PLANNER_LATENCY_BUDGET_MS: int = Field(default=1500)
    RETRIEVAL_LATENCY_BUDGET_MS: int = Field(default=800)
    TOOL_EXECUTION_BUDGET_MS: int = Field(default=2000)
    GATEWAY_TIMEOUT_SEC: float = Field(default=30.0)
    MAX_INVESTIGATION_LATENCY_SEC: float = Field(default=10.0)
    MAX_GRAPH_DEPTH: int = Field(default=15)
    MAX_TOOL_CALLS: int = Field(default=8)

    # --- CONFIDENCE THRESHOLDS ---
    CONFIDENCE_STRONG_THRESHOLD: float = Field(default=0.80)
    CONFIDENCE_MODERATE_THRESHOLD: float = Field(default=0.60)

# Instantiate settings
settings = Settings()

# Apply LangChain environment variables for automatic tracing
os.environ["LANGCHAIN_TRACING_V2"] = settings.LANGSMITH_TRACING
if settings.LANGSMITH_API_KEY:
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGSMITH_ENDPOINT

