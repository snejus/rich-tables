from __future__ import annotations

import inspect
import sys
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, Protocol, runtime_checkable

from rich import box
from rich.console import RichCast
from typing_extensions import Self

from .fields import get_val
from .utils import md_panel

if TYPE_CHECKING:
    from rich.console import ConsoleRenderable

TypeName = Literal["GithubComment"]


@runtime_checkable
class RichCastFactory(RichCast, Protocol):
    @classmethod
    def make(cls, **kwargs: Any) -> Self: ...


class GithubReaction(NamedTuple):
    author: str
    content: str

    @classmethod
    def make(cls, *args: Any, **kwargs: Any) -> Self:
        return cls(*args, **kwargs)

    def __str__(self) -> str:
        content = (
            self.content.lower()
            .replace("laugh", "laughing")
            .replace("hooray", "party_popper")
        )
        return f":{content}: {get_val(self, 'author')}"

    def __rich__(self) -> str:
        return str(self)


class GithubComment(NamedTuple):
    body: str
    author: str
    created_at: str
    state: Literal["CHANGES_REQUESTED", "APPROVED", "COMMENTED"]
    reactions: list[GithubReaction]

    @classmethod
    def make(cls, *args: Any, **kwargs: Any) -> Self:
        kwargs["reactions"] = [GithubReaction(**r) for r in kwargs.get("reactions", [])]
        return cls(*args, **kwargs)

    def __rich__(self) -> ConsoleRenderable:
        return md_panel(
            self.body,
            title=" ".join(get_val(self, f) for f in ["author", "created_at"]),
            subtitle=" ".join(map(str, self.reactions)),
            border_style={
                "APPROVED": "green",
                "COMMENTED": "yellow",
                "CHANGES_REQUESTED": "b red",
            }[self.state],
            box=box.ROUNDED,
        )


TYPE_BY_NAME: dict[str, type[RichCastFactory]] = {
    name: obj
    for name, obj in inspect.getmembers(sys.modules[__name__], inspect.isclass)
    if issubclass(obj, RichCast) and obj is not RichCast
}


def get_renderable(_type: Literal["GithubComment"], **kwargs: Any) -> RichCastFactory:
    return TYPE_BY_NAME[_type].make(**kwargs)
