# Plain-text API plus the separate unstyled browser UI in ui.py.

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse

from .sessions import SessionStore, SessionView
from .storage import CONFIG_PATH, GAME_DIR, list_games, load_config, save_config, save_game
from .ui import build_ui_router

def _reply(message: str, status_code: int = 200) -> PlainTextResponse:
    return PlainTextResponse(message.rstrip() + "\n", status_code=status_code)

def _game_lines(game_id: str, game: dict) -> list[str]:
    calls = sum(len(column["items"]) for column in game["columns"])
    return [f"{game['name']} [{game['word']}] — {calls} calls", f"ID: {game_id}"]

def _session_lines(session_id: str, view: SessionView, limit: int) -> list[str]:
    lines = [
        f"Playing: {view.name} [{view.word}]",
        f"Session: {session_id}",
        f"Previous draw: {view.previous or '(none)'}",
        f"Current draw: {view.current or '(none yet)'}",
        f"Progress: {view.drawn} / {view.total}",
        f"Remaining: {view.remaining}",
    ]
    if limit:
        recent = view.history[-limit:]
        lines.append("Recent draws: " + (", ".join(recent) if recent else "(none yet)"))
    lines.extend([
        "",
        f"GET /ui/sessions/{session_id} - Browser controls",
        f"POST /sessions/{session_id}/next - Draw next call",
        f"GET /sessions/{session_id}/history - Full history",
        f"POST /sessions/{session_id}/reset - Reshuffle and restart",
    ])
    return lines

# Create a testable app; session files default to sibling of games/.
def create_app(
    game_directory: Path = GAME_DIR,
    config_path: Path = CONFIG_PATH,
    session_directory: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Bingo Studio", description="JSON-based Bingo caller with minimal HTML forms")
    sessions = SessionStore(session_directory or Path(game_directory).parent / "sessions")

    def available_games() -> list[tuple[Path, dict]]:
        return list_games(game_directory)

    def find_game(game_id: str) -> dict:
        for path, game in available_games():
            if path.stem == game_id:
                return game
        raise HTTPException(404, f"No game found with ID '{game_id}'. Try GET /games.")

    def config() -> dict:
        try:
            return load_config(config_path)
        except ValueError as exc:
            raise HTTPException(500, str(exc)) from exc

    def session_action(callback, session_id: str):
        try:
            return callback(session_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc.args[0])) from exc

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> PlainTextResponse:
        return _reply(f"Error {exc.status_code}: {exc.detail}", exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> PlainTextResponse:
        return _reply(f"Error 422: Invalid request. {exc.errors()}", 422)

    @app.exception_handler(ValueError)
    async def invalid_saved_session(request: Request, exc: ValueError) -> PlainTextResponse:
        return _reply(f"Error 500: {exc}", 500)

    @app.get("/config", response_class=PlainTextResponse)
    def show_config() -> str:
        settings = config()
        return f"CONFIGURATION\nHistory limit: {settings['history_limit']}\n\nTo update: PUT /config with JSON {{\"history_limit\": 10}}\n"

    @app.put("/config", response_class=PlainTextResponse)
    def update_config(body: dict) -> str:
        try:
            save_config(body, config_path)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return f"Configuration saved. History limit: {config()['history_limit']}\n"

    @app.get("/create-game", response_class=PlainTextResponse)
    def create_game_help() -> str:
        example = {
            "name": "FLAME Mini", "word": "FLAME", "free_center": True,
            "columns": [
                {"letter": letter, "items": items} for letter, items in zip(
                    "FLAME", [["Fire", "Forest"], ["Love", "Lantern"], ["Adventure", "Autumn"],
                              ["Moon", "Mountain"], ["Echo", "Emerald"]]
                )
            ],
        }
        return (
            "CREATE GAME\nPOST /create-game with a JSON body like this:\n\n"
            + json.dumps(example, indent=2)
            + "\n\nHeader must be five letters. Each column must match its header letter and have unique entries.\n"
            "Games are saved in games/*.json; manually placed JSON files also work.\n"
        )

    @app.post("/create-game", response_class=PlainTextResponse, status_code=201)
    def create_game(body: dict) -> str:
        try:
            path = save_game(body, game_directory)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return (
            f"Saved game: {path.name}\nView: GET /games/{path.stem}\n"
            f"Preview: GET /play/{path.stem}\nStart: POST /play/{path.stem}\n"
        )

    @app.get("/games", response_class=PlainTextResponse)
    def games() -> str:
        entries = available_games()
        if not entries:
            return "SAVED GAMES\nNo games found. Add a JSON file to games/ or POST /create-game.\n"
        lines = ["SAVED GAMES"]
        for path, game in entries:
            lines.extend([
                " - ".join(_game_lines(path.stem, game)),
                f"   View: GET /games/{path.stem} | Preview: GET /play/{path.stem}",
                f"   Start: POST /play/{path.stem} (or use browser: /ui/games)",
            ])
        return "\n".join(lines) + "\n"

    @app.get("/games/{game_id}", response_class=PlainTextResponse)
    def game_details(game_id: str) -> str:
        game = find_game(game_id)
        lines = _game_lines(game_id, game)
        lines.append(f"Free center: {game['free_center']}")
        for i, column in enumerate(game["columns"], start=1):
            lines.append(f"Column {i} ({column['letter']}): " + ", ".join(column["items"]))
        lines.append(f"\nPreview: GET /play/{game_id}")
        lines.append(f"Start playing: POST /play/{game_id}")
        return "\n".join(lines) + "\n"

    @app.get("/play", response_class=PlainTextResponse)
    def play_menu() -> str:
        lines = ["PLAY GAME", "Choose a saved game (or open /ui/games in your browser):"]
        entries = available_games()
        if not entries:
            lines.append("No games available. POST /create-game to add one.")
        for path, game in entries:
            lines.append(f"{game['name']} [{game['word']}]: GET /play/{path.stem}")
        return "\n".join(lines) + "\n"

    @app.post("/play/{game_id}", response_class=PlainTextResponse, status_code=201)
    def start_game(game_id: str) -> str:
        session_id, view = sessions.start(find_game(game_id))
        return "\n".join(["SESSION STARTED", *_session_lines(session_id, view, config()["history_limit"])]) + "\n"

    @app.get("/sessions", response_class=PlainTextResponse)
    def saved_sessions() -> str:
        entries = sessions.list_sessions()
        lines = ["SAVED SESSIONS"]
        if not entries:
            lines.append("No saved sessions. Start a new game with POST /play/{game_id}.")
        for sid, view in entries:
            lines.append(f"{sid}: {view.name} [{view.word}] — {view.drawn}/{view.total} drawn")
        lines.append("Browser resume/clear controls: GET /ui/sessions")
        return "\n".join(lines) + "\n"

    @app.get("/sessions/{session_id}", response_class=PlainTextResponse)
    def session_status(session_id: str) -> str:
        view = session_action(sessions.status, session_id)
        return "\n".join(_session_lines(session_id, view, config()["history_limit"])) + "\n"

    @app.post("/sessions/{session_id}/next", response_class=PlainTextResponse)
    def next_draw(session_id: str) -> str:
        call, view = session_action(sessions.next, session_id)
        headline = f"DRAWN: {call}" if call else "All calls have been drawn. No calls remaining."
        return "\n".join([headline, *_session_lines(session_id, view, config()["history_limit"])]) + "\n"

    @app.get("/sessions/{session_id}/history", response_class=PlainTextResponse)
    def draw_history(session_id: str) -> str:
        view = session_action(sessions.status, session_id)
        lines = [f"DRAW HISTORY — {view.name} [{view.word}]", f"Session: {session_id}"]
        lines.extend(f"{i}. {call}" for i, call in enumerate(view.history, start=1))
        if not view.history:
            lines.append("(no calls yet)")
        return "\n".join(lines) + "\n"

    @app.post("/sessions/{session_id}/reset", response_class=PlainTextResponse)
    def reset_session(session_id: str) -> str:
        view = session_action(sessions.reset, session_id)
        return "\n".join(["SESSION RESET", *_session_lines(session_id, view, config()["history_limit"])]) + "\n"

    @app.post("/sessions/{session_id}/delete", response_class=PlainTextResponse)
    def delete_session(session_id: str) -> str:
        session_action(sessions.delete, session_id)
        return f"Deleted session {session_id}. Game definitions are unchanged.\n"

    @app.post("/sessions/clear", response_class=PlainTextResponse)
    def clear_sessions() -> str:
        count = sessions.clear()
        return f"Cleared {count} saved session(s). Game definitions are unchanged.\n"

    app.include_router(build_ui_router(sessions, available_games, find_game))
    return app

app = create_app()