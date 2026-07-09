from app.tools.base import BaseTool
from app.common.exceptions import ToolNotFoundError

class ToolRegistry:
    """
    Lightweight registry to catalog, search, and manage diagnostic tools.
    """
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """
        Registers a tool instance in the registry catalog.
        """
        if tool.name in self._tools:
            from app.common.exceptions import ValidationError
            raise ValidationError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> BaseTool:
        """
        Retrieves a registered tool by its name key.
        Raises ToolNotFoundError if key is missing.
        """
        if name not in self._tools:
            raise ToolNotFoundError(name)
        return self._tools[name]

    def list_tools(self) -> list[BaseTool]:
        """
        Returns all registered tool instances.
        """
        return list(self._tools.values())

    def get_schemas(self) -> dict[str, dict]:
        """
        Returns tool schemas mapping JSON definition structures,
        suitable for LLM tool binding contracts.
        """
        schemas = {}
        for name, tool in self._tools.items():
            schemas[name] = {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.args_model.model_json_schema()
            }
        return schemas
