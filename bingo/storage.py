# Read/write human-editable .json definitions. Using flat-file customization instead of database.

import json
from pathlib import Path
import re
from uuid import uuid4

from .game import validate_game

ROOT = Path(__file__).resolve().parent.parent
GAME_DIR = ROOT / "games"
SESSION_DIR = ROOT / "sessions"
CONFIG_PATH = ROOT / "config.json"
DEFAULT_CONFIG = {
    "history_limit": 5,
    "site_title": "Bingo Studio",
    "tagline": "Your game night, made simple.",
    "accent": "lime",
}
ACCENTS = {"lime": "#c4fa74", "sky": "#7dd3fc", "rose": "#fda4af", "violet": "#c4b5fd", "amber": "#ffce73"}

def validate_config(config: dict, *, current: dict | None = None) -> dict:
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object.")
    result = {**DEFAULT_CONFIG, **(current or {}), **config}
    limit = result.get("history_limit")
    if type(limit) is not int or not 0 <= limit <= 50:
        raise ValueError("history_limit must be an integer between 0 and 50.")
    for key, maximum in (("site_title", 60), ("tagline", 140)):
        value = result.get(key)
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
            raise ValueError(f"{key} must contain 1 to {maximum} characters.")
        result[key] = value.strip()
    if result.get("accent") not in ACCENTS:
        raise ValueError("accent must be lime, sky, rose, violet, or amber.")
    return {key: result[key] for key in DEFAULT_CONFIG}

def load_game(path: Path) -> dict:
    try:
        with Path(path).open(encoding="utf-8") as stream:
            return validate_game(json.load(stream))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read game file '{path}': {exc}") from exc

def list_games(directory: Path = GAME_DIR) -> list[tuple[Path, dict]]:
    directory.mkdir(parents=True, exist_ok=True)
    games = []
    for path in sorted(directory.glob("*.json")):
        try:
            games.append((path, load_game(path)))
        except ValueError as exc:
            print(f"Skipping invalid game: {exc}")
    return games

def save_game(data: dict, directory: Path = GAME_DIR) -> Path:
    game = validate_game(data)
    directory.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", game["name"].lower()).strip("_") or "game"
    path = directory / f"{slug}.json"
    counter = 2
    while path.exists():
        path = directory / f"{slug}_{counter}.json"
        counter += 1
    write_json_atomic(path, game)
    return path

def load_config(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        return DEFAULT_CONFIG.copy()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid configuration: {exc}") from exc
    return validate_config(value)

def save_config(config: dict, path: Path = CONFIG_PATH) -> None:
    current = load_config(path)
    write_json_atomic(path, validate_config(config, current=current))

# Save JSON via a temporary file and atomic replacement (single-host storage).
def write_json_atomic(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
