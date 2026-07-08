import os
from pathlib import Path

class PromptRegistry:
    """
    Registry for versioned prompt templates loaded dynamically from the workspace.
    """
    def __init__(self, prompts_dir: Path | None = None):
        if prompts_dir is None:
            # Fallback relative to project root
            self.prompts_dir = Path(__file__).resolve().parents[3] / "prompts"
        else:
            self.prompts_dir = prompts_dir

    def get_template(self, template_id: str, version: str) -> str:
        """
        Loads a template by path, e.g. system_v1 -> system_v1.txt under prompts/rca.
        """
        # Determine subdirectory based on template_id / purpose
        sub_dir = "rca"
        filename = f"{template_id}_{version}.txt"
        file_path = self.prompts_dir / sub_dir / filename
        
        if not file_path.exists():
            # Try flat fallback if needed or raise
            raise FileNotFoundError(f"Prompt template not found at: {file_path}")
            
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

# Central registry instance
prompt_registry = PromptRegistry()
