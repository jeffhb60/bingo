# Plain, unstyled HTML forms for browser play; no CSS or JavaScript
# More styling to be added later. Testing for functionality before building out frontend.

import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .sessions import SessionStore, SessionView
from .storage import ACCENTS, load_config, save_config, save_game

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
TEMPLATES.env.filters["url_path"] = lambda value: quote(str(value), safe="")

def _page(request: Request, template: str, **context):
    return TEMPLATES.TemplateResponse(request=request, name=template, context=context)

def _status(store: SessionStore, session_id: str) -> SessionView:
    try:
        return store.status(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0])) from exc

def _action(callback, session_id: str):
    try:
        return callback(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0])) from exc

def _column_fields(word: str, values: list[str]) -> list[dict]:
    # Name inputs by position, not by letter: APPLE contains two P columns.
    labels = word.upper() if len(word) == 5 and word.isascii() and word.isalpha() else "BINGO"
    return [{"number": i + 1, "index": i, "letter": labels[i], "text": values[i]} for i in range(5)]

def build_ui_router(store: SessionStore, available_games, find_game, *, game_directory: Path, config_path: Path) -> APIRouter:
    router = APIRouter()

    def page(request: Request, template: str, **context):
        branding = load_config(config_path)
        return _page(request, template, branding=branding,
                     accent_color=ACCENTS[branding["accent"]], **context)

    @router.get("/", response_class=HTMLResponse)
    def home(request: Request):
        games = available_games()
        sessions = store.list_sessions()
        return page(request, "home.html", active="home", game_count=len(games), session_count=len(sessions), recent_sessions=sessions[:3])

    @router.get("/ui/games", response_class=HTMLResponse)
    def choose_game(request: Request):
        games = [{"id": path.stem, "game": game,
                  "total": sum(len(col["items"]) for col in game["columns"])}
                 for path, game in available_games()]
        return page(request, "games.html", active="play", games=games)

    @router.get("/play/{game_id}", response_class=HTMLResponse)
    def game_preview(request: Request, game_id: str):
        game = find_game(game_id)
        total = sum(len(col["items"]) for col in game["columns"])
        return page(request, "preview.html", active="play", game=game, game_id=game_id, total=total)

    @router.post("/ui/start/{game_id}")
    def start_game(game_id: str):
        sid, _ = store.start(find_game(game_id))
        return RedirectResponse(f"/ui/sessions/{sid}", status_code=303)

    @router.get("/ui/sessions", response_class=HTMLResponse)
    def saved_sessions(request: Request):
        return page(request, "sessions.html", active="sessions", sessions=store.list_sessions())

    @router.get("/ui/sessions/clear", response_class=HTMLResponse)
    def confirm_clear(request: Request):
        return page(request, "confirm.html", active="sessions", heading="Clear all sessions?",
                     description=f"This permanently deletes {len(store.list_sessions())} saved session(s) and their draw histories. Game definitions are not affected.",
                     action="/ui/sessions/clear", button_text="Clear all sessions", cancel_url="/ui/sessions")

    @router.post("/ui/sessions/clear")
    def clear_sessions():
        store.clear()
        return RedirectResponse("/ui/sessions", status_code=303)

    @router.get("/ui/sessions/{session_id}", response_class=HTMLResponse)
    def current_game(request: Request, session_id: str):
        view, matrix = _action(store.overview, session_id)
        history = list(reversed(list(enumerate(view.history, start=1))))
        return page(request, "caller.html", active="sessions", session_id=session_id,
                     view=view, matrix=matrix, history=history,
                     percentage=round(view.drawn / view.total * 100))

    @router.get("/ui/sessions/{session_id}/matrix", response_class=HTMLResponse)
    def called_matrix(request: Request, session_id: str):
        matrix = _action(store.matrix, session_id)
        return page(request, "matrix.html", active="sessions", session_id=session_id,
                     matrix=matrix)

    @router.post("/ui/sessions/{session_id}/next")
    def draw_next(session_id: str):
        _action(store.next, session_id)
        return RedirectResponse(f"/ui/sessions/{session_id}", status_code=303)

    @router.get("/ui/sessions/{session_id}/reset", response_class=HTMLResponse)
    def confirm_reset(request: Request, session_id: str):
        view = _status(store, session_id)
        return page(request, "confirm.html", active="sessions", heading=f"Restart {view.name}?",
                     description=f"This clears {view.drawn} drawn call(s) and reshuffles the game. The session will be kept.",
                     action=f"/ui/sessions/{session_id}/reset", button_text="Reset and reshuffle",
                     cancel_url=f"/ui/sessions/{session_id}")

    @router.post("/ui/sessions/{session_id}/reset")
    def reset_session(session_id: str):
        _action(store.reset, session_id)
        return RedirectResponse(f"/ui/sessions/{session_id}", status_code=303)

    @router.get("/ui/sessions/{session_id}/delete", response_class=HTMLResponse)
    def confirm_delete(request: Request, session_id: str):
        view = _status(store, session_id)
        return page(request, "confirm.html", active="sessions", heading=f"Delete {view.name}?",
                     description="The saved session and draw history will be permanently deleted. The game definition stays available.",
                     action=f"/ui/sessions/{session_id}/delete", button_text="Delete session",
                     cancel_url="/ui/sessions")

    @router.post("/ui/sessions/{session_id}/delete")
    def delete_session(session_id: str):
        _action(store.delete, session_id)
        return RedirectResponse("/ui/sessions", status_code=303)

    @router.get("/ui/config", response_class=HTMLResponse)
    def config_page(request: Request):
        return page(request, "config.html", active="config", settings=load_config(config_path),
                     saved=request.query_params.get("saved") == "1")

    @router.post("/ui/config", response_class=HTMLResponse)
    def update_config(request: Request, history_limit: str = Form(...),
                      site_title: str = Form("Bingo Studio"),
                      tagline: str = Form("Your game night, made simple."),
                      accent: str = Form("lime")):
        try:
            limit = int(history_limit)
            save_config({"history_limit": limit, "site_title": site_title,
                         "tagline": tagline, "accent": accent}, config_path)
        except ValueError as exc:
            return page(request, "config.html", active="config", settings={"history_limit": history_limit, "site_title": site_title,
                                    "tagline": tagline, "accent": accent}, error=str(exc))
        return RedirectResponse("/ui/config?saved=1", status_code=303)

    @router.get("/ui/create-game", response_class=HTMLResponse)
    def create_game_page(request: Request):
        return page(request, "create.html", active="create", name="", word="BINGO",
                     free_center=True, columns=_column_fields("BINGO", [""] * 5))

    @router.get("/ui/customize/{game_id}", response_class=HTMLResponse)
    def customize_game(request: Request, game_id: str):
        """Create a new template from a copy; the existing game stays unchanged."""
        game = find_game(game_id)
        return page(request, "create.html", active="create",
                    name=game["name"] + " Custom", word=game["word"],
                    free_center=game["free_center"],
                    columns=_column_fields(game["word"], ["\n".join(col["items"]) for col in game["columns"]]),
                    source_name=game["name"])

    @router.post("/ui/create-game", response_class=HTMLResponse)
    def create_game(
        request: Request,
        name: str = Form(""),
        word: str = Form(""),
        free_center: bool = Form(False),
        items_0: str = Form(""), items_1: str = Form(""), items_2: str = Form(""),
        items_3: str = Form(""), items_4: str = Form(""),
    ):
        word = word.strip().upper()
        raw_values = [items_0, items_1, items_2, items_3, items_4]
        labels = word if len(word) == 5 and word.isascii() and word.isalpha() else "BINGO"
        data = {
            "name": name, "word": word, "free_center": free_center,
            "columns": [{"letter": labels[i], "items": [s.strip() for s in text.splitlines() if s.strip()]}
                        for i, text in enumerate(raw_values)],
        }
        try:
            path = save_game(data, game_directory)
        except ValueError as exc:
            return page(request, "create.html", active="create", name=name, word=word,
                         free_center=free_center, columns=_column_fields(word, raw_values), error=str(exc))
        return RedirectResponse(f"/play/{quote(path.stem, safe='')}", status_code=303)

    @router.post("/ui/import-game", response_class=HTMLResponse)
    async def import_game(request: Request, file: UploadFile = File(...)):
        try:
            if not (file.filename or "").lower().endswith(".json"):
                raise ValueError("Choose a .json game definition file.")
            content = await file.read(256 * 1024 + 1)
            if len(content) > 256 * 1024:
                raise ValueError("The JSON file must be 256 KB or smaller.")
            game = json.loads(content.decode("utf-8-sig"))
            path = save_game(game, game_directory)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            return page(request, "create.html", active="create", name="", word="BINGO", free_center=True,
                         columns=_column_fields("BINGO", [""] * 5), import_error=str(exc))
        finally:
            await file.close()
        return RedirectResponse(f"/play/{quote(path.stem, safe='')}", status_code=303)

    return router