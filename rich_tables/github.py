"""Functionality to display data from GitHub API."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import chain, groupby
from typing import Any, Callable, Iterable, List, Mapping, Union

from rich import box
from rich.console import ConsoleRenderable, RenderableType
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from typing_extensions import TypedDict

from .fields import FIELDS_MAP, _get_val, get_val
from .generic import flexitable
from .utils import (
    JSONDict,
    border_panel,
    diff_dt,
    format_with_color,
    format_with_color_on_black,
    list_table,
    md_panel,
    new_table,
    predictably_random_color,
    simple_panel,
    wrap,
)


def fmt_add_del(file: JSONDict) -> List[str]:
    added, deleted = file["additions"], file["deletions"]
    additions = f"+{added}" if added else ""
    deletions = f"-{deleted}" if deleted else ""
    return [wrap(additions.rjust(5), "b green"), wrap(deletions.rjust(3), "b red")]


def state_color(state: str) -> str:
    return {
        "True": "green",
        True: "green",
        "APPROVED": "green",
        "RESOLVED": "s green",
        "OPEN": "green",
        "MERGED": "magenta",
        "CLOSED": "b red",
        "PENDING": "yellow",
        "OUTDATED": "yellow",
        "COMMENTED": "yellow",
        "CHANGES_REQUESTED": "b red",
        "REVIEW_REQUIRED": "red",
        "DISMISSED": "gray42",
        "False": "red",
    }.get(state, "default")


def fmt_state(state: str) -> str:
    return wrap(state, f"b {state_color(state)}")


def diff_panel(title: str, rows: List[List[str]]) -> Panel:
    return border_panel(
        new_table(rows=rows),
        title=title,
        border_style=f"dim {predictably_random_color(title)}",
    )


PR_FIELDS_MAP: Mapping[str, Callable[..., RenderableType]] = {
    "statusCheckRollup": lambda x: {
        "SUCCESS": ":green_square:",
        "FAILURE": ":red_square:",
        "PENDING": ":yellow_square:",
        "None": "",
    }[x],
    "state": lambda x: wrap(fmt_state(x), "b"),
    "reviewDecision": lambda x: wrap(fmt_state(x), "b"),
    "dates": lambda x: new_table(
        rows=[
            [wrap(r" ⬤ ", "b green"), diff_dt(x[0])],
            [wrap(r" ◯ ", "b yellow"), diff_dt(x[1])],
        ]
    ),
    "path": lambda x: wrap(x, "b"),
    "message": lambda x: wrap(x, "i"),
    "files": lambda files: diff_panel(
        "files", [[*fmt_add_del(f), get_val(f, "path")] for f in files]
    ),
    "reviewRequests": format_with_color_on_black,
    "participants": lambda x: "\n".join(
        map(format_with_color, map("{:^20}".format, x))
    ),
}


class Diff(TypedDict):
    additions: int
    deletions: int


class File(Diff):
    path: str


@dataclass
class Commit:
    additions: int
    deletions: int
    committedDate: str
    message: str
    statusCheckRollup: str

    @property
    def diff(self) -> List[str]:
        additions = f"+{self.additions}" if self.additions else ""
        deletions = f"-{self.deletions}" if self.deletions else ""
        return [wrap(additions.rjust(5), "b green"), wrap(deletions.rjust(3), "b red")]

    @property
    def parts(self) -> List[str]:
        return [
            *self.diff,
            get_val(self, "statusCheckRollup"),
            get_val(self, "message"),
            get_val(self, "committedDate"),
        ]


@dataclass
class Commits:
    commits: List[Commit]

    @property
    def panel(self) -> Panel:
        return diff_panel("commits", [commit.parts for commit in self.commits])


@dataclass
class Reaction:
    user: str
    content: str

    def __str__(self) -> str:
        return f":{self.content.lower()}: {_get_val(self.user, 'author')}"


class PanelMixin:
    def get_title(self, fields: List[str]) -> str:
        return " ".join(get_val(self, f) for f in fields)

    @property
    def title(self) -> str:
        return self.get_title(["author", "createdAt"])

    @property
    def panel(self) -> Panel:
        raise NotImplementedError


@dataclass
class Content:
    createdAt: str
    author: str
    body: str


@dataclass
class IssueComment(PanelMixin, Content):
    reactions: List[Reaction]

    @property
    def panel(self) -> Panel:
        return border_panel(
            list_table([md_panel(self.body)]),
            border_style="b yellow",
            title=self.title,
            box=box.ROUNDED,
        )


@dataclass
class ReviewComment(IssueComment):
    outdated: bool
    path: str
    diffHunk: str
    pullRequestReview: str

    @classmethod
    def make(cls, reactions: List[JSONDict], **kwargs: Any) -> "ReviewComment":
        kwargs["reactions"] = [Reaction(**c) for c in reactions]
        return cls(**kwargs)

    @property
    def diff(self) -> Syntax:
        return Syntax(
            self.diffHunk, "diff", theme="paraiso-dark", background_color="black"
        )

    @property
    def review_id(self) -> str:
        return self.pullRequestReview

    def get_panel(self, **kwargs: Any) -> Panel:
        return md_panel(
            self.body.replace("suggestion", "python"),
            title=self.title,
            subtitle="\n".join(map(str, self.reactions)) + "\n",
            **kwargs,
        )


@dataclass
class ReviewThread(PanelMixin):
    path: str
    isResolved: bool
    isOutdated: bool
    resolvedBy: str
    comments: List[ReviewComment]

    @classmethod
    def make(cls, comments: List[JSONDict], **kwargs: Any) -> "ReviewThread":
        kwargs["comments"] = [ReviewComment.make(**c) for c in comments]
        return cls(**kwargs)

    @property
    def review_id(self) -> str:
        return self.comments[0].review_id

    @property
    def createdAt(self) -> str:
        return self.comments[0].createdAt

    @property
    def formatted_state(self) -> str:
        return (
            (
                fmt_state("RESOLVED")
                + wrap(" by ", "white")
                + format_with_color(self.resolvedBy)
            )
            if self.isResolved
            else fmt_state("PENDING")
        )

    @property
    def title(self) -> str:
        return " ".join(
            [
                wrap(self.path, "b magenta"),
                self.formatted_state,
                fmt_state("OUTDATED") if self.isOutdated else "",
            ]
        )

    @property
    def panel(self) -> Panel:
        comments = self.comments
        comments_col = list_table(
            (c.get_panel() for c in comments), padding=(1, 0, 0, 0)
        )
        return border_panel(
            new_table(
                rows=[[self.comments[0].diff, simple_panel(comments_col)]],
                highlight=False,
            ),
            highlight=False,
            border_style="green" if self.isResolved else "yellow",
            title=self.title,
        )


@dataclass
class Review(PanelMixin, Content):
    id: str
    state: str
    threads: List[ReviewThread]
    comments: List[ReviewComment]

    @property
    def panel(self) -> Panel:
        self.threads.sort(key=lambda t: t.isResolved)

        return border_panel(
            list_table([md_panel(self.body), *(t.panel for t in self.threads)]),
            subtitle=self.state,
            border_style=state_color(self.state),
            title=self.title,
            box=box.HEAVY,
        )

    @property
    def status(self) -> str:
        resolved_count = sum((t.isResolved for t in self.threads))
        total_count = len(self.threads)
        return (
            wrap(" ⬤ " * resolved_count, "b green")
            + wrap(" ◯ " * (total_count - resolved_count), "b red")
            + " resolved"
            if total_count
            else ""
        )

    @property
    def title(self) -> str:
        return self.get_title(["state", "author", "createdAt", "status"])


@dataclass
class PullRequest:
    id: str
    additions: int
    author: str
    body: str
    comments: List[IssueComment]
    commits: Commits
    createdAt: str
    deletions: int
    files: List[File]
    labels: List[str]
    participants: List[str]
    repository: str
    reviewDecision: str
    reviewRequests: List[str]
    reviewThreads: List[ReviewThread]
    reviews: List[Review]
    state: str
    title: str
    updatedAt: str
    url: str

    @property
    def dates(self) -> tuple[str, str]:
        return self.createdAt, self.updatedAt


@dataclass
class PullRequestTable(PullRequest):
    reviews: List[Review]
    comments: List[IssueComment]

    @classmethod
    def make(cls, reviews: List[JSONDict], **kwargs: Any) -> "PullRequestTable":
        kwargs["commits"] = Commits([Commit(**c) for c in kwargs["commits"]])
        kwargs["comments"] = [IssueComment(**c) for c in kwargs["comments"]]
        threads = [ReviewThread.make(**rt) for rt in kwargs["reviewThreads"]]
        review_comments = list(chain.from_iterable((t.comments for t in threads)))
        review_comments.sort(key=lambda c: c.review_id)
        comments_by_review_id = {
            r: list(c) for r, c in groupby(review_comments, lambda c: c.review_id)
        }
        threads.sort(key=lambda t: t.review_id)
        threads_by_review_id = {
            r: list(trs) for r, trs in groupby(threads, lambda t: t.review_id)
        }
        kwargs["reviews"] = [
            Review(
                **r,
                threads=threads_by_review_id.get(r["id"], []),
                comments=comments_by_review_id.get(r["id"], []),
            )
            for r in reviews
            if (
                r["id"] in threads_by_review_id
                and r["state"] != "COMMENTED"
                or r["body"]
            )
        ]
        return cls(**kwargs)

    def make_info_subpanel(self, attr: str) -> Panel:
        return simple_panel(
            get_val(self, attr),
            title=wrap(attr, "b"),
            title_align="center",
            expand=True,
            align="center",
        )

    @property
    def name(self) -> str:
        return wrap(self.title, f"b {predictably_random_color(self.title)}")

    @property
    def repo(self) -> str:
        return wrap(self.repository, f"b {predictably_random_color(self.repository)}")

    @property
    def pr_state(self) -> str:
        return "MERGED" if self.state == "MERGED" else self.reviewDecision

    @property
    def info(self) -> Panel:
        fields = "author", "dates", "participants", "reviewRequests"
        pairs = [(f, getattr(self, f)) for f in fields]
        field_rows = [[flexitable({f: v})] for f, v in pairs if v]
        return border_panel(
            new_table(rows=[*field_rows, [md_panel(self.body)], [self.files_commits]]),
            title=f"{self.name} @ {self.repo}",
            box=box.DOUBLE_EDGE,
            border_style=state_color(self.pr_state),
            subtitle=(
                f"[b]{fmt_state(self.reviewDecision)}[white] // "
                + f"{fmt_state(self.state)}[/]"
            ),
            align="center",
            title_align="center",
            subtitle_align="center",
        )

    @property
    def files_commits(self) -> Table:
        return new_table(rows=[[get_val(self, "files"), self.commits.panel]])

    @property
    def contents(self) -> List[PanelMixin]:
        return [*self.reviews, *self.comments]

    @property
    def panels(self) -> Iterable[Panel]:
        comments = sorted(self.contents, key=lambda c: c.createdAt)
        for comment in comments:
            yield comment.panel


def pulls_table(
    data: List[Mapping[str, Any]],
) -> Iterable[Union[str, ConsoleRenderable]]:
    FIELDS_MAP.update(PR_FIELDS_MAP)

    pr = data[0]
    pr_table = PullRequestTable.make(**pr)
    yield pr_table.info
    yield from pr_table.panels
