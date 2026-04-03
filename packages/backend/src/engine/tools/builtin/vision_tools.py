"""
Vision tools - Image analysis via Gemini Vision.
Replaces VisionWorker.
"""
import json
import base64
from pathlib import Path
from typing import Any

from ..base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)


@build_tool(
    name="image_analyze",
    description="Analyze an image for content, objects, text (OCR), or visual descriptions. Supports local files and base64.",
    category=ToolCategory.VISION,
    execution_mode=ExecutionMode.SERIAL,  # Vision calls are expensive
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Path to local image file (PNG, JPG, WEBP)",
            },
            "image_base64": {
                "type": "string",
                "description": "Base64-encoded image data (alternative to path)",
            },
            "analysis_type": {
                "type": "string",
                "enum": ["describe", "ocr", "objects", "analyze"],
                "description": "Type of analysis to perform",
                "default": "describe",
            },
            "question": {
                "type": "string",
                "description": "Specific question about the image (optional)",
            },
        },
        "required": [],
    },
)
async def image_analyze(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    image_path = args.get("image_path", "")
    image_b64 = args.get("image_base64", "")
    analysis_type = args.get("analysis_type", "describe")
    question = args.get("question", "")

    # Get image data
    if image_path:
        p = Path(image_path)
        if not p.exists():
            return json.dumps({"error": f"Image not found: {image_path}"})
        image_b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp", ".gif": "image/gif"}.get(p.suffix.lower(), "image/png")
    elif not image_b64:
        return json.dumps({"error": "Provide image_path or image_base64"})
    else:
        mime = "image/png"  # Default for base64

    # Build analysis prompt
    prompts = {
        "describe": "Describe this image in detail. What do you see?",
        "ocr": "Extract ALL text visible in this image. Return the text exactly as written.",
        "objects": "List all distinct objects visible in this image with their approximate positions.",
        "analyze": "Provide a comprehensive analysis of this image including: content, mood, colors, composition, and any notable details.",
    }
    prompt = question or prompts.get(analysis_type, prompts["describe"])

    # Call vision-capable model
    # Use "best" or "flash" since they support vision
    vision_model = "flash"  # Gemini Flash supports vision
    try:
        # Build multimodal message for Gemini
        messages = [{
            "role": "user",
            "content": prompt,
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": image_b64}},
            ],
        }]

        result = await ctx.model_registry.call(
            model_or_alias=vision_model,
            messages=messages,
        )

        return json.dumps({
            "analysis_type": analysis_type,
            "result": result.content if hasattr(result, 'content') else str(result),
            "image_path": image_path or "(base64 input)",
        })
    except Exception as e:
        return json.dumps({"error": f"Vision analysis failed: {e}"})


VISION_TOOLS = [image_analyze]
