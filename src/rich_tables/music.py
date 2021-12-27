import itertools as it
import operator as op
from collections import defaultdict
from functools import partial
from typing import Any, Callable, Collection, Dict, Iterable, List, Tuple

from ordered_set import OrderedSet
from rich import box, print
from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .utils import (
    border_panel,
    format_with_color,
    new_table,
    predictably_random_color,
    simple_panel,
    time2human,
    wrap,
)

JSONDict = Dict[str, Any]

TRACK_DISPLAY_FIELDS = ["track", "artist", "title", "bpm", "stats", "last_played"]
ALBUM_KEEP = {"last_played", "bpm", "stats"}
ALBUM_IGNORE = {
    "length",
    "comments",
    "album_color",
    "albumartist_color",
    "album",
    "albumartist",
    "albumtypes",
    "album_title",
    "plays",
    "skips",
}

_first_date_part = partial(time2human, acc=1)
FIELDS_MAP: Dict[str, Callable] = defaultdict(
    lambda: str,
    albumtype=lambda x: " ".join(map(format_with_color, x.split("; "))),
    last_played=_first_date_part,
    added=_first_date_part,
    mtime=_first_date_part,
    bpm=lambda x: wrap(x, "green" if x < 135 else "red" if x > 165 else "yellow"),
    style=format_with_color,
    genre=lambda x: "\n".join(map(format_with_color, x.split(", "))),
    stats=lambda x: "[b on grey3][green] {:>2}[/green] [red]{:<2} [/red][/b on grey3]".format(
        *map(lambda f: f or "", x)
    ),
)
DISPLAY_HEADER: Dict[str, str] = {
    "track": "#",
    "bpm": "🚀",
    "stats": FIELDS_MAP["stats"](("✔", "🞬 ")),
    "last_played": "🎶 ⏰",
    "mtime": "modified",
}


def is_single(track: JSONDict) -> bool:
    album, albumtype = track.get("album"), track.get("albumtype")
    return not album or not albumtype or albumtype == "single"


def get_header(key: str) -> str:
    return wrap(DISPLAY_HEADER.get(key, key), "b")


def get_val(track: JSONDict, field: str) -> str:
    return FIELDS_MAP[field](track[field]) if track.get(field) else ""


def get_vals(fields: Collection[str], tracks: Iterable[JSONDict]) -> Iterable[Any]:
    for track in tracks:
        track["stats"] = track.pop("plays"), track.pop("skips")
        if is_single(track):
            track.pop("album")

    return map(lambda t: map(lambda f: get_val(t, f), fields), tracks)


def tracks_table(tracks: List[JSONDict], **kwargs) -> Table:
    fields = TRACK_DISPLAY_FIELDS.copy()
    if len(tracks) > 1 and len(set(map(lambda x: x.get("artist"), tracks))) == 1:
        fields.remove("artist")

    return new_table(
        *map(lambda x: DISPLAY_HEADER.get(x, x), fields),
        box=box.SIMPLE,
        rows=get_vals(fields, tracks),
        collapse_padding=True,
        **kwargs,
    )


def album_stats(tracks: List[JSONDict]) -> JSONDict:
    def agg(field: str) -> Iterable:
        return map(lambda x: x.get(field) or 0, tracks)

    return dict(
        bpm=round(sum(agg("bpm")) / len(tracks), 1),
        rating=round(sum(agg("rating")) / len(tracks), 2),
        stats=(sum(agg("plays")) or "", sum(agg("skips")) or ""),
        mtime=max(agg("mtime")),
        last_played=max(agg("last_played")),
    )


def album_title(title: str) -> str:
    return wrap(f"  {title}  ", "i white on grey3")


def album_colors(album: JSONDict) -> JSONDict:
    def _add_color(name: str) -> str:
        color = album[f"{name}_color"]
        return wrap(album[name], f"b i {color}")

    album.update(
        album_color=predictably_random_color(album["album"] or ""),
        albumartist_color=predictably_random_color(album["albumartist"] or ""),
    )
    album["album"] = _add_color("album")
    album["albumartist"] = _add_color("albumartist")
    title = album["album"]
    if " - " not in title:
        title += " by " + album["albumartist"]
    album["album_title"] = album_title(title)
    return album


def album_info(tracks: List[JSONDict]) -> JSONDict:
    first = tracks[0]
    fields = set(first.keys()) - set(TRACK_DISPLAY_FIELDS)
    get = first.get

    album: JSONDict = {
        **dict(zip(fields, op.itemgetter(*fields)(first))),
        **album_stats(tracks),
        "albumtype": get("albumtypes") or get("albumtype"),
    }
    album.update(**album_colors(album))

    return album


def album_info_panel(album: JSONDict) -> Panel:
    def should_display(keyval: Tuple[str, Any]) -> bool:
        return keyval[1] and (keyval[0] in ALBUM_KEEP or keyval[0] not in ALBUM_IGNORE)

    fields = filter(should_display, sorted(album.items()))
    rows = it.starmap(lambda k, v: (get_header(k), get_val(album, k)), fields)
    return simple_panel(new_table(rows=rows))


def album_comment_panel(comment: str) -> Panel:
    return border_panel(Markdown(comment), box=box.HORIZONTALS, style="grey54")


def detailed_album_panel(tracks: List[JSONDict]) -> Panel:
    album = album_info(tracks)
    comment = album.get("comments")
    return border_panel(
        new_table(
            rows=[
                [
                    album_info_panel(album),
                    Group(
                        album_comment_panel(comment) if comment else "",
                        tracks_table(tracks, border_style=album["album_color"]),
                    ),
                ]
            ],
            title=album["album_title"],
            title_justify="left",
        ),
        style=album["albumartist_color"],
    )


def make_albums_table(all_tracks: List[JSONDict]) -> None:

    singles = list(filter(is_single, all_tracks))
    not_singles = list(it.filterfalse(is_single, all_tracks))
    for album_name, tracks in it.groupby(not_singles, lambda x: x.get("album") or ""):
        print(detailed_album_panel(list(tracks)))

    if singles:
        table = tracks_table(singles, title_justify="left", border_style="white")
        print(border_panel(table, title=album_title(wrap("Singles", "b"))))


def make_music_table(all_tracks: List[JSONDict]) -> None:
    skip = {
        "rating",
        "released",
        "country",
        "albumtypes",
        "catalognum",
        "albumartist",
        "plays",
        "skips",
    }
    fields = OrderedSet(all_tracks[0].keys()).difference(skip)
    fields.update({"stats"})
    print(
        new_table(
            *map(get_header, fields),
            rows=get_vals(fields, all_tracks),
            collapse_padding=True,
            style="black",
        ),
    )
