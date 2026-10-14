import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse

from .sessions import SessionStore, SessionView
from .storage import (
    CONFIG_PATH,
    GAME_DIR,
    list_games,
    load_config,
    save_config,
    save_game,
)

def _reply(message: str, status_code: int = 200) -> PlainTextResponse:
    return PlainTextResponse(message.rstrip() + "\n", status_code=status_code)


def _game_lines(game_id: str, game: dict) -> list[str]:
    number_of_calls = sum(len(column["items"]) for column in game["columns"])
    return [f"{game['name']} [{game['word']}] — {number_of_calls} calls", f"ID: {game_id}"]

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
    lines.extend(
        [
            "",
            f"POST /sessions/{session_id}/next   - Draw the next call",
            f"GET  /sessions/{session_id}/history - Full history",
            f"POST /sessions/{session_id}/reset  - Reshuffle and restart",
        ]
    )
    return lines

def create_app(game_directory: Path = GAME_DIR, config_path: Path = CONFIG_PATH) -> FastAPI:
    app = FastAPI(title="Bingo Studio", description="Minimal text-only Bingo API")
    sessions = SessionStore()

    # All JSON game files in this directory are discovered on every request.
    def available_games() -> list[tuple[Path, dict]]:
        return list_games(game_directory)

    def find_game(game_id: str) -> dict:
        for path, game in available_games():
            if path.stem == game_id:
                return game
        raise HTTPException(status_code=404, detail=f"No game found with ID '{game_id}'. Try GET /games.")

    def config() -> dict:
        try:
            return load_config(config_path)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> PlainTextResponse:
        return _reply(f"Error {exc.status_code}: {exc.detail}", exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> PlainTextResponse:
        return _reply(f"Error 422: Invalid request. {exc.errors()}", 422)

    @app.get("/", response_class=PlainTextResponse)
    def index() -> str:
        return (
            "BINGO STUDIO\n"
            "============\n"
            "GET  /config       - View settings\n"
            "PUT  /config       - Update settings (JSON body)\n"
            "GET  /create-game  - Instructions for creating games\n"
            "POST /create-game  - Save a new game from JSON\n"
            "GET  /games        - List game definitions\n"
            "GET  /games/{id}   - View game details\n"
            "GET  /play         - Choose a saved game\n"
            "POST /play/{id}    - Start a draw session\n"
            "GET  /sessions/{session_id} - View the current draw\n"
            "\nUse /docs to send POST/PUT requests, or use curl.\n"
        )

    @app.get("/config", response_class=PlainTextResponse)
    def show_config() -> str:
        settings = config()
        return (
            "CONFIGURATION\n"
            f"History limit: {settings['history_limit']}\n"
            "\nTo update: PUT /config with JSON {\"history_limit\": 10}\n"
        )

    @app.put("/config", response_class=PlainTextResponse)
    def update_config(body: dict) -> str:
        try:
            save_config(body, config_path)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return f"Configuration saved. History limit: {load_config(config_path)['history_limit']}\n"

    @app.get("/create-game", response_class=PlainTextResponse)
    def create_game_help() -> str:
        example = {
            "name": "FLAME Mini",
            "word": "FLAME",
            "free_center": True,
            "columns": [
                {"letter": "F", "items": ["Fire", "Forest"]},
                {"letter": "L", "items": ["Love", "Lantern"]},
                {"letter": "A", "items": ["Adventure", "Autumn"]},
                {"letter": "M", "items": ["Moon", "Mountain"]},
                {"letter": "E", "items": ["Echo", "Emerald"]},
            ],
        }
        return (
            "CREATE GAME\n"
            "POST /create-game with a JSON body like this:\n\n"
            + json.dumps(example, indent=2)
            + "\n\nHeader must be five letters. Each of the five columns "
            "must match its header letter and contain unique entries.\n"
            "Games are saved as JSON files inside games/. "
            "You can also put a valid .json file there yourself.\n"
        )

    @app.post("/create-game", response_class=PlainTextResponse, status_code=201)
    def create_game(body: dict) -> str:
        try:
            path = save_game(body, game_directory)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return f"Saved game: {path.name}\nView: GET /games/{path.stem}\nPlay: POST /play/{path.stem}\n"

    @app.get("/games", response_class=PlainTextResponse)
    def games() -> str:
        entries = available_games()
        if not entries:
            return "SAVED GAMES\nNo games found. Add a JSON file to games/ or POST /create-game.\n"
        lines = ["SAVED GAMES"]
        for path, game in entries:
            lines.append(" - ".join(_game_lines(path.stem, game)))
            lines.append(f"   View: GET /games/{path.stem} | Start: POST /play/{path.stem}")
        return "\n".join(lines) + "\n"

    @app.get("/games/{game_id}", response_class=PlainTextResponse)
    def game_details(game_id: str) -> str:
        game = find_game(game_id)
        lines = _game_lines(game_id, game)
        lines.append(f"Free center: {game['free_center']}")
        for index, column in enumerate(game["columns"], start=1):
            lines.append(f"Column {index} ({column['letter']}): " + ", ".join(column["items"]))
        lines.append(f"\nStart playing: POST /play/{game_id}")
        return "\n".join(lines) + "\n"

    @app.get("/play", response_class=PlainTextResponse)
    def play_menu() -> str:
        entries = available_games()
        lines = ["PLAY GAME", "Choose a saved game:"]
        if not entries:
            lines.append("No games available. POST /create-game to add one.")
        for path, game in entries:
            lines.append(f"{game['name']} [{game['word']}]: POST /play/{path.stem}")
        return "\n".join(lines) + "\n"

    @app.post("/play/{game_id}", response_class=PlainTextResponse, status_code=201)
    def start_game(game_id: str) -> str:
        game = find_game(game_id)
        session_id, view = sessions.start(game)
        return "\n".join(["SESSION STARTED", *_session_lines(session_id, view, config()["history_limit"])]) + "\n"

    def status(session_id: str) -> SessionView:
        try:
            return sessions.status(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc

    @app.get("/sessions/{session_id}", response_class=PlainTextResponse)
    def session_status(session_id: str) -> str:
        return "\n".join(_session_lines(session_id, status(session_id), config()["history_limit"])) + "\n"

    @app.post("/sessions/{session_id}/next", response_class=PlainTextResponse)
    def next_draw(session_id: str) -> str:
        try:
            call, view = sessions.next(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
        headline = f"DRAWN: {call}" if call else "All calls have been drawn. No calls remaining."
        return "\n".join([headline, *_session_lines(session_id, view, config()["history_limit"])]) + "\n"

    @app.get("/sessions/{session_id}/history", response_class=PlainTextResponse)
    def draw_history(session_id: str) -> str:
        view = status(session_id)
        lines = [f"DRAW HISTORY — {view.name} [{view.word}]", f"Session: {session_id}"]
        lines.extend(f"{number}. {call}" for number, call in enumerate(view.history, start=1))
        if not view.history:
            lines.append("(no calls yet)")
        return "\n".join(lines) + "\n"

    @app.post("/sessions/{session_id}/reset", response_class=PlainTextResponse)
    def reset_session(session_id: str) -> str:
        try:
            view = sessions.reset(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
        return "\n".join(["SESSION RESET", *_session_lines(session_id, view, config()["history_limit"])]) + "\n"

    return app

app = create_app()
