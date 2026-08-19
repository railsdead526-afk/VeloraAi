from app.tools.builtin import register_platform_tools
from app.tools.registry import registry

_INITIALIZED = False


def get_registry():
    global _INITIALIZED
    if not _INITIALIZED:
        register_platform_tools(registry)
        _INITIALIZED = True
    return registry
