"""Terminal interface. Later a web UI can call storage.py and game.py directly."""

from .game import GameSession
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

def play_game(history_limit: int) -> None:
    game = choose_game()
    if game is None:
        return
    session = GameSession(game)
    print(f"\nPlaying: {game['name']} [{game['word']}]")
    print("Press Enter = next draw | h = all history | r = restart | q = menu")
    while True:
        command = input("\nCommand: ").strip().lower()
        if command == "q":
            return
        if command == "h":
            print("Draw history: " + (", ".join(map(str, session.history)) or "(none yet)"))
            continue
        if command == "r":
            if input("Reshuffle and clear draw history? [y/N]: ").strip().lower() == "y":
                session.reset()
                print("Game restarted.")
            continue
        if command:
            print("Unknown command.")
            continue
        if not session.remaining:
            print("All calls have been drawn! Choose r to restart, or q to exit.")
            continue
        previous = session.previous
        called = session.next_call()
        if previous:
            print(f"Previous: {previous}")
        print(f"\n  >>> {called} <<<")
        print(f"Draw {session.cursor} / {len(session.deck)}  |  Remaining: {session.remaining}")
        if history_limit:
            recent = session.history[-history_limit:]
            print("Recent: " + ", ".join(map(str, recent)))

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
        elif selection == "q":
            print("Goodbye!")
            return
        else:
            print("Choose 1, 2, 3, 4, or Q.")
