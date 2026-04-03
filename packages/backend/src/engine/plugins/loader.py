"""
Plugin loader - discovers, validates, and loads plugins.
"""
import json
import importlib.util
import logging
from pathlib import Path
from typing import Optional

from .schema import PluginManifest
from ..tools.registry import ToolRegistry
from ..tools.base import ToolDefinition
from ..hooks.manager import HookManager

logger = logging.getLogger("ahri.engine.plugins")


class PluginLoader:
    """
    Discovers and loads plugins from configured directories.
    """

    def __init__(self, tool_registry: ToolRegistry, hook_manager: Optional[HookManager] = None):
        self.tool_registry = tool_registry
        self.hook_manager = hook_manager
        self._loaded: dict[str, PluginManifest] = {}

    def discover(self, plugin_dirs: list[str]) -> list[PluginManifest]:
        """Discover all plugins in the given directories."""
        manifests = []
        for dir_path in plugin_dirs:
            p = Path(dir_path)
            if not p.exists():
                logger.warning(f"Plugin directory not found: {dir_path}")
                continue

            for child in p.iterdir():
                if child.is_dir():
                    manifest_file = child / "plugin.json"
                    if manifest_file.exists():
                        try:
                            manifest = self._load_manifest(manifest_file)
                            manifests.append(manifest)
                        except Exception as e:
                            logger.error(f"Failed to load plugin manifest {manifest_file}: {e}")

        return manifests

    def load(self, plugin_dir: Path, manifest: PluginManifest) -> int:
        """
        Load a single plugin.

        Returns:
            Number of tools registered
        """
        if manifest.name in self._loaded:
            logger.warning(f"Plugin already loaded: {manifest.name}")
            return 0

        tools_loaded = 0

        # Load tools
        tools_path = plugin_dir / manifest.tools_dir
        if tools_path.exists():
            for py_file in tools_path.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                tools = self._load_tools_from_file(py_file, manifest.name)
                tools_loaded += len(tools)

        # Load hooks
        hooks_path = plugin_dir / manifest.hooks_dir
        if hooks_path.exists() and self.hook_manager:
            for py_file in hooks_path.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                self._load_hooks_from_file(py_file, manifest.name)

        self._loaded[manifest.name] = manifest
        logger.info(f"Loaded plugin '{manifest.name}' v{manifest.version}: {tools_loaded} tools")
        return tools_loaded

    def load_all(self, plugin_dirs: list[str]) -> int:
        """Discover and load all plugins. Returns total tools loaded."""
        total = 0

        # Build name → path mapping during discovery (O(n) instead of O(n²))
        manifest_paths: dict[str, tuple[Path, PluginManifest]] = {}
        for dir_path in plugin_dirs:
            p = Path(dir_path)
            if not p.exists():
                continue
            for child in p.iterdir():
                if child.is_dir():
                    mf = child / "plugin.json"
                    if mf.exists():
                        try:
                            manifest = self._load_manifest(mf)
                            manifest_paths[manifest.name] = (child, manifest)
                        except Exception as e:
                            logger.error(f"Failed to load plugin manifest {mf}: {e}")

        for name, (plugin_path, manifest) in manifest_paths.items():
            total += self.load(plugin_path, manifest)

        return total

    def _load_manifest(self, manifest_file: Path) -> PluginManifest:
        """Parse plugin.json into PluginManifest."""
        with open(manifest_file) as f:
            data = json.load(f)
        return PluginManifest(**data)

    def _load_tools_from_file(self, py_file: Path, plugin_name: str) -> list[ToolDefinition]:
        """Dynamically load tools from a Python file."""
        tools = []
        try:
            spec = importlib.util.spec_from_file_location(
                f"plugin_{plugin_name}_{py_file.stem}", py_file
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Look for exported tool lists (e.g., FILE_TOOLS, MY_TOOLS)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, list):
                    for item in attr:
                        if isinstance(item, ToolDefinition):
                            item.plugin_name = plugin_name
                            item.is_builtin = False
                            self.tool_registry.register(item)
                            tools.append(item)
                elif isinstance(attr, ToolDefinition):
                    attr.plugin_name = plugin_name
                    attr.is_builtin = False
                    self.tool_registry.register(attr)
                    tools.append(attr)

        except Exception as e:
            logger.error(f"Failed to load tools from {py_file}: {e}")

        return tools

    def _load_hooks_from_file(self, py_file: Path, plugin_name: str):
        """Dynamically load hooks from a Python file."""
        try:
            spec = importlib.util.spec_from_file_location(
                f"plugin_{plugin_name}_hooks_{py_file.stem}", py_file
            )
            module = importlib.util.module_from_spec(spec)

            # Inject hook_manager so the module can register hooks
            module.hook_manager = self.hook_manager
            spec.loader.exec_module(module)

        except Exception as e:
            logger.error(f"Failed to load hooks from {py_file}: {e}")

    @property
    def loaded_plugins(self) -> dict[str, PluginManifest]:
        return dict(self._loaded)
