from __future__ import annotations

from enum import StrEnum


class State(StrEnum):
    TO_DO = "To Do"
    IN_PROGRESS = "In Progress"
    BLOCKED = "Blocked"
    IN_REVIEW = "In Review"
    DONE = "Done"

    @classmethod
    def parse(cls, text: str) -> State:
        wanted = _fold(text)
        for state in cls:
            if wanted in {_fold(state.value), _fold(state.name)}:
                return state
        names = ", ".join(state.value for state in cls)
        raise ValueError(f"unknown state {text!r}; use one of: {names}")


def _fold(text: str) -> str:
    return "".join(character for character in text.casefold() if character.isalnum())
