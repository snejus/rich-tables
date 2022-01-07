import itertools as it
import random
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from functools import partial
from typing import Any, Dict, Iterable, List, Optional, Tuple

from rich import box
from rich.align import Align
from rich.console import Console, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Column, Table
from rich.text import Text
from rich.tree import Tree

JSONDict = Dict[str, Any]


def format_new(string: str) -> str:
    return wrap(re.sub(r"(^\s+$)", "[u green]\\1[/u green]", string), "b green")


def format_old(string: str) -> str:
    return wrap(re.sub(r"(^\s+$)", "[u red]\\1[/u red]", string), "b s red")


def fmtdiff(change: str, before: str, after: str) -> str:
    if change == "insert":
        return format_new(after)
    elif change == "delete":
        return format_old(before)
    elif change == "replace":
        return format_old(before) + format_new(after)
    else:
        return before


def make_difftext(before: str, after: str) -> str:
    def preparse(value: str) -> str:
        return value.strip().replace("[]", "~")

    before = preparse(before)
    after = preparse(after)

    matcher = SequenceMatcher(isjunk=lambda x: x in " ,-\\n", a=before, b=after)
    diff = ""
    for code, a1, a2, b1, b2 in matcher.get_opcodes():
        diff = diff + (fmtdiff(code, before[a1:a2], after[b1:b2]) or "")
    return diff


def fmt_time(diff: timedelta, clr: str = "cyan") -> Iterable[str]:
    opts: List[Tuple[int, str]] = [
        (diff.days, "d"),
        (diff.seconds // 3600, "h"),
        (diff.seconds % 3600 // 60, "min"),
        (diff.seconds % 60, "s"),
    ]

    return it.starmap("{:>3}{}".format, filter(lambda x: x[0], opts))


def duration2human(duration: int) -> str:
    return " ".join(fmt_time(timedelta(seconds=duration)))


def time2human(timestamp: Optional[int], acc: int = 1) -> str:
    if not timestamp:
        return "-"
    diff = datetime.now().timestamp() - timestamp
    fmted = " ".join(it.islice(fmt_time(timedelta(seconds=abs(diff))), acc))
    if diff > 0:
        return f"{fmted} ago"
    return f"in {fmted}"


def make_console(**kwargs: Any) -> Console:
    default: JSONDict = dict(force_terminal=True, force_interactive=True)
    return Console(**{**default, **kwargs})


def wrap(text: str, tag: str) -> str:
    return f"[{tag}]{text}[/{tag}]"


def new_table(*args: Any, **kwargs: Any) -> Table:
    default: JSONDict = dict(
        border_style="black",
        show_edge=False,
        show_header=False,
        highlight=True,
        row_styles=["white"],
        expand=False,
    )
    headers = list(map(lambda x: Column(str(x), justify="left") or "", args))
    if len(headers):
        default["header_style"] = "bold misty_rose1"
        default["box"] = box.SIMPLE_HEAVY
        default["show_header"] = True
    rows = kwargs.pop("rows", [])
    table = Table(*headers, **{**default, **kwargs})
    for row in rows:
        if isinstance(row, Iterable):
            table.add_row(*row)
        else:
            table.add_row(row)
    return table


def predictably_random_color(string: str) -> str:
    random.seed(string)
    rand = partial(random.randint, 180, 255)
    return "#{:0>6X}".format(rand() * rand() * rand())


def format_with_color(name: str) -> str:
    return wrap(name, f"b i {predictably_random_color(name)}")


def simple_panel(content: RenderableType, **kwargs: Any) -> Panel:
    default: JSONDict
    default = dict(title_align="left", subtitle_align="left", box=box.SIMPLE, expand=True)
    if kwargs.get("align", "") == "center":
        content = Align.center(content)
    return Panel(content, **{**default, **kwargs})


def border_panel(content: RenderableType, **kwargs: Any) -> Panel:
    return simple_panel(content, **{**dict(box=box.ROUNDED), **kwargs})


def md_panel(content: str, **kwargs: Any) -> Panel:
    return border_panel(Markdown(content), **kwargs)


def comment_panel(comment: Dict[str, str], **kwargs: Any) -> Panel:
    state = comment.get("state") or ""
    author = format_with_color(comment["author"])
    return md_panel(
        re.sub(r"[\[\]\\]", "", comment["body"]),
        padding=1,
        title=" ".join([state, author]),
        subtitle=wrap(comment.get("createdAt") or "", "d"),
        **kwargs,
    )


def syntax_panel(content: str, lexer: str, **kwargs: Any) -> Panel:
    return Panel(
        Syntax(
            content, lexer, theme="paraiso-dark", background_color="black", word_wrap=True
        ),
        style="on black",
        width=200,
    )


def centered(content: Any, **kwargs: Any) -> Align:
    return Align.center(simple_panel(content, **kwargs), vertical="middle")


def new_tree(values: List[str] = [], **kwargs) -> Tree:
    default: JSONDict = dict(guide_style="black")
    tree = Tree(kwargs.pop("title", None) or "", **{**default, **kwargs})
    for val in values:
        tree.add(val)
    return tree


def colored_split(content: str) -> Align:
    parts = content.split(", ")
    return centered(Text.from_markup(" ~ ".join(map(format_with_color, sorted(parts)))))


def tstamp2timedate(timestamp: Optional[str], fmt: str = "%F %H:%M") -> str:
    return datetime.fromtimestamp(int(float(timestamp or 0))).strftime(fmt)
