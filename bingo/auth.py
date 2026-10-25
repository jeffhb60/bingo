# Invite-only accounts, Argon2id credentials and revocable SQLite-backed sessions.
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError, VerificationError

PH = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, hash_len=32, salt_len=16, type=Type.ID)
USER_RE = re.compile(r"[a-z][a-z0-9_.-]{2,39}\Z")
SESSION_SECONDS = 12 * 60 * 60
# Opaque cookie never stored as plaintext. Separate CSRF secret tied to a server session.

def digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()

def valid_password(password: str) -> None:
    if not 12 <= len(password) <= 128 or len(password.encode("utf-8")) > 512:
        raise ValueError("Password must contain 12 to 128 characters (up to 512 UTF-8 bytes).")

@dataclass(frozen=True)
class User:
    id: str
    username: str

@dataclass(frozen=True)
class LoginSession:
    user: User
    csrf: str

class AuthStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Do not allow auth state to be accidentally committed as part of the project.
        self._setup()
        self._dummy_hash = PH.hash("invalid-password-used-for-timing-balance")

    @contextmanager
    def _db(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _setup(self):
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS login_sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    csrf TEXT NOT NULL, expires_at INTEGER NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS ix_session_user ON login_sessions(user_id);
                CREATE TABLE IF NOT EXISTS failures (
                    username TEXT NOT NULL, ip TEXT NOT NULL,
                    attempts INTEGER NOT NULL, window_at INTEGER NOT NULL,
                    blocked_until INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(username, ip)
                );
            """)

    def add_user(self, username: str, password: str) -> User:
        username = username.strip().lower()
        if not USER_RE.fullmatch(username):
            raise ValueError("Username must be 3–40 characters: lowercase letters, digits, dot, underscore or hyphen; start with a letter.")
        valid_password(password)
        user = User(uuid4().hex, username)
        try:
            with self._db() as db:
                db.execute("INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
                           (user.id, user.username, PH.hash(password)))
        except sqlite3.IntegrityError as exc:
            raise ValueError("That username already exists.") from exc
        return user

    def list_users(self):
        with self._db() as db:
            return [(row["username"], bool(row["enabled"])) for row in db.execute("SELECT username,enabled FROM users ORDER BY username")]

    def change_password(self, username: str, password: str):
        valid_password(password)
        with self._db() as db:
            row = db.execute("SELECT id FROM users WHERE username=?", (username.lower(),)).fetchone()
            if row is None:
                raise ValueError("User not found.")
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (PH.hash(password), row["id"]))
            db.execute("DELETE FROM login_sessions WHERE user_id=?", (row["id"],))

    def disable_user(self, username: str):
        with self._db() as db:
            row = db.execute("SELECT id FROM users WHERE username=?", (username.lower(),)).fetchone()
            if row is None:
                raise ValueError("User not found.")
            db.execute("UPDATE users SET enabled=0 WHERE id=?", (row["id"],))
            db.execute("DELETE FROM login_sessions WHERE user_id=?", (row["id"],))

    def authenticate(self, username: str, password: str, ip: str) -> User | None:
        username = username.strip().lower()[:80]
        ip = ip[:80]
        now = int(time.time())
        with self._db() as db:
            rate = db.execute("SELECT * FROM failures WHERE username=? AND ip=?", (username, ip)).fetchone()
            if rate and rate["blocked_until"] > now:
                return None
            row = db.execute("SELECT * FROM users WHERE username=? AND enabled=1", (username,)).fetchone()
            stored = row["password_hash"] if row else self._dummy_hash
            try:
                success = PH.verify(stored, password[:512])
            except (VerifyMismatchError, VerificationError, ValueError):
                success = False
            if row is not None and success:
                db.execute("DELETE FROM failures WHERE username=? AND ip=?", (username, ip))
                if PH.check_needs_rehash(stored):
                    db.execute("UPDATE users SET password_hash=? WHERE id=?", (PH.hash(password), row["id"]))
                return User(row["id"], row["username"])
            attempts = rate["attempts"] + 1 if rate and now - rate["window_at"] < 900 else 1
            window_at = rate["window_at"] if rate and now - rate["window_at"] < 900 else now
            blocked_until = now + 900 if attempts >= 5 else 0
            db.execute("""INSERT INTO failures VALUES(?,?,?,?,?)
                       ON CONFLICT(username,ip) DO UPDATE SET attempts=excluded.attempts,
                       window_at=excluded.window_at, blocked_until=excluded.blocked_until""",
                       (username, ip, attempts, window_at, blocked_until))
            return None

    def new_session(self, user: User) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        now = int(time.time())
        with self._db() as db:
            db.execute("DELETE FROM login_sessions WHERE expires_at<?", (now,))
            db.execute("INSERT INTO login_sessions VALUES (?,?,?,?)", (digest(token), user.id, csrf, now + SESSION_SECONDS))
        return token, csrf

    def session(self, token: str | None) -> LoginSession | None:
        if not token or len(token) > 128:
            return None
        with self._db() as db:
            row = db.execute("""SELECT users.id,users.username,login_sessions.csrf
                    FROM login_sessions JOIN users ON users.id=login_sessions.user_id
                    WHERE token_hash=? AND expires_at>? AND users.enabled=1""",
                    (digest(token), int(time.time()))).fetchone()
            return LoginSession(User(row["id"], row["username"]), row["csrf"]) if row else None

    def revoke(self, token: str | None):
        if token and len(token) <= 128:
            with self._db() as db:
                db.execute("DELETE FROM login_sessions WHERE token_hash=?", (digest(token),))

def cookie_name(secure: bool) -> str:
    return "__Host-bingo_session" if secure else "bingo_session"

def add_session_cookie(response, token: str, secure: bool):
    response.set_cookie(cookie_name(secure), token, max_age=SESSION_SECONDS,
                        path="/", httponly=True, secure=secure, samesite="strict")

def matches_csrf(expected: str, candidate: str | None) -> bool:
    return bool(candidate and hmac.compare_digest(expected, candidate))