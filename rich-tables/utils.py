import random
import re
import time
from datetime import datetime
from functools import reduce
from typing import Any, Dict, List, MutableMapping, Optional, TypeVar

from dateutil.relativedelta import relativedelta
from rich import box
from rich.align import Align
from rich.console import Console, ConsoleRenderable
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Column, Table
from rich.text import Text
from rich.tree import Tree

Renderable = TypeVar("Renderable")


def timeint2human(timestamp: int) -> str:
    timediff = relativedelta(seconds=timestamp)
    return reduce(
        lambda x, y: x + "{} {} ".format(int(y[1]), y[0])
        if y[1] or len(x) and y[0] != "leapdays"
        else x,
        list(vars(timediff).items())[:7],
        "",
    )


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
    )
    headers = []
    if len(args):
        headers = list(map(lambda x: Column(str(x), justify="center") or "", args))
        default["header_style"] = "bold misty_rose1"
        default["box"] = box.SIMPLE_HEAVY
        default["show_header"] = True
    table = Table(*headers, **{**default, **kwargs})
    if "rows" in kwargs:
        for row in kwargs["rows"]:
            table.add_row(*row)
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


def simple_panel(content: ConsoleRenderable, **kwargs: Any) -> Panel:
    align_content = None
    if kwargs.get("align", "") == "center":
        align_content = Align.center(content)
    default = dict(title_align="left", subtitle_align="left", box=box.SIMPLE, expand=True)
    args: MutableMapping = default.copy()
    args.update(kwargs)
    return Panel(align_content or content, **args)


def border_panel(content: Renderable, **kwargs: Any) -> Panel:
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


FIRST_PART = re.compile(r"^([0-9]+ [^ ]+).*")


def time2human(value: int) -> str:
    return FIRST_PART.sub(r"\1", timeint2human(int(time.time() - value))) + " ago"


def tstamp2timedate(timestamp: Optional[str], fmt: str = "%F %H:%M") -> str:
    return datetime.fromtimestamp(int(float(timestamp or 0))).strftime(fmt)
