"""Functionality to display data from GitHub API."""
import typing as t
from collections import defaultdict
from dataclasses import dataclass

from rich import box
from rich.columns import Columns
from rich.console import ConsoleRenderable
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from typing_extensions import TypedDict

from rich_tables.utils import (
    FIELDS_MAP,
    JSONDict,
    border_panel,
    colored_with_bg,
    format_with_color,
    get_val,
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


class Reaction(TypedDict):
    user: str
    content: str


class Content(TypedDict):
    createdAt: str
    author: str
    body: str


class IssueComment(Content):
    reactions: t.List[Reaction]


class ReviewComment(IssueComment):
    outdated: bool
    path: str
    diffHunk: str
    pullRequestReview: str


class ReviewThread(TypedDict):
    path: str
    isResolved: bool
    isOutdated: bool
    resolvedBy: str
    comments: t.List[ReviewComment]


class Review(Content):
    id: str
    state: str
    threads: t.List[ReviewThread]


@dataclass
class PullRequest:
    id: str
    additions: int
    author: str
    body: str
    comments: t.List[IssueComment]
    commits: t.List[Commit]
    createdAt: str
    deletions: int
    files: t.List[File]
    labels: t.List[str]
    participants: t.List[str]
    repository: str
    reviewDecision: str
    reviewRequests: t.List[str]
    reviewThreads: t.List[ReviewThread]
    reviews: t.List[Review]
    state: str
    title: str
    updatedAt: str
    url: str


def fmt_add_del(file: JSONDict) -> t.List[str]:
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
        "CHANGES_REQUESTED": "yellow",
        "REVIEW_REQUIRED": "red",
        "DISMISSED": "gray42",
        "False": "red",
    }.get(state, "default")


def fmt_state(state: str) -> str:
    return wrap(state, f"b {state_color(state)}")


def resolved_border_style(resolved: bool) -> str:
    return "green" if resolved else "yellow"


def top_level_comment_title(comment: Content) -> str:
    return " ".join(get_val(comment, f) for f in ["state", "author", "createdAt"])


def comment_panel(comment: IssueComment, **kwargs: t.Any) -> Panel:
    reactions = [
        wrap(f":{r['content'].lower()}:", "bold") + " " + get_val(r, "user")
        for r in comment.get("reactions", [])
    ]
    return md_panel(
        comment["body"].replace("suggestion", "python"),
        title=top_level_comment_title(comment),
        subtitle="\n".join(reactions) + "\n",
        **kwargs,
    )


def resolved_title(thread: ReviewThread) -> str:
    if thread["isResolved"]:
        resolved = (
            fmt_state("RESOLVED")
            + wrap(" by ", "white")
            + format_with_color(thread["resolvedBy"])
        )
    else:
        resolved = fmt_state("PENDING")
    return " ".join(
        [
            wrap(thread["path"], "b magenta"),
            resolved,
            fmt_state("OUTDATED") if thread["isOutdated"] else "",
        ]
    )


def diff_panel(title: str, rows: t.List[t.List]) -> Panel:
    return border_panel(
        new_table(rows=rows),
        title=title,
        border_style=f"dim {predictably_random_color(title)}",
    )


def make_thread(thread: ReviewThread) -> Panel:
    comments = thread["comments"][-1:] if thread["isResolved"] else thread["comments"]
    comments_col = list_table(map(comment_panel, comments), padding=(1, 0, 0, 0))
    diff = Syntax(
        thread["comments"][0]["diffHunk"],
        "diff",
        theme="paraiso-dark",
        background_color="black",
    )
    return border_panel(
        new_table(rows=[[diff, simple_panel(comments_col)]], highlight=False),
        highlight=False,
        border_style=resolved_border_style(thread["isResolved"]),
        title=resolved_title(thread),
    )


PR_FIELDS_MAP = {
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
        map(format_with_color, map("{:^20}".format, x))  # noqa
    ),
}


class PullRequestTable(PullRequest):
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

    @staticmethod
    def format_comment(comment: t.Union[Review, IssueComment]) -> Panel:
        if "id" in comment:
            comment["threads"].sort(key=lambda t: t["isResolved"])
            resolved_count = sum((t["isResolved"] for t in comment["threads"]))
            total_count = len(comment["threads"])
            status = wrap(" ⬤ " * resolved_count, "b green") + wrap(
                " ◯ " * (total_count - resolved_count), "b red"
            )

            return border_panel(
                list_table(
                    [
                        simple_panel(md_panel(comment["body"])),
                        *map(make_thread, comment["threads"]),
                    ]
                ),
                subtitle=comment["state"],
                border_style=state_color(comment["state"]),
                title=top_level_comment_title(comment) + f" {status} resolved",
                box=box.HEAVY,
            )

        return comment_panel(comment, border_style="yellow", box=box.HEAVY)

    @property
    def reviews_and_comments(self) -> t.List[t.Union[Review, IssueComment]]:
        return self.reviews + self.comments

    @property
    def top_level_comments(self) -> t.Iterable[Panel]:
        comments = sorted(self.reviews_and_comments, key=lambda c: c["createdAt"])
        for comment in comments:
            yield self.format_comment(comment)


def pulls_table(
    data: t.List[PullRequest],
) -> t.Iterable[t.Union[str, ConsoleRenderable]]:
    FIELDS_MAP.update(PR_FIELDS_MAP)

    pr = data[0]
    pr_table = PullRequestTable(**pr)
    pr_table.reviews = [
        r for r in pr_table.reviews if r["state"] != "COMMENTED" or r["body"]
    ]
    yield pr_table.info
    yield pr_table.files_commits

    review_id_to_threads = defaultdict(list)
    for thread in pr_table.reviewThreads:
        review_id_to_threads[thread["comments"][0]["pullRequestReview"]].append(thread)
    for review in pr_table.reviews:
        review["threads"] = review_id_to_threads[review["id"]]

    yield from pr_table.top_level_comments
