"""
Built-in tools for the V4 Engine.
Import all tool collections and provide a single registration function.
"""
from ..registry import ToolRegistry

from .file_tools import FILE_TOOLS
from .shell_tools import SHELL_TOOLS
from .code_tools import CODE_TOOLS
from .web_tools import WEB_TOOLS
from .memory_tools import MEMORY_TOOLS
from .search_tools import SEARCH_TOOLS
from .vision_tools import VISION_TOOLS


def register_builtin_tools(registry: ToolRegistry):
    """Register all built-in tools in the registry."""
    all_tools = (
        FILE_TOOLS +
        SHELL_TOOLS +
        CODE_TOOLS +
        WEB_TOOLS +
        MEMORY_TOOLS +
        SEARCH_TOOLS +
        VISION_TOOLS
    )
    registry.register_many(all_tools)
    return len(all_tools)
