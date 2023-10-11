"""Functionality to display data from GitHub API."""
from dataclasses import dataclass
from itertools import groupby
from typing import Any, Callable, Iterable, List, Mapping, Union

from rich import box
from rich.columns import Columns
from rich.console import ConsoleRenderable, RenderableType
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from typing_extensions import TypedDict

from .fields import FIELDS_MAP, get_val
from .utils import (
    JSONDict,
    border_panel,
    colored_with_bg,
    format_with_color,
    list_table,
    md_panel,
    new_table,
    predictably_random_color,
    simple_panel,
    time2human,
    wrap,
)


class Diff(TypedDict):
    additions: int
    deletions: int


class File(Diff):
    path: str


class Commit(Diff):
    committedDate: str
    statusCheckRollup: str
    message: str


@dataclass
class Reaction:
    user: str
    content: str

    def __str__(self) -> str:
        return f":{self.content.lower()}: {self.user}"


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
            list_table([simple_panel(md_panel(self.body))]),
            border_style="b yellow",
            title=self.title,
            box=box.HEAVY,
        )


@dataclass
class ReviewComment(IssueComment):
    outdated: bool
    path: str
    diffHunk: str
    pullRequestReview: str

    @property
    def diff(self) -> Syntax:
        return Syntax(
            self.diffHunk, "diff", theme="paraiso-dark", background_color="black"
        )

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
        kwargs["comments"] = [ReviewComment(**c) for c in comments]
        return cls(**kwargs)

    @property
    def review_id(self) -> str:
        return self.comments[0].pullRequestReview

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
        comments = self.comments[-1:] if self.isResolved else self.comments
        comments_col = list_table(
            (c.get_panel() for c in comments), padding=(1, 0, 0, 0)
        )
        return border_panel(
            new_table(
                rows=[[self.comments[0].diff, simple_panel(comments_col)]],
                highlight=False,
            ),
            highlight=False,
            border_style=resolved_border_style(self.isResolved),
            title=self.title,
        )


@dataclass
class Review(PanelMixin, Content):
    id: str
    state: str
    threads: List[ReviewThread]

    @property
    def panel(self) -> Panel:
        self.threads.sort(key=lambda t: t.isResolved)

        return border_panel(
            list_table(
                [simple_panel(md_panel(self.body)), *(t.panel for t in self.threads)]
            ),
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
    commits: List[Commit]
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
        "PENDING": "yellow",
        "OUTDATED": "yellow",
        "COMMENTED": "yellow",
        "CHANGES_REQUESTED": "#ffa500",
        "REVIEW_REQUIRED": "red",
        "DISMISSED": "gray42",
        "False": "red",
    }.get(state, "default")


def fmt_state(state: str) -> str:
    return wrap(state, f"b {state_color(state)}")


def resolved_border_style(resolved: bool) -> str:
    return "green" if resolved else "yellow"


def diff_panel(title: str, rows: List[List[str]]) -> Panel:
    return border_panel(
        new_table(rows=rows),
        title=title,
        border_style=f"dim {predictably_random_color(title)}",
    )


PR_FIELDS_MAP: Mapping[str, Callable[..., RenderableType]] = {
    "state": lambda x: wrap(fmt_state(x), "b"),
    "reviewDecision": lambda x: wrap(fmt_state(x), "b"),
    "dates": lambda x: new_table(
        rows=[
            [wrap(r" ⬤ ", "b green"), time2human(x[0])],
            [wrap(r" ◯ ", "b yellow"), time2human(x[1])],
        ]
    ),
    "path": lambda x: wrap(x, "b"),
    "message": lambda x: wrap(x, "i"),
    "files": lambda files: diff_panel(
        "files", [[*fmt_add_del(f), get_val(f, "path")] for f in files]
    ),
    "commits": lambda commits: diff_panel(
        "commits",
        [
            [
                *fmt_add_del(commit),
                get_val(commit, "message"),
                get_val(commit, "committedDate"),
            ]
            for commit in commits
        ],
    ),
    "reviewRequests": lambda x: "  ".join(map(colored_with_bg, x)),
    "participants": lambda x: "\n".join(
        map(format_with_color, map("{:^20}".format, x))
    ),
}


@dataclass
class PullRequestTable(PullRequest):
    reviews: List[Review]
    comments: List[IssueComment]

    @classmethod
    def make(cls, reviews: List[JSONDict], **kwargs: Any) -> "PullRequestTable":
        kwargs["comments"] = [IssueComment(**c) for c in kwargs["comments"]]
        threads = [ReviewThread.make(**rt) for rt in kwargs["reviewThreads"]]
        threads.sort(key=lambda t: t.review_id)
        threads_by_review_id = {
            r: list(trs) for r, trs in groupby(threads, lambda t: t.review_id)
        }
        kwargs["reviews"] = [
            Review(**r, threads=threads_by_review_id.get(r["id"], []))
            for r in reviews
            # if r["body"]
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
    def repo(self) -> str:
        return wrap(self.repository, f"b {predictably_random_color(self.repository)}")

    @property
    def pr_state(self) -> str:
        return "MERGED" if self.state == "MERGED" else self.reviewDecision

    @property
    def info(self) -> Panel:
        fields = "author", "dates", "participants", "reviewRequests"
        return border_panel(
            new_table(
                rows=[
                    [
                        Columns(
                            map(self.make_info_subpanel, fields),
                            align="center",
                            expand=True,
                            equal=True,
                        )
                    ],
                    [md_panel(self.body)],
                ]
            ),
            title=self.repo,
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
        return new_table(rows=[[get_val(self, "files"), get_val(self, "commits")]])

    @property
    def contents(self) -> List[PanelMixin]:
        return [*self.reviews, *self.comments]

    @property
    def panels(self) -> Iterable[Panel]:
        comments = sorted(self.contents, key=lambda c: c.createdAt)
        for comment in comments:
            yield comment.panel


def pulls_table(
    data: List[Mapping[str, Any]]
) -> Iterable[Union[str, ConsoleRenderable]]:
    FIELDS_MAP.update(PR_FIELDS_MAP)

    pr = data[0]
    pr_table = PullRequestTable.make(**pr)
    yield pr_table.info
    yield pr_table.files_commits
    yield from pr_table.panels
