"""
Plugin manifest schema.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PluginManifest:
    """Schema for plugin.json manifest file."""
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""

    # Entry points
    tools_dir: str = "tools"        # Directory containing tool modules
    hooks_dir: str = "hooks"        # Directory containing hook modules
    agents_dir: str = "agents"      # Directory containing agent YAML files

    # Dependencies
    requires: list[str] = field(default_factory=list)  # Required plugin names
    python_requires: str = ">=3.11"

    # Capabilities
    enabled: bool = True
    tool_names: list[str] = field(default_factory=list)  # Explicitly declared tools
    hook_events: list[str] = field(default_factory=list)  # Events this plugin hooks into

    # Metadata
    homepage: str = ""
    license: str = ""
