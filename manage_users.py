# Create and maintain invite-only users. Password input never appears in shell history.
import argparse
from getpass import getpass
from bingo.auth import AuthStore
from bingo.storage import ROOT
from shutil import copy2

def main():
    parser = argparse.ArgumentParser(description="Manage Bingo Studio user accounts")
    parser.add_argument("action", choices=("add", "reset-password", "disable", "list", "import-legacy"))
    parser.add_argument("username", nargs="?")
    args = parser.parse_args()
    store = AuthStore(ROOT / "private" / "auth.sqlite3")
    if args.action == "list":
        for username, active in store.list_users():
            print(f"{username}: {'active' if active else 'disabled'}")
        return
    if not args.username:
        parser.error("username is required for this action")
    if args.action == "import-legacy":
        # Requires an existing account and is an explicit assignment of old shared data.
        with store._db() as db:
            row = db.execute("SELECT id FROM users WHERE username=? AND enabled=1", (args.username.lower(),)).fetchone()
        if not row:
            parser.error("Existing active user required")
        destination = ROOT / "private" / "users" / row["id"]
        count = 0
        for src_dir, dst_dir in ((ROOT / "games", destination / "games"),
                                 (ROOT / "sessions", destination / "sessions")):
            if not src_dir.exists():
                continue
            dst_dir.mkdir(parents=True, exist_ok=True)
            for src in src_dir.glob("*.json"):
                if src.name == "default_bingo.json" and src_dir.name == "games":
                    continue
                dst = dst_dir / src.name
                if not dst.exists():
                    copy2(src, dst)
                    count += 1
        if (ROOT / "config.json").is_file() and not (destination / "config.json").exists():
            destination.mkdir(parents=True, exist_ok=True)
            copy2(ROOT / "config.json", destination / "config.json")
            count += 1
        print(f"Assigned {count} existing JSON files to {args.username}. Originals remain unchanged.")
        return
    if args.action == "disable":
        store.disable_user(args.username)
    else:
        password = getpass("Password (min. 12 characters): ")
        if password != getpass("Repeat password: "):
            parser.error("Passwords do not match")
        if args.action == "add":
            store.add_user(args.username, password)
        else:
            store.change_password(args.username, password)
    print(f"User {args.username}: {args.action} complete")

if __name__ == "__main__":
    main()