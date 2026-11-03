# Bingo Studio

A customizable, multi-user Bingo caller built with **Python**, **FastAPI**, **Jinja2**, and lightweight **JSON + SQLite** persistence.

## Features

- **Invite-only accounts.** Administrators create users; public registration is disabled.
- **Shared standard BINGO.** Every signed-in user can start their own 75-number BINGO session using `games/default_bingo.json`.
- **Private games.** Create or import five-column games with five-letter headings such as BINGO, FLAME, or APPLE; customize a copy without changing the original.
- **Personal settings.** Configure your own site title, tagline, accent color, and recent-call limit.
- **Persistent draws.** Shuffle once, draw without repeats, resume saved sessions, view history, reset, and delete sessions.
- **Check-calls matrix.** Open a popup to see all possible calls, a checkmark for each drawn entry, and a highlight around the latest call; a full-page matrix is also available.
- **Plain-text API** in addition to the styled browser interface.

> **Note:** The call matrix checks which entries have been called; it does not automatically verify a player's Bingo card. The `free_center` setting is retained in game definitions for future card functionality.
>
> ## Quick start (local development)

Use Python 3.11 or newer.

```bash
git clone https://github.com/jeffhb60/bingo.git
cd bingo
git switch main
python -m venv .venv
```

Activate the virtual environment:

- Windows PowerShell: `.venv\Scripts\Activate.ps1`
- macOS/Linux: `source .venv/bin/activate`

Install dependencies:

```bash
python -m pip install -r requirements.txt
python -m pip install jinja2 python-multipart argon2-cffi
```

**Important:** On the current `main` branch, `requirements.txt` lists only `fastapi` and `uvicorn` despite the app importing Jinja2, python-multipart, and Argon2. The second command fills that gap until the requirements file is updated.

Create your first user. You will be prompted to enter and confirm a password:

```bash
python manage_users.py add admin
```

Run the local web application:

```bash
python run_web.py
```

Open **http://127.0.0.1:8000/login** and sign in. The launcher runs a single Uvicorn worker bound to localhost.

## Use the web app

1. **Play:** Open the shared default BINGO game or one of your private games.
2. **Draw:** Start a session and click *Draw next*. The app saves each draw immediately.
3. **Verify calls:** Click *Check BINGO calls* (or the name of your custom heading) to open the matrix. Close it using **×**, **Escape**, or the Close button. The latest draw is highlighted.
4. **Sessions:** Resume previously saved games, review call history, reset, or delete sessions.
5. **Create:** Enter five columns of custom calls, import a JSON game file (256 KB maximum), or choose **Customize a copy** from a saved game.
6. **Settings:** Set a personal site title, tagline, accent color, and recent-history limit.
7. **Account:** Change your password; changing it requires logging in again.

Each account's games, settings, and saved sessions are private. The classic BINGO definition is shared, but each user starts an independent session with their own draws.

## Manage user accounts

Accounts are **invite-only**. Run these commands on the host machine in the repository directory:

```bash
python manage_users.py add alice
python manage_users.py list
python manage_users.py reset-password alice
python manage_users.py disable alice
```

Passwords must be **12–128 characters**. Password prompts do not echo passwords or place them in command history.

To assign existing pre-account JSON games, sessions, and settings to one *existing* user:

```bash
python manage_users.py import-legacy alice
```

The import makes private copies of the legacy data and leaves the original files intact. It does not make imported games available to all accounts.

## Customize a game with JSON

A game has a name, an exactly five-letter header, five columns matching those letters in order, and one or more unique entries per column.

```json
{
  "name": "Friday FLAME",
  "word": "FLAME",
  "free_center": true,
  "columns": [
    { "letter": "F", "items": ["Fire", "Friendship"] },
    { "letter": "L", "items": ["Light", "Love"] },
    { "letter": "A", "items": ["Art", "Adventure"] },
    { "letter": "M", "items": ["Music", "Moon"] },
    { "letter": "E", "items": ["Earth", "Energy"] }
  ]
}
```

Column labels must match the corresponding character in `word`. Entries must be nonblank and unique within their column. Column positions are distinct even if multiple heading letters are the same (such as in APPLE). You can use strings or integers for call values.

Use the Create page to build a game interactively, or upload a `.json` file. New games are saved to the signed-in user's private game library, not `games/default_bingo.json`.

## Storage and project structure

The current branch uses **SQLite for user accounts and login sessions** and **JSON files for user preferences, custom game definitions, and saved draws**.

```text
bingo/
├── bingo/
│   ├── auth.py              # Password hashes, logins, user administration storage
│   ├── tenant.py            # Authenticated user's private workspace
│   ├── game.py              # Draw logic and saved-deck snapshots
│   ├── sessions.py          # Saved draw sessions and matrix state
│   ├── storage.py           # JSON read/write and validation
│   ├── ui.py                # Styled web forms and browser routes
│   ├── web.py               # FastAPI server, authentication, text API
│   ├── templates/           # Jinja2 pages
│   └── static/              # CSS and small JavaScript files
├── games/
│   └── default_bingo.json   # Shared standard BINGO definition
├── private/                 # Created at runtime; excluded from Git
│   ├── auth.sqlite3
│   └── users/<user-id>/
│       ├── config.json
│       ├── games/*.json
│       └── sessions/*.json
├── manage_users.py
├── run_web.py
├── run_cli.py
└── requirements.txt
```

**Back up `private/` securely.** It contains account records, personal settings, custom games, and draw histories. Saved sessions include the original game definition and exact shuffled deck so reloading a session never reshuffles previous draws.

The optional `python run_cli.py` is a **legacy, standalone terminal caller** using root-level game/session files. It is not connected to private user accounts and should not be treated as an account management interface.

## Security

- Passwords are stored as **Argon2id hashes**.
- Logins use time-limited, opaque, revocable cookies. Production mode enables Secure cookies.
- Browser forms validate **CSRF tokens**; the authenticated plain-text API requires an `X-CSRF-Token` header on state-changing requests.
- Tenant-specific data is selected server-side from the authenticated user, not from client-supplied file paths.
- No public registration endpoint is provided.
- Keep the host updated, restrict access to management commands, and do not expose `private/` as public files.

To run behind HTTPS in production, set `BINGO_ENV=production` and configure a trusted HTTPS reverse proxy or ingress. Do not expose the development launcher directly to the internet. With the existing local SQLite/JSON storage and process-level locks, use **one application instance/worker and persistent disk**.

## API routes

Once authenticated, interactive API documentation is available at `/docs`.

| Route | Function |
| --- | --- |
| `GET /ui/games` | View your game library |
| `GET /ui/create-game` | Create or import a private game |
| `GET /ui/sessions` | Resume and manage sessions |
| `GET /ui/sessions/{id}` | Caller and check-calls popup |
| `GET /ui/sessions/{id}/matrix` | Full-page call matrix |
| `GET /ui/config` | Personal settings |
| `GET /account` | Account and password management |
| `GET /games` | Plain-text game list |
| `POST /play/{game_id}` | Start a game through the API |
| `POST /sessions/{id}/next` | Draw via the API |

The plain-text API is protected by the same login session and requires a valid `X-CSRF-Token` for writes. Browser forms supply their own token.
