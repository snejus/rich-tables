from __future__ import annotations

from dataclasses import asdict, dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Any, Callable

from typing_extensions import Literal, TypedDict

from .fields import FIELDS_MAP, get_val
from .generic import flexitable
from .utils import (
    border_panel,
    format_with_color,
    human_dt,
    new_tree,
    predictably_random_color,
    wrap,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from rich.panel import Panel
    from rich.tree import Tree

SKIP_HEADERS = {
    "priority",
    "recur",
    "uuid",
    "reviewed",
    "modified",
    "annotations",
    "depends",
    "description",
}
INITIAL_HEADERS = ["id", "urgency", "created", "modified", "tree"]

COLOR_BY_STATUS = {
    "completed": "b s black on green",
    "deleted": "s red",
    "pending": "white",
    "started": "b green",
    "recurring": "i magenta",
}

JSONDict = dict[str, Any]


def keep_keys(keys: Iterable[str], item: JSONDict) -> JSONDict:
    """Keep only the keys in `keys` from `item`."""
    return dict(zip(keys, map(item.get, keys)))


class Annotation(TypedDict):
    created: str
    description: str


@dataclass
class Task:
    annotations: list[Annotation]
    created: str
    description: str
    id: int
    modified: str
    status: Literal["completed", "deleted", "pending", "started", "recurring"]
    urgency: int
    uuid: str

    depends: list[str] = field(default_factory=list)
    due: str | None = None
    end: str | None = None
    priority: Literal["H", "M", "L"] | None = None
    project: str | None = None
    reviewed: str | None = None
    sched: str | None = None
    start: str | None = None
    tags: list[str] = field(default_factory=list)
    wait: str | None = None

    @property
    def desc(self) -> str:
        desc = self.description
        if self.start:
            self.status = "started"

        desc = wrap(desc, COLOR_BY_STATUS[self.status])
        if self.priority:
            desc = f"{get_val(self, 'priority')} {desc}"

        return desc

    def get_tree(self, get_desc: Callable[[str], str]) -> Tree:
        tree = new_tree(label=self.desc, guide_style="white")
        if self.annotations:
            tree.add(get_val(self, "annotations"))

        dep_uuids = self.depends
        if deps := list(filter(None, map(get_desc, dep_uuids))):
            tree.add(new_tree(deps, guide_style="b red", hide_root=True))

        return tree

    def get_row(
        self, extract_data: Callable[[JSONDict], JSONDict], *_: Any, **kwargs: Any
    ) -> JSONDict:
        data = extract_data(asdict(self))
        data["tree"] = self.get_tree(**kwargs)

        return data


def get_headers(task_headers: Iterable[str]) -> list[str]:
    """Return the list of headers that will be used in the table."""
    ordered_keys = dict.fromkeys([*INITIAL_HEADERS, *sorted(task_headers)]).keys()
    return [*[k for k in ordered_keys if k not in SKIP_HEADERS], "tree"]


fields_map: JSONDict = {
    "id": str,
    "uuid": str,
    "urgency": lambda x: str(round(float(x), 1)),
    "description": lambda x: x,
    "due": human_dt,
    "end": human_dt,
    "sched": human_dt,
    "tags": format_with_color,
    "project": format_with_color,
    "modified": human_dt,
    "created": human_dt,
    "start": human_dt,
    "priority": lambda x: "[b]([red]![/])[/]" if x == "H" else "",
    "annotations": lambda ann: new_tree(
        (f"[b]{human_dt(a['created'])}[/]: [i]{a['description']}[/]" for a in ann),
        "Annotations",
    )
    if ann
    else None,
}


def get_table(
    tasks_data_by_group: dict[str, list[JSONDict]], **__: Any
) -> Iterator[Panel]:
    """Yield a table for each tasks group."""
    FIELDS_MAP.update(fields_map)
    headers = get_headers(next(t for g in tasks_data_by_group.values() for t in g))
    keep_headers = partial(keep_keys, headers)

    tasks_by_group = {
        g: [Task(**t) for t in tasks_data]
        for g, tasks_data in tasks_data_by_group.items()
    }
    desc_by_uuid = {t.uuid: t.desc for g in tasks_by_group.values() for t in g}
    for group, tasks in tasks_by_group.items():
        yield border_panel(
            flexitable(
                [t.get_row(keep_headers, get_desc=desc_by_uuid.get) for t in tasks]
            ),
            title=wrap(group, "b"),
            style=predictably_random_color(group),
        )
