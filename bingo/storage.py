import json
from pathlib import Path
import re

from .game import validate_game

ROOT = Path(__file__).resolve().parent.parent
GAME_DIR = ROOT / "games"
CONFIG_PATH = ROOT / "config.json"
DEFAULT_CONFIG = {"history_limit": 5}

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
    # Atomic replace prevents leaving behind incomplete JSON if interrupted.
    temp = path.with_suffix(".tmp")
    try:
        temp.write_text(json.dumps(game, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()
    return path

def load_config(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        return DEFAULT_CONFIG.copy()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid configuration: {exc}") from exc
    if not isinstance(value, dict) or type(value.get("history_limit")) is not int or not 0 <= value["history_limit"] <= 50:
        raise ValueError("Configuration must have an integer 'history_limit' from 0 to 50.")
    return {"history_limit": value["history_limit"]}

def save_config(config: dict, path: Path = CONFIG_PATH) -> None:
    limit = config.get("history_limit")
    if type(limit) is not int or not 0 <= limit <= 50:
        raise ValueError("history_limit must be an integer between 0 and 50.")
    path.write_text(json.dumps({"history_limit": limit}, indent=2) + "\n", encoding="utf-8")