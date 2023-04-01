import itertools as it
import operator as op
import re
import typing as t

from rich import box, print
from rich.columns import Columns
from rich.console import ConsoleRenderable, Group
from rich.panel import Panel
from rich.syntax import Syntax

from rich_tables.utils import (
    FIELDS_MAP,
    JSONDict,
    border_panel,
    colored_with_bg,
    format_with_color,
    get_val,
    md_panel,
    new_table,
    predictably_random_color,
    progress_bar,
    simple_panel,
    time2human,
    wrap,
)


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
    return wrap(state, state_color(state))


def resolved_border_style(resolved: bool) -> str:
    return {True: "green", False: "yellow"}.get(resolved, "")


def comment_panel(comment: JSONDict, **kwargs: t.Any) -> Panel:
    reactions = [
        wrap(f":{r['content'].lower()}:", "bold") + " " + get_val(r, "user")
        for r in comment.get("reactions", [])
    ]
    text = comment["body"]
    split = re.split(r"(?=```.*)```", text)
    rends = []
    for idx, content in enumerate(split):
        if content:
            if idx % 2 == 0:
                content = md_panel(content)
            else:
                lang, codeblock = content.split("\n", 1)
                content = FIELDS_MAP[lang or "python"](text)
            rends.append(content)
    return simple_panel(
        Group(*rends),
        **{
            "title": " ".join(get_val(comment, f) for f in ["author", "createdAt"]),
            "subtitle": "\n".join(reactions) + "\n",
            **kwargs,
        },
    )


def thread_panel(thread: JSONDict, files: t.List[ConsoleRenderable]) -> Panel:
    return border_panel(
        new_table(rows=it.zip_longest(*(iter(files),) * 2)),
        highlight=False,
        border_style=resolved_border_style(thread["isResolved"]),
        title=wrap(thread["path"], "b magenta")
        + " "
        + fmt_state("RESOLVED" if thread["isResolved"] else "PENDING"),
        subtitle=fmt_state("OUTDATED") if thread["isOutdated"] else "",
    )


def diff_panel(title: str, rows: t.List[t.List[ConsoleRenderable]]) -> Panel:
    return border_panel(
        new_table(rows=rows),
        title=title,
        border_style=f"dim {predictably_random_color(title)}",
    )


PR_FIELDS_MAP = {
    "state": lambda x: wrap(fmt_state(x), "b"),
    "reviewDecision": lambda x: wrap(fmt_state(x), "b"),
    "dates": lambda x: new_table(
        rows=[
            [wrap(r" ⬤ ", "b green"), time2human(x["created"])],
            [wrap(r" ◯ ", "b yellow"), time2human(x["updated"])],
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


class Diff(t.TypedDict):
    additions: int
    deletions: int


class File(Diff):
    path: str


class Commit(Diff):
    committedDate: str
    statusCheckRollup: str
    message: str


class Comment(t.TypedDict):
    author: str
    body: str
    createdAt: str


class Review(Comment):
    state: str
    comments: t.List[Comment]


class ReviewThread(t.TypedDict):
    path: str
    line: int
    isResolved: bool
    isOutdated: bool
    resolvedBy: str
    diffSide: str
    startLine: int
    comments: t.List[Comment]


class PullRequest(t.TypedDict):
    additions: int
    author: str
    body: str
    comments: t.List[Comment]
    commits: t.List[Commit]
    createdAt: str
    deletions: int
    files: t.List[File]
    isReadByViewer: bool
    labels: t.List[str]
    participants: t.List[str]
    repository: str
    reviewDecision: str
    reviewRequests: t.List[str]
    reviewThreads: t.List[ReviewThread]
    reviews: t.List[Review]
    state: str
    timelineItems: t.List[JSONDict]
    title: str
    updatedAt: str
    url: str


def pulls_table(data: t.List[JSONDict]) -> t.Iterable[t.Union[str, ConsoleRenderable]]:
    FIELDS_MAP.update(PR_FIELDS_MAP)

    pr = data[0]
    if pr and "additions" in pr:
        pr["files"].append(
            dict(additions=pr.pop("additions", ""), deletions=pr.pop("deletions", ""))
        )
    pr["dates"] = {"created": pr.pop("createdAt"), "updated": pr.pop("updatedAt")}

    repo, state, decision = pr["repository"], pr["state"], pr["reviewDecision"]
    fields = "author", "dates", "participants"
    yield border_panel(
        new_table(
            rows=[
                [
                    Columns(
                        map(
                            lambda f: simple_panel(
                                get_val(pr, f),
                                title=wrap(f, "b"),
                                title_align="center",
                                expand=True,
                                align="center",
                            ),
                            fields,
                        ),
                        align="center",
                        expand=True,
                        equal=True,
                    )
                ],
                [md_panel(pr["body"])],
            ]
        ),
        title=wrap(repo, f"b {predictably_random_color(repo)}"),
        box=box.DOUBLE_EDGE,
        border_style=state_color("MERGED")
        if state == "MERGED"
        else state_color(decision),
        subtitle=(
            f"[b][{state_color(decision)}]{decision}[/]"
            + " [#ffffff]//[/] "
            + f"{fmt_state(pr['state'])}[/]"
        ),
        expand=False,
        align="center",
        title_align="center",
        subtitle_align="center",
    )

    yield new_table(rows=[[get_val(pr, "files"), get_val(pr, "commits")]])

    global_comments: t.List[ConsoleRenderable] = []
    raw_global_comments = pr["comments"] + pr["reviews"]
    for comment in sorted(raw_global_comments, key=op.itemgetter("createdAt")):
        state = comment.get("state", "COMMENTED")
        subtitle = "comment"
        if state != "COMMENTED":
            subtitle = "review - " + wrap(state, f"b {state_color(state)}")
        if state != "COMMENTED" or comment["body"]:
            global_comments.append(
                comment_panel(
                    comment,
                    subtitle=subtitle,
                    border_style=predictably_random_color(comment["author"]),
                    box=box.HEAVY,
                )
            )
    if global_comments:
        yield border_panel(
            new_table(rows=[[x] for x in global_comments]), title="Reviews & Comments"
        )

    yield new_table(rows=[[get_val(pr, "reviewRequests")]])
    total_threads = len(pr["reviewThreads"])
    if not total_threads:
        return

    resolved_threads = len(list(filter(lambda x: x["isResolved"], pr["reviewThreads"])))
    table = new_table()
    table.add_row(
        border_panel(
            progress_bar(resolved_threads, total_threads),
            title=f"{resolved_threads} / {total_threads} resolved",
            border_style="dim yellow",
        )
    )

    for thread in pr["reviewThreads"]:
        files: t.List[ConsoleRenderable] = []
        for diff_hunk, comments in it.groupby(
            sorted(
                thread["comments"],
                key=lambda x: (x.get("diffHunk", ""), x.get("createdAt", "")),
            ),
            lambda x: x.get("diffHunk") or "",
        ):
            rows = it.chain.from_iterable(
                [[x], [""]] for x in map(comment_panel, comments)
            )
            comments_col = new_table(rows=rows)
            diff = Syntax(
                diff_hunk,
                "diff",
                theme="paraiso-dark",
                background_color="black",
                # word_wrap=True,
            )
            files.append(
                new_table(rows=[[diff, simple_panel(comments_col)]], highlight=False)
            )

        table.add_row(thread_panel(thread, files))
    yield border_panel(table)
