from __future__ import annotations

import inspect
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, Protocol, runtime_checkable

from rich import box
from rich.console import RichCast
from typing_extensions import Self

from .fields import get_val
from .utils import (
    border_panel,
    format_with_color_on_black,
    human_dt,
    link,
    list_table,
    md_panel,
    new_table,
    wrap,
)

if TYPE_CHECKING:
    from rich.console import ConsoleRenderable

TypeName = Literal["GithubComment"]

STATE_COLORS: dict[str, str] = {
    "DRAFT": "b gray39",
    "CHANGES_REQUESTED": "b red",
    "APPROVED": "b green",
    "REVIEW_REQUIRED": "b orange1",
    "WAIT": "b blue",
    "COMMENTED": "b yellow",
}


@runtime_checkable
class RichCastFactory(RichCast, Protocol):
    @classmethod
    def make(cls, *args: Any, **kwargs: Any) -> Self:
        return cls(*args, **kwargs)


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


@dataclass
class BaseComment:
    body: str
    author: str
    created_at: str
    url: str
    state: Literal[
        "DRAFT", "CHANGES_REQUESTED", "APPROVED", "REVIEW_REQUIRED", "WAIT", "COMMENTED"
    ]
    reactions: list[GithubReaction]


class GithubComment(BaseComment):
    @classmethod
    def make(cls, *args: Any, **kwargs: Any) -> Self:
        kwargs["reactions"] = [GithubReaction(**r) for r in kwargs.get("reactions", [])]
        return cls(*args, **kwargs)

    def __rich__(self) -> ConsoleRenderable:
        created = link(get_val(self, "created_at"), self.url)
        author = get_val(self, "author")
        return md_panel(
            self.body,
            title=f"{author} {created}",
            subtitle=" ".join(map(str, self.reactions)),
            border_style=STATE_COLORS[self.state],
            box=box.ROUNDED,
        )


@dataclass
class GithubLabel(RichCastFactory):
    name: str
    color: str
    url: str | None = None

    def __rich__(self) -> str:
        text = wrap(self.name, f"b #{self.color}")
        if self.url:
            text = link(text, self.url)
        return text



@dataclass
class IssueReference(RichCastFactory):
    number: int
    title: str
    url: str | None = None

    def __rich__(self) -> str:
        text = wrap(f"#{self.number} {self.title}", "b")
        if self.url:
            text = link(text, self.url)
        return text


@dataclass
class GithubPRCard(RichCastFactory, BaseComment):
    title: str
    additions: int
    deletions: int
    labels: list[GithubLabel]
    updated_at: str
    last_comment: GithubComment | None
    closingIssuesReferences: list[IssueReference]

    @classmethod
    def make(cls, *args: Any, **kwargs: Any) -> Self:
        kwargs["labels"] = [GithubLabel.make(**r) for r in kwargs.get("labels", [])]
        kwargs["last_comment"] = (
            GithubComment.make(**lc) if (lc := kwargs.get("last_comment")) else None
        )
        kwargs["closingIssuesReferences"] = [
            IssueReference(**issue)
            for issue in kwargs.get("closingIssuesReferences", [])
        ]
        kwargs.setdefault("additions", 0)
        kwargs.setdefault("deletions", 0)

        return super().make(*args, **kwargs)

    def __rich__(self) -> ConsoleRenderable:
        additions = f"+{self.additions}" if self.additions else ""
        deletions = f"-{self.deletions}" if self.deletions else ""

        meta = new_table(
            rows=[
                [wrap("state", "dim"), wrap(self.state, STATE_COLORS[self.state])],
                [
                    wrap("churn", "dim"),
                    wrap(additions, "b green") + " " + wrap(deletions, "b red"),
                ],
                [wrap("opened", "dim"), human_dt(self.created_at)],
                [wrap("updated", "dim"), human_dt(self.updated_at)],
                [
                    wrap("labels", "dim"),
                    (
                        list_table(list(filter(None, self.labels)))
                        if self.labels
                        else wrap("—", "dim")
                    ),
                ],
                [
                    wrap("issues", "dim"),
                    (
                        list_table(self.closingIssuesReferences)
                        if self.closingIssuesReferences
                        else wrap("—", "dim")
                    ),
                ],
                [
                    wrap("body", "dim"),
                    (md_panel(self.body) if self.body else wrap("—", "dim")),
                ],
                [
                    wrap("last comment", "dim"),
                    self.last_comment or wrap("no comments yet", "dim"),
                ],
            ],
            show_header=False,
            highlight=False,
            box=box.SIMPLE,
            expand=False,
            padding=(0, 1),
        )
        card_title = " ".join(
            [
                wrap(self.title, "b white"),
                wrap("by", "dim"),
                format_with_color_on_black(self.author),
            ]
        )
        return border_panel(
            meta,
            title=card_title,
            title_align="left",
            border_style=STATE_COLORS[self.state],
            subtitle=link(self.url, self.url),
        )


TYPE_BY_NAME: dict[str, type[RichCastFactory]] = {
    name: obj
    for name, obj in inspect.getmembers(sys.modules[__name__], inspect.isclass)
    if issubclass(obj, RichCastFactory) and obj is not RichCastFactory
}


def get_renderable(
    _type: Literal["GithubComment", "GithubPRCard"], **kwargs: Any
) -> RichCast:
    return TYPE_BY_NAME[_type].make(**kwargs)
