# Disk-backed draw sessions: one JSON snapshot per session.

# The JSON files, not a Python cache, are the source of truth.
# A thread lock serializes drawing for a single server process.
# Use one Uvicorn worker only.

import json
from dataclasses import dataclass
from pathlib import Path
import re
from threading import RLock
from uuid import uuid4

from .game import Call, GameSession
from .storage import SESSION_DIR, write_json_atomic

_SESSION_ID = re.compile(r"[0-9a-f]{32}\Z")


@dataclass(frozen=True)
class SessionView:
    name: str
    word: str
    current: str | None
    previous: str | None
    history: tuple[str, ...]
    total: int
    remaining: int

    @property
    def drawn(self) -> int:
        return self.total - self.remaining


@dataclass(frozen=True)
class MatrixCell:
    value: str
    drawn: bool
    latest: bool


@dataclass(frozen=True)
class MatrixColumn:
    letter: str
    cells: tuple[MatrixCell, ...]


@dataclass(frozen=True)
class MatrixView:
    name: str
    word: str
    columns: tuple[MatrixColumn, ...]
    drawn: int
    total: int
    current: str | None

    @property
    def remaining(self) -> int:
        return self.total - self.drawn

    @property
    def rows(self) -> int:
        return max(len(column.cells) for column in self.columns)


class SessionStore:
    def __init__(self, directory: Path = SESSION_DIR) -> None:
        self.directory = Path(directory)
        self._lock = RLock()

    def _path(self, session_id: str) -> Path:
        if not _SESSION_ID.fullmatch(session_id):
            raise KeyError("Game session not found.")
        return self.directory / f"{session_id}.json"

    def _load(self, session_id: str) -> GameSession:
        try:
            content = json.loads(self._path(session_id).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise KeyError("Game session not found. Start a new game or view saved sessions.") from None
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Saved session {session_id} is unreadable: {exc}") from exc
        try:
            return GameSession.from_snapshot(content)
        except ValueError as exc:
            raise ValueError(f"Saved session {session_id} is invalid: {exc}") from exc

    def _save(self, session_id: str, session: GameSession) -> None:
        write_json_atomic(self._path(session_id), session.snapshot())

    def start(self, game: dict) -> tuple[str, SessionView]:
        session = GameSession(game)
        with self._lock:
            session_id = uuid4().hex
            self._save(session_id, session)
            return session_id, self._view(session)

    def status(self, session_id: str) -> SessionView:
        with self._lock:
            return self._view(self._load(session_id))

    def overview(self, session_id: str) -> tuple[SessionView, MatrixView]:
        """Return caller information and the matrix from the same disk snapshot."""
        with self._lock:
            session = self._load(session_id)
            return self._view(session), self._matrix_view(session)

    def matrix(self, session_id: str) -> MatrixView:
        """Read the complete call pool and drawn flags from one saved snapshot."""
        with self._lock:
            return self._matrix_view(self._load(session_id))

    def list_sessions(self) -> list[tuple[str, SessionView]]:
        with self._lock:
            if not self.directory.exists():
                return []
            result = []
            for path in sorted(self.directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                if _SESSION_ID.fullmatch(path.stem):
                    result.append((path.stem, self._view(self._load(path.stem))))
            return result

    def next(self, session_id: str) -> tuple[str | None, SessionView]:
        with self._lock:
            session = self._load(session_id)
            call = session.next_call()
            if call is not None:
                self._save(session_id, session)
            return (str(call) if call is not None else None), self._view(session)

    def reset(self, session_id: str) -> SessionView:
        with self._lock:
            session = self._load(session_id)
            session.reset()
            self._save(session_id, session)
            return self._view(session)

    def delete(self, session_id: str) -> None:
        with self._lock:
            try:
                self._path(session_id).unlink()
            except FileNotFoundError:
                raise KeyError("Game session not found.") from None

    def clear(self) -> int:
        """Delete only recognized session JSONs. Never touch game definitions."""
        with self._lock:
            if not self.directory.exists():
                return 0
            paths = [p for p in self.directory.glob("*.json") if _SESSION_ID.fullmatch(p.stem)]
            for path in paths:
                path.unlink()
            return len(paths)

    @staticmethod
    def _matrix_view(session: GameSession) -> MatrixView:
        # Comparing full Call objects also distinguishes repeated header letters
        # (e.g. APPLE) and repeated values in different columns.
        history = session.history
        called = set(history)
        latest = history[-1] if history else None
        columns = tuple(
            MatrixColumn(
                letter=column["letter"],
                cells=tuple(
                    MatrixCell(value=entry.value, drawn=entry in called, latest=entry == latest)
                    for entry in (Call(index, column["letter"], value) for value in column["items"])
                ),
            )
            for index, column in enumerate(session.game["columns"])
        )
        return MatrixView(
            name=session.game["name"],
            word=session.game["word"],
            columns=columns,
            drawn=session.cursor,
            total=len(session.deck),
            current=str(latest) if latest else None,
        )

    @staticmethod
    def _view(session: GameSession) -> SessionView:
        history = tuple(str(call) for call in session.history)
        return SessionView(
            name=session.game["name"],
            word=session.game["word"],
            current=history[-1] if history else None,
            previous=history[-2] if len(history) > 1 else None,
            history=history,
            total=len(session.deck),
            remaining=session.remaining,
        )