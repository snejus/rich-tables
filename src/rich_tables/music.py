import itertools as it
import operator as op
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Collection, Dict, Iterable, List, Optional, Tuple

from ordered_set import OrderedSet
from rich import box, print
from rich.console import Group
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

TRACK_FIELDS = OrderedSet(
    ["track", "length", "artist", "title", "bpm", "last_played", "stats"]
)
ALBUM_IGNORE = TRACK_FIELDS.union(
    {
        "length",
        "comments",
        "album_color",
        "albumartist_color",
        "album",
        "albumartist",
        "albumtypes",
        "album_title",
        "genre",
        "plays",
        "skips",
        "tracktotal",
    }
)

FIELDS_MAP: Dict[str, Callable] = defaultdict(
    lambda: str,
    albumtype=lambda x: " ".join(map(format_with_color, x.split("; "))),
    last_played=time2human,
    added=time2human,
    mtime=time2human,
    bpm=lambda x: wrap(x, "green" if x < 135 else "red" if x > 165 else "yellow"),
    style=format_with_color,
    genre=lambda x: "  ".join(map(lambda y: f" {format_with_color(y)} ", x.split(", "))),
    stats=lambda x: "[green]{:>4}[/green] [red]{:<4} [/red]".format(
        f"{x[0]}🞂" if x[0] else "", f"🞩 {x[1]}" if x[1] else ""
    ),
    length=lambda x: datetime.fromtimestamp(x).strftime("%M:%S"),
)

DISPLAY_HEADER: Dict[str, str] = {
    "track": "#",
    "bpm": "🚀",
    "stats": "",
    "last_played": "🎶 ⏰",
    "mtime": "updated",
    "data_source": "source",
}


def is_single(track: JSONDict) -> bool:
    album, albumtype = track.get("album"), track.get("albumtype")
    return not album or not albumtype or albumtype == "single"


def get_header(key: str) -> str:
    return wrap(DISPLAY_HEADER.get(key, key), "b")


def get_val(track: JSONDict, field: str) -> str:
    return FIELDS_MAP[field](track[field]) if track.get(field) else ""


def get_vals(fields: Collection[str], tracks: Iterable[JSONDict]) -> Iterable[Any]:
    _, most_recent = max(map(lambda x: (x.get("last_played"), x), tracks))
    most_recent["artist"] = wrap(most_recent["artist"], "b i")
    most_recent["title"] = wrap(most_recent["title"], "b i")
    for track in tracks:
        track["stats"] = track.pop("plays"), track.pop("skips")
        if is_single(track):
            track.pop("album")

    return map(lambda t: map(lambda f: get_val(t, f), fields), tracks)


def tracks_table(tracks: List[JSONDict], **kwargs) -> Table:
    fields = TRACK_FIELDS.copy()
    if len(tracks) > 1 and len(set(map(lambda x: x.get("artist"), tracks))) == 1:
        fields.remove("artist")

    return new_table(
        *map(get_header, fields),
        expand=True,
        rows=get_vals(fields, sorted(tracks, key=lambda x: x["track"])),
        collapse_padding=True,
        **kwargs,
    )


def album_stats(tracks: List[JSONDict]) -> JSONDict:
    def agg(field: str) -> Iterable:
        return map(lambda x: x.get(field) or 0, tracks)

    stats = dict(
        bpm=round(sum(agg("bpm")) / len(tracks), 1),
        rating=round(sum(agg("rating")) / len(tracks), 2),
        plays=sum(agg("plays")),
        skips=sum(agg("skips")),
        mtime=max(agg("mtime")),
        last_played=max(agg("last_played")),
    )
    stats["stats"] = stats["plays"] or "", stats["skips"] or ""
    return stats


def album_title(album: JSONDict) -> str:
    name = re.sub(r".* - ", "", album["album"])
    artist = album.get("albumartist") or album.get("artist")
    return wrap(f"  {name} by {artist}  ", "i white on grey3")


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
    return album


def album_info(tracks: List[JSONDict]) -> JSONDict:
    first = tracks[0]
    fields = set(first.keys()) - set(TRACK_FIELDS)
    get = first.get

    album: JSONDict = {
        **dict(zip(fields, op.itemgetter(*fields)(first))),
        **album_stats(tracks),
        "albumtype": get("albumtypes") or get("albumtype"),
    }
    album.update(**album_colors(album))
    album.update(album_title=album_title(album))
    return album


def should_display(keyval: Tuple[str, Any]) -> bool:
    return keyval[1] and keyval[0] not in ALBUM_IGNORE


def album_comment_panel(comment: str) -> Panel:
    return simple_panel(comment, box=box.SIMPLE, style="grey54")


def tracklist_summary(album: JSONDict) -> List[str]:
    stats_fields = "bpm", "last_played", "stats"
    tracktotal = str(album.get("tracktotal") or "")
    return [tracktotal, "", "", "", *op.itemgetter(*stats_fields)(album)]


def album_info_table(album: JSONDict) -> Table:
    items = filter(should_display, sorted(album.items()))
    return new_table(rows=map(lambda x: (get_header(x[0]), x[1]), items))


def map_album_fields(album: JSONDict) -> JSONDict:
    for field, val in filter(op.truth, sorted(album.items())):
        album[field] = get_val(album, field)
    return album


def detailed_album_panel(tracks: List[JSONDict]) -> Panel:
    album = album_info(tracks)
    album = map_album_fields(album)
    tracks_list = tracks_table(tracks, border_style=album["album_color"])
    row = tracklist_summary(album)
    tracks_list.add_row(*row, style="white on grey11")

    comments = album.get("comments")
    return border_panel(
        Group(
            album["album_title"] + 10 * " " + album["genre"],
            album_comment_panel(comments) if comments else "",
            new_table(rows=[map(simple_panel, [album_info_table(album), tracks_list])]),
        ),
        box=box.HEAVY,
        style=album["albumartist_color"],
    )


def make_albums_table(all_tracks: List[JSONDict]) -> None:
    singles = list(filter(is_single, all_tracks))
    not_singles = list(it.filterfalse(is_single, all_tracks))
    for album_name, tracks in it.groupby(not_singles, lambda x: x.get("album") or ""):
        print(detailed_album_panel(list(tracks)))

    if singles:
        table = tracks_table(singles, border_style="white")
        print(border_panel(table, title=wrap("  Singles  ", "b on grey3")))


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
