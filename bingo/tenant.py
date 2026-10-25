# User-specific JSON stores. No user-controlled pathname reaches the filesystem.

from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request

from .sessions import SessionStore
from .storage import load_game, list_games

@dataclass
class Tenant:
    directory: Path
    shared_default_path: Path

    @property
    def games_dir(self) -> Path:
        return self.directory / "games"

    @property
    def config_path(self) -> Path:
        return self.directory / "config.json"

    @property
    def sessions(self) -> SessionStore:
        # Per-user data is never read or listed from another directory.
        return self._session_store

    def __post_init__(self):
        self._session_store = SessionStore(self.directory / "sessions")

    def games(self):
        # Only the universal BINGO option is shared; other global JSON files are ignored.
        shared = [(Path("default_bingo.json"), load_game(self.shared_default_path))]
        return shared + [(Path("custom-" + path.stem + ".json"), game)
                         for path, game in list_games(self.games_dir)]

    def find_game(self, game_id: str) -> dict:
        for path, game in self.games():
            if path.stem == game_id:
                return game
        raise HTTPException(404, "Game not found.")

def tenant_for(request: Request) -> Tenant:
    # User IDs are generated on the server and loaded from authenticated sessions.
    return request.app.state.tenants[request.state.login.user.id]
