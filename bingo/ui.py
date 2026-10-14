# Plain, unstyled HTML forms for browser play; no CSS or JavaScript
# More styling to be added later. Testing for functionality before building out frontend.

from html import escape
from typing import Callable
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from .sessions import SessionStore, SessionView

def _url_part(value: str) -> str:
    return quote(value, safe="")

def _status(store: SessionStore, session_id: str) -> SessionView:
    try:
        return store.status(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0])) from exc
# One tiny shared wrapper; browser defaults handle all formatting.
def _page(body: str) -> str:

    return f'<!doctype html><html lang="en"><meta charset="utf-8"><title>Bingo Studio</title><body>{body}</body></html>'


def build_ui_router(
    store: SessionStore,
    available_games: Callable[[], list[tuple]],
    find_game: Callable[[str], dict],
) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    def home() -> str:
        return _page(
            '<h1>BINGO STUDIO</h1><ul>'
            '<li><a href="/ui/games">Play game</a></li>'
            '<li><a href="/ui/sessions">Resume / manage sessions</a></li>'
            '<li><a href="/config">Configuration (text)</a></li>'
            '<li><a href="/create-game">Create game (JSON instructions)</a></li>'
            '<li><a href="/games">Saved game definitions (text)</a></li>'
            '<li><a href="/docs">API documentation</a></li>'
            '</ul>'
        )

    @router.get("/ui/games", response_class=HTMLResponse)
    def choose_game() -> str:
        choices = available_games()
        items = "".join(
            f'<li><a href="/play/{_url_part(path.stem)}">'
            f'{escape(game["name"])} [{escape(game["word"])}]</a></li>'
            for path, game in choices
        ) or '<li>No saved games found.</li>'
        return _page(f'<h1>PLAY GAME</h1><ul>{items}</ul><p><a href="/">Main menu</a></p>')

    @router.get("/play/{game_id}", response_class=HTMLResponse)
    def game_preview(game_id: str) -> str:
        game = find_game(game_id)
        count = sum(len(column["items"]) for column in game["columns"])
        columns = "".join(
            f'<li>{escape(column["letter"])}: {len(column["items"])} available calls</li>'
            for column in game["columns"]
        )
        return _page(
            f'<h1>GAME PREVIEW</h1><h2>{escape(game["name"])}</h2>'
            f'<p>Word: {escape(game["word"])} | Calls: {count} | Free center: {game["free_center"]}</p>'
            f'<ul>{columns}</ul>'
            f'<form method="post" action="/ui/start/{_url_part(game_id)}">'
            '<button type="submit">Start Game</button></form>'
            '<p><a href="/ui/games">Back to games</a></p>'
        )

    @router.post("/ui/start/{game_id}")
    def start_game(game_id: str) -> RedirectResponse:
        session_id, _ = store.start(find_game(game_id))
        return RedirectResponse(f"/ui/sessions/{session_id}", status_code=303)

    @router.get("/ui/sessions", response_class=HTMLResponse)
    def saved_sessions() -> str:
        entries = store.list_sessions()
        items = "".join(
            f'<li><a href="/ui/sessions/{session_id}">'
            f'{escape(view.name)} [{escape(view.word)}] — '
            f'{view.drawn}/{view.total} drawn</a> '
            f'(<a href="/ui/sessions/{session_id}/delete">Delete</a>)</li>'
            for session_id, view in entries
        ) or '<li>No saved sessions.</li>'
        return _page(
            '<h1>RESUME / MANAGE GAMES</h1>'
            f'<ul>{items}</ul>'
            '<p><a href="/ui/sessions/clear">Clear all sessions...</a></p>'
            '<p><a href="/ui/games">Start new game</a> | <a href="/">Main menu</a></p>'
        )

    # Register the static /clear path before the dynamic /{session_id} path.
    @router.get("/ui/sessions/clear", response_class=HTMLResponse)
    def confirm_clear() -> str:
        count = len(store.list_sessions())
        return _page(
            f'<h1>Clear all saved sessions?</h1><p>This will permanently delete {count} session(s) '
            'and their draw histories. Saved game definitions will NOT be deleted.</p>'
            '<form method="post" action="/ui/sessions/clear">'
            '<button type="submit">Yes, clear all sessions</button></form>'
            '<p><a href="/ui/sessions">Cancel</a></p>'
        )

    @router.post("/ui/sessions/clear")
    def clear_sessions() -> RedirectResponse:
        store.clear()
        return RedirectResponse("/ui/sessions", status_code=303)

    @router.get("/ui/sessions/{session_id}", response_class=HTMLResponse)
    def current_game(session_id: str) -> str:
        view = _status(store, session_id)
        history = "\n".join(f"{i}. {call}" for i, call in enumerate(view.history, start=1)) or "(none yet)"
        action = f"/ui/sessions/{session_id}"
        draw = (
            f'<form method="post" action="{action}/next">'
            '<button type="submit">Draw Next Number</button></form>'
            if view.remaining
            else '<p>All calls have been drawn.</p>'
        )
        return _page(
            f'<h1>{escape(view.name)} [{escape(view.word)}]</h1>'
            f'<h2>Current draw: {escape(view.current or "Not started")}</h2>'
            f'<p>Previous: {escape(view.previous or "None")}</p>'
            f'<p>Drawn: {view.drawn} / {view.total} | Remaining: {view.remaining}</p>'
            f'{draw}'
            '<h3>Draw history</h3>'
            f'<pre>{escape(history)}</pre>'
            f'<p><a href="{action}/reset">Restart / reshuffle...</a> | '
            f'<a href="{action}/delete">Delete session...</a> | '
            '<a href="/ui/sessions">Resume / manage games</a></p>'
        )

    @router.post("/ui/sessions/{session_id}/next")
    def draw_next(session_id: str) -> RedirectResponse:
        try:
            store.next(session_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc.args[0])) from exc
        return RedirectResponse(f"/ui/sessions/{session_id}", status_code=303)

    @router.get("/ui/sessions/{session_id}/reset", response_class=HTMLResponse)
    def confirm_reset(session_id: str) -> str:
        view = _status(store, session_id)
        return _page(
            f'<h1>Restart {escape(view.name)}?</h1>'
            f'<p>This erases all {view.drawn} draws and reshuffles the deck.</p>'
            f'<form method="post" action="/ui/sessions/{session_id}/reset">'
            '<button type="submit">Yes, reset game</button></form>'
            f'<p><a href="/ui/sessions/{session_id}">Cancel</a></p>'
        )

    @router.post("/ui/sessions/{session_id}/reset")
    def reset_session(session_id: str) -> RedirectResponse:
        try:
            store.reset(session_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc.args[0])) from exc
        return RedirectResponse(f"/ui/sessions/{session_id}", status_code=303)

    @router.get("/ui/sessions/{session_id}/delete", response_class=HTMLResponse)
    def confirm_delete(session_id: str) -> str:
        view = _status(store, session_id)
        return _page(
            f'<h1>Delete {escape(view.name)} session?</h1>'
            '<p>Its draw history will be lost. The game definition will be kept.</p>'
            f'<form method="post" action="/ui/sessions/{session_id}/delete">'
            '<button type="submit">Yes, delete session</button></form>'
            '<p><a href="/ui/sessions">Cancel</a></p>'
        )

    @router.post("/ui/sessions/{session_id}/delete")
    def delete_session(session_id: str) -> RedirectResponse:
        try:
            store.delete(session_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc.args[0])) from exc
        return RedirectResponse("/ui/sessions", status_code=303)

    return router
