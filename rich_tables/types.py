from __future__ import annotations

import inspect
import sys
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    NamedTuple,
    Protocol,
    TypedDict,
    runtime_checkable,
)

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


class GithubLabel(TypedDict):
    name: str
    color: str


class IssueReference(TypedDict):
    number: int
    title: str


@dataclass
class GithubPRCard(RichCastFactory):
    url: str
    title: str
    author: str
    state: str  # already Rich markup from your data
    additions: int
    deletions: int
    labels: list[GithubLabel]
    created_at: str
    updated_at: str
    reactions: list[GithubReaction]
    last_comment: GithubComment | None
    closingIssuesReferences: list[IssueReference]

    @classmethod
    def make(cls, *args: Any, **kwargs: Any) -> Self:
        raw_lc = kwargs.pop("last_comment", None)
        kwargs["last_comment"] = GithubComment.make(**raw_lc) if raw_lc else None
        kwargs["reactions"] = [GithubReaction(**r) for r in kwargs.get("reactions", [])]
        kwargs.setdefault("additions", 0)
        kwargs.setdefault("deletions", 0)
        return cls(*args, **kwargs)

    @staticmethod
    def _border(state: str) -> str:
        for emoji, colour in {
            "⏳": "green",
            "✅": "bright_green",
            "⛔": "red",
            "❔": "yellow",
        }.items():
            if emoji in state:
                return colour
        return "dim"

    def __rich__(self) -> ConsoleRenderable:
        from rich import box

        from .fields import FIELDS_MAP
        from .utils import (
            border_panel,
            format_with_color_on_black,
            human_dt,
            list_table,
            new_table,
            simple_panel,
            wrap,
        )

        additions = f"+{self.additions}" if self.additions else ""
        deletions = f"-{self.deletions}" if self.deletions else ""

        meta = new_table(
            rows=[
                [wrap("state", "dim"), self.state],
                [
                    wrap("churn", "dim"),
                    wrap(additions, "b green") + " " + wrap(deletions, "b red"),
                ],
                [wrap("opened", "dim"), human_dt(self.created_at)],
                [wrap("updated", "dim"), human_dt(self.updated_at)],
                # [wrap("issue", "dim"), wrap(self.issue_ref, "dim cyan")],
                [
                    wrap("labels", "dim"),
                    FIELDS_MAP["labels"](self.labels)
                    if self.labels
                    else wrap("—", "dim"),
                ],
            ],
            show_header=False,
            highlight=False,
            box=box.SIMPLE,
            expand=False,
            padding=(0, 1),
        )
        body = list_table(
            [
                meta,
                simple_panel(
                    self.last_comment or wrap("no comments yet", "dim"),
                    title="last comment",
                    border_style="dim",
                ),
            ],
            padding=(0, 0, 1, 0),
        )
        card_title = " ".join(
            [
                wrap(self.title, "b white"),
                wrap("by", "dim"),
                format_with_color_on_black(self.author),
            ]
        )
        return border_panel(
            body,
            title=card_title,
            title_align="left",
            border_style=self._border(self.state),
            subtitle=f"[link]{self.url}[/link]",
        )


TYPE_BY_NAME: dict[str, type[RichCastFactory]] = {
    name: obj
    for name, obj in inspect.getmembers(sys.modules[__name__], inspect.isclass)
    if issubclass(obj, RichCast) and obj is not RichCast
}


def get_renderable(
    _type: Literal["GithubComment", "GithubPRCard"], **kwargs: Any
) -> RichCastFactory:
    return TYPE_BY_NAME[_type].make(**kwargs)
