import itertools as it
import random
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, MutableMapping, Optional, Tuple, TypeVar

from rich import box
from rich.align import Align
from rich.console import Console, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Column, Table
from rich.text import Text
from rich.tree import Tree

Renderable = TypeVar("Renderable")


def fmtdiff(change: str, before: str, after: str) -> str:
    retval = before
    if change == "insert":
        retval = wrap(after, "b green")
    elif change == "delete":
        retval = wrap(before, "b strike red")
    elif change == "replace":
        retval = wrap(before, "b strike red") + wrap(after, "b green")
    return retval


def make_difftext(before: str, after: str) -> str:
    def preparse(value: str) -> str:
        return value.strip().replace("[]", "~")

    before = preparse(before)
    after = preparse(after)

    matcher = SequenceMatcher(lambda x: x in " ", a=before, b=after)
    diff = ""
    for code, a1, a2, b1, b2 in matcher.get_opcodes():
        diff = diff + (fmtdiff(code, before[a1:a2], after[b1:b2]) or "")
    return diff


def time2human(timestamp: Optional[int], acc: int = 1) -> str:
    if not timestamp:
        return "-"
    diff = datetime.now() - datetime.fromtimestamp(timestamp)
    opts: List[Tuple[int, str]] = [
        (diff.days, "d"),
        (diff.seconds // 3600, "h"),
        (diff.seconds % 3600 // 60, "min"),
        (diff.seconds % 60, "s"),
    ]
    parts = it.starmap("[b cyan]{}[/b cyan]{}".format, filter(lambda x: x[0], opts))
    return " ".join(it.islice(parts, acc)) + " ago"


def make_console(**kwargs: Any) -> Console:
    default = dict(force_terminal=True, force_interactive=True)
    return Console(**{**default, **kwargs})


def wrap(text: str, tag: str) -> str:
    return f"[{tag}]{text}[/{tag}]"


def new_table(*args: Any, **kwargs: Any) -> Table:
    default = dict(
        border_style="black",
        show_edge=False,
        show_header=False,
        highlight=True,
        row_styles=["white"],
        expand=False,
        style="light_steel_blue1",
    )
    headers = []
    if len(args):
        headers = list(map(lambda x: Column(str(x), justify="left") or "", args))
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
    rand1 = random.randint(150, 255)
    rand2 = random.randint(150, 255)
    rand3 = random.randint(150, 255)
    return "#{:0>6X}".format(rand1 * rand2 * rand3)
    # return "#{:0>6X}".format(random.randint(3000, 2 ** 24))


def format_with_color(name: str) -> str:
    if re.match(r"20[12][0-9]-[0-9][0-9](-[0-9][0-9])?", name):
        return " ".join(
            map(
                lambda x: wrap(x[0], f"b {x[1]}"),
                map(lambda x: [x, predictably_random_color(x)], name.split("-")),
            )
        )
    else:
        return wrap(name, f"b i {predictably_random_color(name)}")


def simple_panel(content: RenderableType, **kwargs: Any) -> Panel:
    align_content = None
    if kwargs.get("align", "") == "center":
        align_content = Align.center(content)
    default = dict(title_align="left", subtitle_align="left", box=box.SIMPLE, expand=True)
    args: MutableMapping = default.copy()
    args.update(kwargs)
    return Panel(align_content or content, **args)


def border_panel(content: RenderableType, **kwargs: Any) -> Panel:
    return simple_panel(content, **{**dict(box=box.ROUNDED), **kwargs})


def md_panel(content: str, **kwargs: Any) -> Panel:
    return border_panel(Markdown(content), **kwargs)


def comment_panel(comment: Dict[str, str], **kwargs: Any) -> Panel:
    state = comment.get("state") or ""
    author = format_with_color(comment["author"])
    time = wrap(comment.get("createdAt") or "", "d")
    title = (state + " " if state else "") + author
    return md_panel(
        re.sub(r"[\[\]\\]", "", comment["body"]),
        padding=1,
        title=title,
        subtitle=time,
        **kwargs,
    )


def syntax_panel(content: str, lexer: str, **kwargs: Any) -> Panel:
    default = dict(theme="paraiso-dark", background_color="black", word_wrap=True)
    return Panel(Syntax(content, lexer, **default), style="on black", width=200)


def centered(content: Any, **kwargs: Any) -> Align:
    return Align.center(simple_panel(content, **kwargs), vertical="middle")


def new_tree(values: List[str] = [], **kwargs) -> Tree:
    default = dict(guide_style="black")
    tree = Tree(kwargs.pop("title", None) or "", **{**default, **kwargs})
    for val in values:
        tree.add(val)
    return tree


def colored_split(content: str) -> Align:
    parts = content.split(", ")
    return centered(Text.from_markup(" ~ ".join(map(format_with_color, sorted(parts)))))


def tstamp2timedate(timestamp: Optional[str], fmt: str = "%F %H:%M") -> str:
    return datetime.fromtimestamp(int(float(timestamp or 0))).strftime(fmt)
