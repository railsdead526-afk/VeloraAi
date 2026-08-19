from app.tools.builtin import register_platform_tools
from app.tools.registry import ToolRegistry


tool_registry = ToolRegistry()
register_platform_tools(tool_registry)
