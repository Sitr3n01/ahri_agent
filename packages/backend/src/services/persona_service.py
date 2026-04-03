"""
Persona Service - Gerenciamento de personas.
Portar de PersonaManager (brain.py linhas 377-575).
"""
import logging
import shutil
from pathlib import Path
from typing import Optional

import yaml

from src.config import get_settings
from src.models.schemas import (
    PersonaSummary, PersonaDetail, PersonaTheme,
    UpdatePersonaRequest, CreatePersonaRequest,
)

logger = logging.getLogger("ahri.persona")

# Estado global: persona ativa (single-user)
_active_persona: str = "ahri"


def get_active_persona() -> str:
    return _active_persona


def set_active_persona(name: str) -> str:
    global _active_persona
    _active_persona = name.lower()
    return _active_persona


def _parse_persona_file(persona_dir: Path) -> dict:
    """Parse persona.md com YAML frontmatter opcional."""
    persona_file = persona_dir / "persona.md"
    if not persona_file.exists():
        return {"name": persona_dir.name, "display_name": persona_dir.name.title(), "identity_text": ""}

    content = persona_file.read_text(encoding="utf-8")

    # Tenta extrair YAML frontmatter (---\n...\n---)
    frontmatter = {}
    identity_text = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
                identity_text = parts[2].strip()
            except yaml.YAMLError:
                identity_text = content

    return {
        "name": frontmatter.get("name", persona_dir.name),
        "display_name": frontmatter.get("display_name", persona_dir.name.replace("_", " ").title()),
        "archetype": frontmatter.get("archetype", ""),
        "universe": frontmatter.get("universe", ""),
        "voice_language": frontmatter.get("voice_language", "pt-br"),
        "theme": frontmatter.get("theme", {}),
        "spotify_genres": frontmatter.get("spotify_genres", []),
        "identity_text": identity_text,
    }


def list_personas() -> list[PersonaSummary]:
    """Lista todas as personas disponíveis."""
    settings = get_settings()
    personas_dir = settings.personas_dir

    if not personas_dir.exists():
        return []

    result = []
    for p_dir in sorted(personas_dir.iterdir()):
        if not p_dir.is_dir():
            continue

        persona_file = p_dir / "persona.md"
        if not persona_file.exists():
            continue

        try:
            data = _parse_persona_file(p_dir)
            theme_data = data.get("theme", {})

            result.append(PersonaSummary(
                name=data["name"],
                display_name=data["display_name"],
                archetype=data.get("archetype", ""),
                universe=data.get("universe", ""),
                theme=PersonaTheme(
                    # Returning empty string means "no custom override" — frontend mergePersonaTheme
                    # will fall back to the per-persona static theme instead of Ahri's defaults.
                    primary=theme_data.get("primary", ""),
                    secondary=theme_data.get("secondary", ""),
                    shadow=theme_data.get("shadow", ""),
                    glow=theme_data.get("glow", ""),
                    avatar=theme_data.get("avatar", ""),
                    background=theme_data.get("background", ""),
                    background_mobile=theme_data.get("background_mobile", ""),
                ),
            ))
        except Exception as e:
            logger.warning(f"Failed to parse persona '{p_dir.name}': {e}")
            continue

    return result


def get_persona_detail(name: str) -> Optional[PersonaDetail]:
    """Detalhes completos de uma persona."""
    settings = get_settings()
    persona_dir = settings.personas_dir / name.lower().replace(" ", "_")

    if not persona_dir.exists():
        return None

    data = _parse_persona_file(persona_dir)
    theme_data = data.get("theme", {})

    # Contagens
    knowledge_dir = persona_dir / "knowledge"
    history_dir = persona_dir / "history"
    rag_docs_dir = persona_dir / "rag_docs"

    knowledge_count = len(list(knowledge_dir.glob("*.md"))) if knowledge_dir.exists() else 0
    session_count = len(list(history_dir.glob("*.json"))) if history_dir.exists() else 0
    has_lore = any(rag_docs_dir.glob("*.*")) if rag_docs_dir.exists() else False

    return PersonaDetail(
        name=data["name"],
        display_name=data["display_name"],
        archetype=data.get("archetype", ""),
        universe=data.get("universe", ""),
        identity_text=data["identity_text"],
        spotify_genres=data.get("spotify_genres", []),
        has_lore=has_lore,
        knowledge_count=knowledge_count,
        session_count=session_count,
        theme=PersonaTheme(
            # Returning empty string means "no custom override" — frontend mergePersonaTheme
            # will fall back to the per-persona static theme instead of Ahri's defaults.
            primary=theme_data.get("primary", ""),
            secondary=theme_data.get("secondary", ""),
            shadow=theme_data.get("shadow", ""),
            glow=theme_data.get("glow", ""),
            avatar=theme_data.get("avatar", ""),
            background=theme_data.get("background", ""),
            background_mobile=theme_data.get("background_mobile", ""),
        ),
    )


def load_persona_identity(name: str) -> str:
    """Carrega o texto de identidade (persona.md) para uso no prompt."""
    settings = get_settings()
    persona_dir = settings.personas_dir / name.lower().replace(" ", "_")
    data = _parse_persona_file(persona_dir)
    return data.get("identity_text", "Identity: Assistant.")


def load_persona_knowledge(name: str) -> str:
    """Carrega knowledge.md legado (se existir)."""
    settings = get_settings()
    knowledge_file = settings.personas_dir / name.lower().replace(" ", "_") / "knowledge.md"
    if knowledge_file.exists():
        return knowledge_file.read_text(encoding="utf-8")
    return ""


def _write_persona_file(persona_dir: Path, data: dict, identity_text: str) -> None:
    """Updates the persona.md file with new frontmatter and content."""
    persona_file = persona_dir / "persona.md"

    # Clean up data to only include frontmatter fields
    frontmatter = {
        "name": data.get("name"),
        "display_name": data.get("display_name"),
        "archetype": data.get("archetype"),
        "universe": data.get("universe"),
        "voice_language": data.get("voice_language", "pt-br"),
        "theme": data.get("theme", {}),
        "spotify_genres": data.get("spotify_genres", []),
    }

    # Clean None values recursively or just top level?
    # Top level is fine for now
    frontmatter = {k: v for k, v in frontmatter.items() if v is not None}
    
    # If theme is dict, clean it too
    if isinstance(frontmatter.get("theme"), dict):
        frontmatter["theme"] = {k: v for k, v in frontmatter["theme"].items() if v is not None}

    with open(persona_file, "w", encoding="utf-8") as f:
        f.write("---\n")
        yaml.dump(frontmatter, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        f.write("---\n")
        f.write(identity_text)


import base64

def update_persona(name: str, update_data: UpdatePersonaRequest) -> Optional[PersonaDetail]:
    """Updates persona attributes and identity."""
    settings = get_settings()
    persona_slug = name.lower().replace(" ", "_")
    persona_dir = settings.personas_dir / persona_slug

    if not persona_dir.exists():
        return None

    # Load existing data to merge
    existing_data = _parse_persona_file(persona_dir)
    theme = existing_data.get("theme", {})
    if not isinstance(theme, dict):
        theme = {}
    
    # Handle Image Uploads (Base64)
    for img_field, theme_key in [("avatar_base64", "avatar"), ("background_base64", "background")]:
        b64_data = getattr(update_data, img_field)
        if b64_data:
            try:
                # Basic parsing of data:image/xxx;base64,yyy
                if "," in b64_data:
                    header, encoded = b64_data.split(",", 1)
                else:
                    header, encoded = None, b64_data
                
                img_bytes = base64.b64decode(encoded)
                
                # Determine extension
                ext = "png"
                if header:
                    if "image/jpeg" in header: ext = "jpg"
                    elif "image/webp" in header: ext = "webp"
                
                filename = f"{theme_key}.{ext}"
                file_path = persona_dir / filename
                file_path.write_bytes(img_bytes)
                
                # Update theme path (relative to static root /data)
                theme[theme_key] = f"data/personas/{persona_slug}/{filename}"
                logger.info(f"Saved {theme_key} for persona '{name}' at {file_path}")
            except Exception as e:
                logger.error(f"Failed to process {img_field} for persona '{name}': {e}")

    # Merge updates
    new_data = existing_data.copy()
    
    if update_data.display_name is not None:
        new_data["display_name"] = update_data.display_name
    if update_data.archetype is not None:
        new_data["archetype"] = update_data.archetype
    if update_data.universe is not None:
        new_data["universe"] = update_data.universe
    if update_data.voice_language is not None:
        new_data["voice_language"] = update_data.voice_language
        
    # Theme updates
    if update_data.primary_color:
        theme["primary"] = update_data.primary_color
    if update_data.secondary_color:
        theme["secondary"] = update_data.secondary_color
        
    new_data["theme"] = theme
    
    # Identity text
    identity_text = update_data.identity_text if update_data.identity_text is not None else existing_data.get("identity_text", "")
    
    # Write back
    _write_persona_file(persona_dir, new_data, identity_text)

    return get_persona_detail(name)


def create_persona(request: CreatePersonaRequest) -> PersonaDetail:
    """Creates a new persona with directory structure and persona.md."""
    settings = get_settings()
    persona_dir = settings.personas_dir / request.name

    if persona_dir.exists():
        raise ValueError(f"Persona '{request.name}' already exists")

    # Create directory structure
    persona_dir.mkdir(parents=True)
    (persona_dir / "rag_docs").mkdir()
    (persona_dir / "knowledge").mkdir()

    # Build persona data
    data = {
        "name": request.name,
        "display_name": request.display_name,
        "archetype": request.archetype,
        "universe": request.universe,
        "voice_language": request.voice_language,
        "theme": {
            "primary": request.primary_color,
            "secondary": request.secondary_color,
        },
        "spotify_genres": request.spotify_genres,
    }

    identity_text = request.identity_text or f"# {request.display_name}\n\nA new persona."

    _write_persona_file(persona_dir, data, identity_text)
    logger.info(f"Created persona '{request.name}' at {persona_dir}")

    return get_persona_detail(request.name)


def delete_persona(name: str) -> bool:
    """Deletes a persona and all its files. Returns True if deleted."""
    if name.lower() == "ahri":
        return False

    settings = get_settings()
    persona_dir = settings.personas_dir / name.lower().replace(" ", "_")

    if not persona_dir.exists():
        return False

    shutil.rmtree(persona_dir)
    logger.info(f"Deleted persona '{name}' from {persona_dir}")

    # Reset active persona if the deleted one was active
    global _active_persona
    if _active_persona == name.lower():
        _active_persona = "ahri"

    return True
