from dataclasses import dataclass
from threading import RLock
from uuid import uuid4

from .game import GameSession

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

class SessionStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: dict[str, GameSession] = {}

    def start(self, game: dict) -> tuple[str, SessionView]:
        session = GameSession(game)
        session_id = uuid4().hex
        with self._lock:
            self._sessions[session_id] = session
            return session_id, self._view(session)

    def status(self, session_id: str) -> SessionView:
        with self._lock:
            return self._view(self._lookup(session_id))

    def next(self, session_id: str) -> tuple[str | None, SessionView]:
        with self._lock:
            session = self._lookup(session_id)
            call = session.next_call()
            return (str(call) if call is not None else None), self._view(session)

    def reset(self, session_id: str) -> SessionView:
        with self._lock:
            session = self._lookup(session_id)
            session.reset()
            return self._view(session)

    def _lookup(self, session_id: str) -> GameSession:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise KeyError("Game session not found. Start a new game at POST /play/{game_id}.") from None

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