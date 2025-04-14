"""Formatted text difference generation between Python objects.

This module provides utilities for creating rich, highlighted text
representations of differences between various Python data types.
It supports diffing strings, lists, dictionaries, and other objects
with specialized formatting for each type.
"""

import json
import re
from difflib import SequenceMatcher
from functools import partial
from itertools import starmap, zip_longest
from typing import Any, Hashable, Literal

from multimethod import multimethod

from .utils import BOLD_GREEN, BOLD_RED, HashableDict, HashableList, wrap

MIN_EQUAL_LENGTH = 5

underscore_space = partial(re.compile(r"(^ +)|( +$)").sub, r"[u]\g<0>[/]")
mark_newline = partial(
    re.compile(r"(^\n+)|(\n+$)").sub, lambda m: m[0].replace("\n", "⮠\n")
)


def format_new(string: str) -> str:
    """Format added text in bold green with visible whitespace markers."""
    return wrap(mark_newline(underscore_space(string)), BOLD_GREEN)


def format_old(string: str) -> str:
    """Format deleted text in bold red with strikethrough."""
    return wrap(mark_newline(string), f"s {BOLD_RED}")


def fmtdiff(change: str, before: str, after: str) -> str:
    """Format a single diff chunk based on its operation type.

    Handles insert, delete, replace and equal operations with appropriate styling.
    """
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


def make_difftext(before: str, after: str) -> str:
    """Generate formatted text showing differences between two strings.

    Creates a unified, styled representation merging small equal sections
    into larger replace operations for improved readability.
    """
    matcher = SequenceMatcher(lambda x: x in "", autojunk=False, a=before, b=after)
    ops = matcher.get_opcodes()
    # Identify small "equal" sections that should be merged with surrounding changes
    # This creates more cohesive diff chunks by avoiding tiny unchanged fragments
    to_remove_ids = [
        i
        for i, (op, a, b, c, d) in enumerate(ops)
        if 0 < i < len(ops) - 1  # Skip first and last operations
        and op == "equal"  # Only process unchanged sections
        and b - a < MIN_EQUAL_LENGTH  # Section must be smaller than threshold
        and before[a:b].strip()  # Section must not be just whitespace in 'before'
        and after[c:d].strip()  # Section must not be just whitespace in 'after'
    ]
    # Merge small equal sections with surrounding operations
    # `to_remove_ids` are processed in reverse order to avoid index shifting
    # problems when deleting elements from the list. This pattern ensures that
    # as we remove items, we don't affect the indices of items we still need to
    # process.
    for i in reversed(to_remove_ids):
        # Get the operations before and after the small equal section
        a, b = ops[i - 1], ops[i + 1]
        # All small equal sections are converted to 'replace' operations
        action: Literal["replace"] = "replace"

        # Create a new merged operation that spans from the start of the previous
        # operation to the end of the next operation
        ops[i] = (action, a[1], b[2], a[3], b[4])

        # Remove the operations that are now merged into the new operation
        del ops[i + 1]
        del ops[i - 1]

    return "".join(
        fmtdiff(code, before[a1:a2], after[b1:b2]) or "" for code, a1, a2, b1, b2 in ops
    )


@multimethod
def to_hashable(value: Any) -> Any:
    """Convert potentially unhashable objects to hashable equivalents.

    Base implementation for primitive hashable types.
    Extended via multimethod for lists and dictionaries.
    """
    return value


@to_hashable.register
def _(value: list[Any]) -> Hashable:
    return HashableList([to_hashable(v) for v in value])


@to_hashable.register
def _(value: dict[str, Any]) -> Hashable:
    return HashableDict({k: to_hashable(v) for k, v in value.items()})


def diff_serialize(value: Any) -> str:
    """Convert a value to its string representation for diffing."""
    if value is None:
        return ""
    return '""' if value == "" else str(value)


@multimethod
def diff(before: str, after: str) -> str:
    """Generate a formatted diff between two objects.

    Base implementation for strings. Extended via multimethod
    for lists, dictionaries and generic objects.
    """
    return make_difftext(before, after)


@diff.register
def _(before: Any, after: Any) -> Any:
    return diff(diff_serialize(before), diff_serialize(after))


@diff.register
def _(before: HashableList[Any], after: HashableList[Any]) -> Any:
    return list(starmap(diff, zip_longest(before, after)))


@diff.register
def _(before: HashableDict, after: HashableDict) -> dict[str, str]:
    data = {}
    keys = dict.fromkeys((*before, *after))
    for key in keys:
        if key not in before:
            data[wrap(key, BOLD_GREEN)] = wrap(diff_serialize(after[key]), BOLD_GREEN)
        elif key not in after:
            data[wrap(key, BOLD_RED)] = wrap(diff_serialize(before[key]), BOLD_RED)
        else:
            data[key] = diff(before[key], after[key])

    return data


def pretty_diff(before: Any, after: Any) -> str:
    """Generate a Rich Text object showing differences between any two Python objects.

    This is the main entry point for the diffing functionality.
    Handles all supported types through the multimethod dispatch system.
    """
    result = diff(to_hashable(before), to_hashable(after))
    if isinstance(result, str):
        return result

    return (
        json.dumps(result, indent=2, ensure_ascii=False)
        .replace("'", "")
        .replace('"', "")
        .replace("\\", "")
        .replace("()", "[]")
    )
