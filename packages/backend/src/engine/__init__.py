"""
Ahri V4 Engine - Modular agent execution engine.

Inspired by Claude Code (Anthropic) architecture patterns:
- Async generator query loop
- Tool registry with concurrent/serial partitioning
- Permission system in layers
- Hook system (event-driven)
- Agent spawning with isolated contexts
- Plugin system
"""
