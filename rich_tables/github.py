"""Functionality to display data from GitHub API."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from itertools import islice
from typing import TYPE_CHECKING, Any, Callable, Protocol

from rich import box
from rich.syntax import Syntax
from typing_extensions import Literal, TypedDict

from .fields import FIELDS_MAP, get_val
from .generic import flexitable
from .utils import (
    JSONDict,
    border_panel,
    fmt_time,
    format_with_color,
    format_with_color_on_black,
    list_table,
    md_panel,
    new_table,
    predictably_random_color,
    simple_panel,
    sortgroup_by,
    timestamp2datetime,
    wrap,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from rich.console import ConsoleRenderable, RenderableType
    from rich.panel import Panel
    from rich.table import Table

SECONDS_PER_DAY = 86400


def b_green(text: str) -> str:
    """Make the text bold green."""
    return wrap(text, "b green")


def b_red(text: str) -> str:
    """Make the text bold red."""
    return wrap(text, "b red")


def diff_dt(timestamp: str | float, acc: int = 2) -> str:
    try:
        datetime = timestamp2datetime(timestamp)
    except ValueError:
        return str(timestamp)

    diff = datetime.timestamp() - time.time()
    fmted = " ".join(islice(fmt_time(int(diff)), acc))

    strtime = datetime.strftime("%F" if abs(diff) >= SECONDS_PER_DAY else "%T")

    return f"{(b_red if diff < 0 else b_green)(fmted)} {strtime}"


def fmt_add_del(added: int, deleted: int) -> list[str]:
    """Format added and deleted diff counts."""
    additions = f"+{added}" if added else ""
    deletions = f"-{deleted}" if deleted else ""
    return [b_green(additions.rjust(5)), b_red(deletions.rjust(3))]


COLOR_BY_STATE = defaultdict(
    lambda: "default",
    {
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
    },
)


def fmt_state(state: str) -> str:
    return wrap(state, f"b {COLOR_BY_STATE[state]}")


def diff_panel(title: str, rows: list[list[str]]) -> Panel:
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
            [b_green(r" ⬤ "), diff_dt(x[0])],
            [wrap(r" ◯ ", "b yellow"), diff_dt(x[1])],
        ]
    ),
    "path": lambda x: wrap(x, "b"),
    "message": lambda x: wrap(x, "i"),
    "files": lambda files: diff_panel(
        "files",
        [
            [*fmt_add_del(f["additions"], f["deletions"]), get_val(f, "path")]
            for f in files
        ],
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
    def diff(self) -> list[str]:
        return fmt_add_del(self.additions, self.deletions)

    @property
    def parts(self) -> list[str]:
        return [
            *self.diff,
            get_val(self, "statusCheckRollup"),
            get_val(self, "message"),
            get_val(self, "committedDate"),
        ]


@dataclass
class Commits:
    commits: list[Commit]

    @property
    def panel(self) -> Panel:
        return diff_panel("commits", [commit.parts for commit in self.commits])


@dataclass
class Reaction:
    user: str
    content: str

    def __str__(self) -> str:
        return f":{self.content.lower()}: {get_val(self, 'user')}"


class CreatedMixin(Protocol):
    @property
    def created(self) -> str:
        raise NotImplementedError


@dataclass
class PanelMixin:
    def get_title(self, fields: list[str]) -> str:
        return " ".join(get_val(self, f) for f in fields)

    @property
    def panel(self) -> Panel:
        raise NotImplementedError


@dataclass
class CreatedPanelMixin(CreatedMixin, PanelMixin):
    pass


@dataclass
class Content(CreatedPanelMixin):
    createdAt: str
    author: str
    body: str

    @property
    def created_at(self) -> str:
        return f"""[white]{self.createdAt.replace("T", " ").replace("Z", "")}[/]"""

    @property
    def created(self) -> str:
        return self.created_at


@dataclass
class Comment(Content):
    reactions: list[Reaction]

    @classmethod
    def make(cls, reactions: list[JSONDict], **kwargs: Any) -> Comment:
        kwargs["reactions"] = [Reaction(**c) for c in reactions]
        return cls(**kwargs)

    @property
    def title(self) -> str:
        return self.get_title(["author", "created_at"])

    @property
    def subtitle(self) -> str:
        return (
            " ".join(map(str, self.reactions))
            .replace(":laugh:", ":laughing:")
            .replace(":hooray:", ":party_popper:")
        )


@dataclass
class IssueComment(Comment):
    @property
    def panel(self) -> Panel:
        return border_panel(
            list_table([md_panel(self.body)]),
            border_style="b yellow",
            title=self.title,
            subtitle=self.subtitle,
            box=box.ROUNDED,
        )


@dataclass
class ReviewComment(Comment):
    outdated: bool
    path: str
    diffHunk: str
    pullRequestReview: str

    @property
    def diff(self) -> Syntax:
        return Syntax(
            self.diffHunk, "diff", theme="paraiso-dark", background_color="black"
        )

    @property
    def review_id(self) -> str:
        return self.pullRequestReview

    @property
    def panel(self) -> Panel:
        return md_panel(
            self.body.replace("suggestion", "python"),
            title=self.title,
            subtitle=self.subtitle,
        )


class ResolvedMixin:
    @property
    def resolved(self) -> bool:
        raise NotImplementedError

    @property
    def border_color(self) -> str:
        return "green" if self.resolved else "yellow"


@dataclass
class ReviewThread(CreatedPanelMixin, ResolvedMixin):
    path: str
    isResolved: bool
    isOutdated: bool
    resolvedBy: str
    comments: list[ReviewComment]
    verbose: bool

    @property
    def resolved(self) -> bool:
        return self.isResolved

    @classmethod
    def make(cls, comments: list[JSONDict], **kwargs: Any) -> ReviewThread:
        kwargs["comments"] = [ReviewComment.make(**c) for c in comments]
        return cls(**kwargs)

    @property
    def review_id(self) -> str:
        return self.comments[0].review_id

    @property
    def created(self) -> str:
        return self.comments[0].created_at

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
        content: RenderableType
        if self.verbose or not self.resolved:
            comments_col = list_table((c.panel for c in comments), padding=(1, 0, 0, 0))
            content = new_table(
                rows=[[self.comments[0].diff, simple_panel(comments_col)]],
                highlight=False,
            )
        else:
            content = ""
        return border_panel(
            content,
            highlight=False,
            border_style=self.border_color,
            title=self.title,
        )


@dataclass
class Review(Content, ResolvedMixin):
    id: str
    state: str
    threads: list[ReviewThread]
    comments: list[ReviewComment]

    verbose: bool

    @property
    def resolved(self) -> bool:
        return all(t.resolved for t in self.threads)

    @property
    def panel(self) -> Panel:
        rows = []
        if self.body:
            rows.append(md_panel(self.body))

        if not self.resolved or self.verbose:
            self.threads.sort(key=lambda t: t.resolved)
            rows.extend(t.panel for t in self.threads)

        return border_panel(
            list_table(rows),
            subtitle=self.state,
            border_style=self.border_color,
            title=self.title,
            box=box.HEAVY,
        )

    @property
    def status(self) -> str:
        resolved_count = sum(t.isResolved for t in self.threads)
        if total_count := len(self.threads):
            return (
                wrap("RESOLVED", COLOR_BY_STATE["RESOLVED"])
                if total_count == resolved_count
                else b_green(" ⬤ " * resolved_count)
                + b_red(" ◯ " * (total_count - resolved_count))
            )
        return ""

    @property
    def title(self) -> str:
        return self.get_title(["state", "author", "created_at", "status"])


@dataclass
class Issue:
    number: int
    title: str
    state: Literal["OPEN", "CLOSED"]
    url: str

    @property
    def status(self) -> str:
        return {"OPEN": "[b green][/]", "CLOSED": "[b magenta][/]"}[self.state]

    @property
    def fmt(self) -> str:
        return f"{self.title} {self.url}"


@dataclass
class PullRequest:
    id: str
    createdAt: str
    author: str
    body: str
    additions: int
    commits: Commits
    deletions: int
    files: list[File]
    headRefName: str
    labels: list[str]
    participants: list[str]
    repository: str
    reviewDecision: str
    reviewRequests: list[str]
    reviewThreads: list[ReviewThread]
    reviews: list[Review]
    comments: list[Comment]
    state: str
    title: str
    updatedAt: str
    url: str
    issues: list[Issue]

    verbose: bool

    @property
    def dates(self) -> tuple[str, str]:
        return self.createdAt, self.updatedAt


@dataclass
class PullRequestTable(PullRequest):
    @classmethod
    def make(cls, reviews: list[JSONDict], **kwargs: Any) -> PullRequestTable:
        verbose = kwargs["verbose"]
        threads = [
            ReviewThread.make(**rt, verbose=verbose) for rt in kwargs["reviewThreads"]
        ]
        comments_by_review_id = dict(
            sortgroup_by(
                (c for t in threads for c in t.comments),
                lambda c: c.review_id,
            )
        )
        threads_by_review_id = dict(sortgroup_by(threads, lambda t: t.review_id))
        return cls(
            commits=Commits([Commit(**c) for c in kwargs.pop("commits", [])]),
            comments=[IssueComment.make(**c) for c in kwargs.pop("comments", [])],
            reviews=[
                Review(
                    **r,
                    threads=threads_by_review_id.pop(r["id"], []),
                    comments=comments_by_review_id.pop(r["id"], []),
                    verbose=verbose,
                )
                for r in reviews
                if (r["id"] in threads_by_review_id or r["body"])
            ],
            issues=[Issue(**i) for i in kwargs.pop("closingIssuesReferences")],
            **kwargs,
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
    def fixed_issues(self) -> RenderableType:
        return list_table([i.fmt for i in self.issues])

    @property
    def info(self) -> Panel:
        fields = (
            "author",
            "dates",
            "headRefName",
            "participants",
            "reviewRequests",
            "fixed_issues",
        )
        pairs = {f: v for f in fields if (v := getattr(self, f))}
        field_rows = flexitable(pairs)
        return border_panel(
            new_table(rows=[[field_rows], [md_panel(self.body)], [self.files_commits]]),
            title=f"{self.name} @ {self.repo}",
            box=box.DOUBLE_EDGE,
            border_style=COLOR_BY_STATE[self.pr_state],
            subtitle=(
                wrap(
                    " ".join(
                        [
                            fmt_state(self.reviewDecision),
                            wrap("//", "white"),
                            fmt_state(self.state),
                        ]
                    ),
                    "b",
                )
            ),
            vertical_align="middle",
            title_align="center",
            subtitle_align="center",
        )

    @property
    def files_commits(self) -> Table:
        return new_table(rows=[[get_val(self, "files"), self.commits.panel]])

    @property
    def timestamped_contents(self) -> list[CreatedPanelMixin]:
        return [*self.reviews, *self.comments]

    @property
    def panels(self) -> Iterable[Panel]:
        for content in sorted(self.timestamped_contents, key=lambda c: c.created):
            yield content.panel


def pulls_table(
    data: list[Mapping[str, Any]], **kwargs: Any
) -> Iterable[str | ConsoleRenderable]:
    FIELDS_MAP.update(PR_FIELDS_MAP)

    pr = data[0]
    pr_table = PullRequestTable.make(**pr, verbose=kwargs["verbose"])
    yield pr_table.info
    yield from pr_table.panels
