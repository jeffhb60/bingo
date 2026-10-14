# Terminal interface (Command Line Interface)

from .sessions import SessionStore
from .storage import list_games, save_game, load_config, save_config

def print_game_list(games):
    if not games:
        print("No games found. Use Create Game first.")
        return
    print("\nSaved games:")
    for i, (_, game) in enumerate(games, start=1):
        count = sum(len(col["items"]) for col in game["columns"])
        print(f"  {i}. {game['name']} ({game['word']}, {count} calls)")

def choose_game():
    games = list_games()
    print_game_list(games)
    if not games:
        return None
    answer = input("Select a game number (or Enter to cancel): ").strip()
    if not answer:
        return None
    if not answer.isdecimal() or not 1 <= int(answer) <= len(games):
        print("Invalid selection.")
        return None
    return games[int(answer) - 1][1]

def create_game() -> None:
    print("\nCREATE GAME")
    name = input("Game name (blank to cancel): ").strip()
    if not name:
        return
    word = input("Five-letter header (e.g. FLAME): ").strip().upper()
    if len(word) != 5 or not word.isascii() or not word.isalpha():
        print("Header must contain exactly five letters A-Z.")
        return
    free_center = input("Free center square later on printable cards? [Y/n]: ").strip().lower() != "n"
    columns = []
    print("Enter each call/item on its own line; press Enter on a blank line to finish each column.")
    for pos, letter in enumerate(word, start=1):
        print(f"\nColumn {pos} — {letter}")
        items = []
        while True:
            entry = input(f"  {letter}> ").strip()
            if not entry:
                if not items:
                    print("  Please enter at least one item.")
                    continue
                break
            if entry.casefold() in {x.casefold() for x in items}:
                print("  That item is already in this column.")
                continue
            items.append(entry)
        columns.append({"letter": letter, "items": items})
    try:
        path = save_game({"name": name, "word": word, "free_center": free_center, "columns": columns})
        print(f"\nSaved to {path}")
    except ValueError as exc:
        print(f"Unable to save game: {exc}")

def _run_session(store: SessionStore, session_id: str, history_limit: int) -> None:
    view = store.status(session_id)
    print(f"\nPlaying: {view.name} [{view.word}]\nSession: {session_id}")
    print("Enter = next draw | h = all history | r = restart | q = menu")
    while True:
        command = input("\nCommand: ").strip().lower()
        if command == "q":
            print("Session saved; resume it later using menu option 5.")
            return
        if command == "h":
            view = store.status(session_id)
            print("Draw history: " + (", ".join(view.history) or "(none yet)"))
            continue
        if command == "r":
            if input("Reshuffle and clear draw history? [y/N]: ").strip().lower() == "y":
                store.reset(session_id)
                print("Game restarted and saved.")
            continue
        if command:
            print("Unknown command.")
            continue
        called, view = store.next(session_id)
        if called is None:
            print("All calls drawn! Choose r to restart or q to exit.")
            continue
        if view.previous:
            print(f"Previous: {view.previous}")
        print(f"\n  >>> {called} <<<")
        print(f"Draw {view.drawn} / {view.total} | Remaining: {view.remaining}")
        if history_limit:
            print("Recent: " + ", ".join(view.history[-history_limit:]))

def play_game(history_limit: int) -> None:
    game = choose_game()
    if game is None:
        return
    store = SessionStore()
    session_id, _ = store.start(game)
    _run_session(store, session_id, history_limit)

def resume_game(history_limit: int) -> None:
    store = SessionStore()
    sessions = store.list_sessions()
    if not sessions:
        print("No saved sessions.")
        return
    print("\nSaved sessions:")
    for index, (_, view) in enumerate(sessions, start=1):
        print(f"  {index}. {view.name} [{view.word}] - {view.drawn}/{view.total} drawn")
    answer = input("Select a session number (blank to cancel): ").strip()
    if answer.isdecimal() and 1 <= int(answer) <= len(sessions):
        _run_session(store, sessions[int(answer) - 1][0], history_limit)
    elif answer:
        print("Invalid selection.")

def clear_sessions() -> None:
    store = SessionStore()
    count = len(store.list_sessions())
    answer = input(f"Delete all {count} session(s)? This cannot be undone. Type CLEAR to confirm: ")
    if answer == "CLEAR":
        print(f"Deleted {store.clear()} saved sessions. Game JSON files were kept.")
    else:
        print("Cancelled.")

def configure(config: dict) -> None:
    print(f"\nCONFIGURATION — recent calls shown: {config['history_limit']}")
    answer = input("New history count (0–50; blank to keep): ").strip()
    if not answer:
        return
    if answer.isdecimal() and 0 <= int(answer) <= 50:
        config["history_limit"] = int(answer)
        save_config(config)
        print("Settings saved to config.json")
    else:
        print("Enter a whole number between 0 and 50.")

def main():
    try:
        config = load_config()
    except ValueError as exc:
        print(f"{exc}\nUsing default settings for this run.")
        config = {"history_limit": 5}
    while True:
        print("\n" + "=" * 32)
        print("           BINGO STUDIO")
        print("=" * 32)
        print("1. Config")
        print("2. Create game")
        print("3. Play game")
        print("4. List saved games")
        print("5. Resume saved game")
        print("6. Clear saved sessions")
        print("Q. Quit")
        selection = input("Select: ").strip().lower()
        if selection == "1":
            configure(config)
        elif selection == "2":
            create_game()
        elif selection == "3":
            play_game(config["history_limit"])
        elif selection == "4":
            print_game_list(list_games())
        elif selection == "5":
            resume_game(config["history_limit"])
        elif selection == "6":
            clear_sessions()
        elif selection == "q":
            print("Goodbye!")
            return
        else:
            print("Choose 1, 2, 3, 4, 5, 6, or Q.")