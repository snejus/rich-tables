from __future__ import annotations

import inspect
import sys
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, TypedDict

from rich import box
from rich.console import RichCast

from .fields import get_val
from .utils import md_panel

if TYPE_CHECKING:
    from rich.console import ConsoleRenderable

TypeName = Literal["GithubComment"]


class GithubReaction(TypedDict):
    author: str
    content: str


class GithubComment(NamedTuple):
    body: str
    author: str
    created_at: str
    state: Literal["CHANGES_REQUESTED", "APPROVED", "COMMENTED"]
    reactions: list[GithubReaction]

    def __rich__(self) -> ConsoleRenderable:
        return md_panel(
            self.body,
            title=" ".join(get_val(self, f) for f in ["author", "created_at"]),
            subtitle=(
                " ".join(
                    f":{r['content'].lower()}: {get_val(r, 'author')}"
                    for r in self.reactions
                )
                .replace(":laugh:", ":laughing:")
                .replace(":hooray:", ":party_popper:")
            ),
            border_style={
                "APPROVED": "green",
                "COMMENTED": "yellow",
                "CHANGES_REQUESTED": "b red",
            }[self.state],
            box=box.ROUNDED,
        )


TYPE_BY_NAME: dict[str, type[RichCast]] = {
    name: obj
    for name, obj in inspect.getmembers(sys.modules[__name__], inspect.isclass)
    if issubclass(obj, RichCast) and obj is not RichCast
}


def get_renderable(_type: Literal["GithubComment"], **kwargs: Any) -> ConsoleRenderable:
    return TYPE_BY_NAME[_type](**kwargs)  # type: ignore[return-value]
