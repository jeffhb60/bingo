# Plain-text API plus the separate unstyled browser UI in ui.py.

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .auth import AuthStore, add_session_cookie, cookie_name, matches_csrf
from .storage import CONFIG_PATH, GAME_DIR, ROOT, load_config, save_config, save_game, ACCENTS
from .tenant import Tenant, tenant_for
from .ui import build_ui_router, TEMPLATES


def _reply(message: str, status_code: int = 200) -> PlainTextResponse:
    return PlainTextResponse(message.rstrip() + "\n", status_code=status_code)

def _session_lines(session_id, view, limit):
    lines = [f"Playing: {view.name} [{view.word}]", f"Session: {session_id}",
             f"Previous draw: {view.previous or '(none)'}", f"Current draw: {view.current or '(none yet)'}",
             f"Progress: {view.drawn} / {view.total}", f"Remaining: {view.remaining}"]
    if limit:
        lines.append("Recent draws: " + (", ".join(view.history[-limit:]) if view.history else "(none yet)"))
    lines += ["", f"GET /ui/sessions/{session_id} - Browser controls",
              f"GET /ui/sessions/{session_id}/matrix - Visual draw matrix",
              f"POST /sessions/{session_id}/next - Draw next call",
              f"GET /sessions/{session_id}/history - Full history"]
    return lines

def create_app(game_directory: Path = GAME_DIR, config_path: Path = CONFIG_PATH,
               session_directory: Path | None = None, *, private_directory: Path | None = None,
               secure_cookies: bool | None = None) -> FastAPI:
    """One app instance per process. User data is private and excluded from static mounts."""
    app = FastAPI(title="Bingo Studio", description="Private Bingo games and caller")
    private_directory = Path(private_directory or Path(game_directory).parent / "private")
    prod = os.environ.get("BINGO_ENV", "development").lower() == "production"
    if secure_cookies is None:
        secure_cookies = prod
    if prod and not secure_cookies:
        raise RuntimeError("Production must use HTTPS / Secure cookies")
    secure_cookies = bool(secure_cookies)
    auth = AuthStore(private_directory / "auth.sqlite3")
    app.state.auth = auth
    app.state.tenants = {}
    app.state.secure_cookies = secure_cookies
    # Default BINGO is the only globally visible game; other games must be imported per-user.
    default_game_path = Path(game_directory) / "default_bingo.json"
    if not default_game_path.exists():
        raise RuntimeError("Missing shared games/default_bingo.json")

    @app.middleware("http")
    async def enforce_access(request: Request, call_next):
        path = request.url.path
        # Only static assets and the login form are public. No open registration.
        if path.startswith("/static/") or path == "/login":
            response = await call_next(request)
        else:
            token = request.cookies.get(cookie_name(secure_cookies))
            login = auth.session(token)
            if login is None:
                if request.method in ("GET", "HEAD") and not (path.startswith("/sessions") or path in ("/games", "/config", "/play", "/create-game", "/openapi.json", "/docs", "/redoc")):
                    return RedirectResponse("/login", status_code=303)
                return _reply("Error 401: Sign in required.", 401)
            request.state.login = login
            if login.user.id not in app.state.tenants:
                app.state.tenants[login.user.id] = Tenant(private_directory / "users" / login.user.id, default_game_path)
            # Plain-text API mutation requires CSRF header. Browser forms are checked by router dependencies.
            if request.method not in ("GET", "HEAD", "OPTIONS") and not path.startswith("/ui/") and path != "/logout" and path != "/account/password":
                if not matches_csrf(login.csrf, request.headers.get("X-CSRF-Token")):
                    return _reply("Error 403: Missing or invalid X-CSRF-Token.", 403)
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        # Dynamic inline CSS accent is escaped and limited to a fixed color list.
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        if prod:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        if auth.session(request.cookies.get(cookie_name(secure_cookies))):
            return RedirectResponse("/", status_code=303)
        import secrets
        pre_token = secrets.token_urlsafe(32)
        response = TEMPLATES.TemplateResponse(request=request, name="login.html", context={"pre_token": pre_token})
        response.set_cookie("bingo_prelogin", pre_token, max_age=600, secure=secure_cookies, httponly=True, samesite="strict", path="/")
        return response

    @app.post("/login", response_class=HTMLResponse)
    def login_post(request: Request, username: str = Form(""), password: str = Form(""),
                   csrf_token: str = Form("")):
        pre_token = request.cookies.get("bingo_prelogin", "")
        if not pre_token or not matches_csrf(pre_token, csrf_token):
            raise HTTPException(403, "Invalid login token. Reload the sign-in page.")
        # Read remote IP from ASGI peer only, not spoofable X-Forwarded-For input.
        ip = request.client.host if request.client else "unknown"
        user = auth.authenticate(username, password, ip)
        if not user:
            return TEMPLATES.TemplateResponse(request=request, name="login.html", context={
                "pre_token": pre_token, "error": "Invalid username or password, or temporarily locked. Try again later."}, status_code=401)
        token, _ = auth.new_session(user)
        response = RedirectResponse("/", status_code=303)
        add_session_cookie(response, token, secure_cookies)
        response.delete_cookie("bingo_prelogin", path="/")
        return response

    @app.post("/logout")
    def logout(request: Request, csrf_token: str = Form("")):
        if not matches_csrf(request.state.login.csrf, csrf_token):
            raise HTTPException(403, "Invalid security token")
        auth.revoke(request.cookies.get(cookie_name(secure_cookies)))
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(cookie_name(secure_cookies), path="/")
        return response

    @app.get("/account", response_class=HTMLResponse)
    def account_page(request: Request):
        return TEMPLATES.TemplateResponse(request=request, name="account.html", context={
            "username": request.state.login.user.username,
            "csrf_token": request.state.login.csrf,
            "branding": load_config(tenant_for(request).config_path),
            "accent_color": ACCENTS[load_config(tenant_for(request).config_path)["accent"]],
            "active": "account"})

    @app.post("/account/password")
    def change_own_password(request: Request, current_password: str = Form(""),
                            new_password: str = Form(""), csrf_token: str = Form("")):
        if not matches_csrf(request.state.login.csrf, csrf_token):
            raise HTTPException(403, "Invalid security token")
        username = request.state.login.user.username
        ip = request.client.host if request.client else "unknown"
        if not auth.authenticate(username, current_password, ip):
            raise HTTPException(403, "Current password incorrect or temporarily locked")
        try:
            auth.change_password(username, new_password)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(cookie_name(secure_cookies), path="/")
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return _reply(f"Error {exc.status_code}: {exc.detail}", exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return _reply(f"Error 422: Invalid request. {exc.errors()}", 422)

    @app.exception_handler(ValueError)
    async def invalid_data(request: Request, exc: ValueError):
        return _reply(f"Error 422: {exc}", 422)

    @app.get("/config", response_class=PlainTextResponse)
    def show_config(request: Request):
        return json.dumps(load_config(tenant_for(request).config_path), indent=2)

    @app.put("/config", response_class=PlainTextResponse)
    def update_config(request: Request, body: dict):
        save_config(body, tenant_for(request).config_path)
        return "Configuration saved.\n"

    @app.get("/create-game", response_class=PlainTextResponse)
    def create_game_help(request: Request):
        return "Use /ui/create-game to make private games, or POST /create-game with the JSON game definition.\n"

    @app.post("/create-game", response_class=PlainTextResponse, status_code=201)
    def create_game(request: Request, body: dict):
        path = save_game(body, tenant_for(request).games_dir)
        return f"Saved private game: custom-{path.stem}\n"

    @app.get("/games", response_class=PlainTextResponse)
    def games(request: Request):
        return "SAVED GAMES\n" + "\n".join(f"{p.stem}: {g['name']} [{g['word']}]" for p, g in tenant_for(request).games()) + "\n"

    @app.get("/games/{game_id}", response_class=PlainTextResponse)
    def game_details(request: Request, game_id: str):
        game = tenant_for(request).find_game(game_id)
        return json.dumps(game, indent=2)

    @app.get("/play", response_class=PlainTextResponse)
    def play_menu(request: Request):
        return "Open /ui/games to play your games.\n"

    @app.post("/play/{game_id}", response_class=PlainTextResponse, status_code=201)
    def start_game(request: Request, game_id: str):
        tenant = tenant_for(request)
        sid, view = tenant.sessions.start(tenant.find_game(game_id))
        return "\n".join(["SESSION STARTED", *_session_lines(sid, view, load_config(tenant.config_path)["history_limit"])]) + "\n"

    @app.get("/sessions", response_class=PlainTextResponse)
    def saved_sessions(request: Request):
        sessions = tenant_for(request).sessions.list_sessions()
        return "SAVED SESSIONS\n" + "\n".join(f"{sid}: {view.name} {view.drawn}/{view.total}" for sid, view in sessions) + "\n"

    def session_action(request: Request, name: str, session_id: str):
        try:
            return getattr(tenant_for(request).sessions, name)(session_id)
        except KeyError as exc:
            raise HTTPException(404, "Session not found") from exc

    @app.get("/sessions/{session_id}", response_class=PlainTextResponse)
    def session_status(request: Request, session_id: str):
        view = session_action(request, "status", session_id)
        return "\n".join(_session_lines(session_id, view, load_config(tenant_for(request).config_path)["history_limit"])) + "\n"

    @app.get("/sessions/{session_id}/matrix", response_class=PlainTextResponse)
    def text_matrix(request: Request, session_id: str):
        matrix = session_action(request, "matrix", session_id)
        lines = [f"CALL MATRIX — {matrix.name}", f"Drawn: {matrix.drawn} / {matrix.total}"]
        for column in matrix.columns:
            lines.append(f"Column {column.letter}")
            lines += [f"  {'✓' if cell.drawn else '·'} {cell.value}" for cell in column.cells]
        return "\n".join(lines) + "\n"

    @app.post("/sessions/{session_id}/next", response_class=PlainTextResponse)
    def next_draw(request: Request, session_id: str):
        call, view = session_action(request, "next", session_id)
        return "\n".join([f"DRAWN: {call}", *_session_lines(session_id, view, 5)]) + "\n"

    @app.get("/sessions/{session_id}/history", response_class=PlainTextResponse)
    def draw_history(request: Request, session_id: str):
        view = session_action(request, "status", session_id)
        return "\n".join([f"DRAW HISTORY — {view.name}"] + [f"{i}. {call}" for i, call in enumerate(view.history, start=1)]) + "\n"

    @app.post("/sessions/{session_id}/reset", response_class=PlainTextResponse)
    def reset_session(request: Request, session_id: str):
        view = session_action(request, "reset", session_id)
        return f"RESET: {view.name}\n"

    @app.post("/sessions/{session_id}/delete", response_class=PlainTextResponse)
    def delete_session(request: Request, session_id: str):
        session_action(request, "delete", session_id)
        return "Session deleted.\n"

    @app.post("/sessions/clear", response_class=PlainTextResponse)
    def clear_sessions(request: Request):
        count = tenant_for(request).sessions.clear()
        return f"Cleared {count} sessions.\n"

    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    app.include_router(build_ui_router())
    return app

app = create_app()
