import re
from collections import UserDict, UserList
from difflib import SequenceMatcher
from itertools import starmap, zip_longest
from pprint import pformat
from string import printable, punctuation
from typing import Any, Hashable, Literal

from multimethod import multimethod
from rich.text import Text

from .utils import BOLD_GREEN, BOLD_RED, wrap

CONSECUTIVE_SPACE = re.compile(r"(?:^ +)|(?: +$)")


def format_space(string: str) -> str:
    return CONSECUTIVE_SPACE.sub(r"[u]\g<0>[/]", string)


def format_new(string: str) -> str:
    string = re.sub(r"^\n+", lambda m: m[0].replace("\n", "⮠\n"), string)
    return wrap(format_space(string), BOLD_GREEN)


def format_old(string: str) -> str:
    string = re.sub(r"^\n|\n$", lambda m: m[0].replace("\n", "⮠ "), string)
    return wrap(string, f"s {BOLD_RED}")


def fmtdiff(change: str, before: str, after: str) -> str:
    if change == "insert":
        return format_new(after)
    if change == "delete":
        return format_old(before)
    if change == "replace":
        return "".join(
            (format_old(a) + format_new(b)) if a != b else a
            for a, b in zip(before.partition("\n"), after.rpartition("\n"))
        )

    return wrap(before, "dim")


def make_difftext(
    before: str,
    after: str,
    junk: str = "".join(sorted((set(punctuation) - {"_", "-", ":"}) | {"\n"})),
) -> str:
    matcher = SequenceMatcher(lambda x: x in "", autojunk=False, a=before, b=after)
    ops = matcher.get_opcodes()
    to_remove_ids = [
        i
        for i, (op, a, b, c, d) in enumerate(ops)
        if 0 < i < len(ops) - 1
        and op == "equal"
        and b - a < 5
        and before[a:b].strip()
        and after[c:d].strip()
    ]
    for i in reversed(to_remove_ids):
        a, b = ops[i - 1], ops[i + 1]
        action: Literal["replace"] = "replace"

        ops[i] = (action, a[1], b[2], a[3], b[4])

        del ops[i + 1]
        del ops[i - 1]

    return "".join(
        fmtdiff(code, before[a1:a2], after[b1:b2]) or "" for code, a1, a2, b1, b2 in ops
    )


class HashableList(UserList[Any]):
    def __hash__(self) -> int:
        return hash(tuple(self.data))


class HashableDict(UserDict[str, Any]):
    def __hash__(self) -> int:
        return hash(tuple(self.data.items()))


@multimethod
def to_hashable(value: Any) -> Any:
    return value


@to_hashable.register
def _(value: list[Any]) -> Hashable:
    return HashableList(map(to_hashable, value))


@to_hashable.register
def _(value: dict[str, Any]) -> Hashable:
    return HashableDict({k: to_hashable(v) for k, v in value.items()})


def diff_serialize(value: Any) -> str:
    if value is None:
        return ""
    return '""' if value == "" else str(value)


@multimethod
def diff(before: str, after: str) -> str:
    return make_difftext(before, after, printable)


@diff.register
def _(before: Any, after: Any) -> Any:
    return diff(diff_serialize(before), diff_serialize(after))


@diff.register
def _(before: list[Any], after: list[Any]) -> Any:
    return list(starmap(diff, zip_longest(before, after)))


@diff.register
def _(before: list[str], after: list[str]) -> list[str]:
    before_set, after_set = dict.fromkeys(before), dict.fromkeys(after)
    common = [k for k in before_set if k in after_set]
    return [
        *list(starmap(diff, zip(common, common))),
        *[
            diff(before or "", after or "")
            for before, after in zip_longest(
                [k for k in before_set if k not in common],
                [k for k in after_set if k not in common],
            )
        ],
    ]


@diff.register
def _(before: dict[str, Any], after: dict[str, Any]) -> dict[str, str]:
    data = {}
    keys = sorted(before.keys() | after.keys())
    for key in keys:
        if key not in before:
            data[wrap(key, BOLD_GREEN)] = wrap(diff_serialize(after[key]), BOLD_GREEN)
        elif key not in after:
            data[wrap(key, BOLD_RED)] = wrap(diff_serialize(before[key]), BOLD_RED)
        else:
            data[key] = diff(before[key], after[key])

    return data


def pretty_diff(before: Any, after: Any, **kwargs: Any) -> Text:
    result = diff(to_hashable(before), to_hashable(after))
    if not isinstance(result, str):
        result = (
            pformat(result, indent=2, width=300, sort_dicts=False)
            .replace("'", "")
            .replace('"', "")
            .replace("\\\\", "\\")
        )

    return Text.from_markup(result, **kwargs)
