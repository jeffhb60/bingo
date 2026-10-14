# Game rules, random drawing, and validated session snapshots.
# Game contents come entirely from JSON definitions, not hardcoded number ranges.

from collections import Counter
from dataclasses import asdict, dataclass
import random

@dataclass(frozen=True)
class Call:
    column: int
    letter: str
    value: str

    def __str__(self) -> str:
        divider = "-" if self.value.isdecimal() else ": "
        return f"{self.letter}{divider}{self.value}"

# Normalize a five-column game definition or raise ValueError.
def validate_game(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Game JSON must be an object.")

    name = data.get("name")
    word = data.get("word")
    columns = data.get("columns")
    free_center = data.get("free_center", True)

    if not isinstance(name, str) or not name.strip():
        raise ValueError("'name' must be a nonempty string.")
    if not isinstance(word, str) or len(word) != 5 or not word.isascii() or not word.isalpha():
        raise ValueError("'word' must contain exactly five letters A-Z.")
    if not isinstance(free_center, bool):
        raise ValueError("'free_center' must be true or false.")
    if not isinstance(columns, list) or len(columns) != 5:
        raise ValueError("'columns' must contain exactly five column objects.")

    normalized = []
    word = word.upper()
    for i, column in enumerate(columns):
        if not isinstance(column, dict):
            raise ValueError(f"Column {i + 1} must be an object.")
        letter = column.get("letter")
        if not isinstance(letter, str) or letter.upper() != word[i]:
            raise ValueError(f"Column {i + 1} letter must be '{word[i]}'.")
        items = column.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError(f"Column {i + 1} must have at least one item.")
        values = []
        seen = set()
        for item in items:
            if isinstance(item, bool) or not isinstance(item, (str, int)):
                raise ValueError(f"Column {i + 1}: items must be strings or integers.")
            value = str(item).strip()
            if not value:
                raise ValueError(f"Column {i + 1}: an item cannot be blank.")
            if value.casefold() in seen:
                raise ValueError(f"Column {i + 1}: duplicate item '{value}'.")
            seen.add(value.casefold())
            values.append(value)
        normalized.append({"letter": word[i], "items": values})

    return {
        "name": name.strip(),
        "word": word,
        "free_center": free_center,
        "columns": normalized,
    }

# One shuffled deck and a cursor. Each call is drawn exactly once.
class GameSession:

    def __init__(self, game: dict, *, rng: random.Random | None = None):
        self.game = validate_game(game)
        self.rng = rng if rng is not None else random.Random()
        self.reset()

    def reset(self) -> None:
        self.deck = [
            Call(column=i, letter=column["letter"], value=value)
            for i, column in enumerate(self.game["columns"])
            for value in column["items"]
        ]
        self.rng.shuffle(self.deck)
        self.cursor = 0

    @property
    def remaining(self) -> int:
        return len(self.deck) - self.cursor

    @property
    def history(self) -> list[Call]:
        return self.deck[:self.cursor]

    @property
    def previous(self) -> Call | None:
        return self.deck[self.cursor - 1] if self.cursor else None

    def next_call(self) -> Call | None:
        if self.remaining == 0:
            return None
        call = self.deck[self.cursor]
        self.cursor += 1
        return call

    # Snapshot exact draw order + progress for a restart-safe session.
    def snapshot(self) -> dict:
        return {
            "version": 1,
            "game": self.game,  # Preserve game rules even if its source JSON changes.
            "deck": [asdict(call) for call in self.deck],
            "cursor": self.cursor,
        }

    # Restore and validate a saved shuffle; never reshuffle a resumed game.
    @classmethod
    def from_snapshot(cls, data: dict) -> "GameSession":
        if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
            raise ValueError("Unsupported or invalid saved-session format.")
        game = validate_game(data.get("game"))
        raw_deck = data.get("deck")
        cursor = data.get("cursor")
        if not isinstance(raw_deck, list) or type(cursor) is not int or not 0 <= cursor <= len(raw_deck):
            raise ValueError("Saved session has an invalid deck or cursor.")
        try:
            deck = [Call(**item) for item in raw_deck]
        except (TypeError, ValueError) as exc:
            raise ValueError("Saved session has malformed calls.") from exc
        expected = Counter(
            Call(i, column["letter"], value)
            for i, column in enumerate(game["columns"])
            for value in column["items"]
        )
        if Counter(deck) != expected:
            raise ValueError("Saved session deck does not match its game definition.")
        # Constructor initializes the RNG for future resets; restore exact saved deck.
        session = cls(game)
        session.deck = deck
        session.cursor = cursor
        return session

