import itertools as it
import operator as op
import re
from collections import defaultdict
from datetime import datetime
from functools import partial
from typing import Any, Callable, Dict, Iterable, List, Tuple

from ordered_set import OrderedSet
from pycountry import countries
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
        "album_color",
        "albumartist_color",
        "album",
        "album_title",
        "comments",
        "genre",
        "tracktotal",
        "plays",
        "skips",
        "albumartist",
        "albumtypes",
    }
)


def get_country(code: str) -> str:
    try:
        return countries.lookup(code).name
    except LookupError:
        return "Worldwide"


FIELDS_MAP: Dict[str, Callable] = defaultdict(
    lambda: str,
    albumtype=lambda x: " ".join(map(format_with_color, x.split("; "))),
    label=format_with_color,
    last_played=time2human,
    added=lambda x: datetime.fromtimestamp(x).strftime("%F %H:%M"),
    mtime=lambda x: re.sub(r"\] *", "]", time2human(x)),
    bpm=lambda x: wrap(x, "green" if x < 135 else "red" if x > 165 else "yellow"),
    style=format_with_color,
    genre=lambda x: "  ".join(map(lambda y: f" {format_with_color(y)} ", x.split(", "))),
    stats=lambda x: "[green]{:>4}[/green] [red]{:<4}[/red]".format(
        f"{x[0]}🞂" if x[0] else "", f"🞩 {x[1]}" if x[1] else ""
    ),
    length=lambda x: datetime.fromtimestamp(x).strftime("%M:%S"),
    tracktotal="/[b cyan]{}[/b cyan]".format,
    country=get_country,
    data_source=format_with_color,
)

DISPLAY_HEADER: Dict[str, str] = {
    "track": "#",
    "bpm": "🚀",
    "stats": "",
    "last_played": "  🎶 ⏰",
    "mtime": "updated",
    "data_source": "source",
}

new_table = partial(new_table, collapse_padding=True, expand=True)


def get_header(key: str) -> str:
    return DISPLAY_HEADER.get(key, key)


def get_val(track: JSONDict, field: str) -> str:
    return FIELDS_MAP[field](track[field]) if track.get(field) else ""


def get_vals(fields: List[str], tracks: Iterable[JSONDict]) -> Iterable[Iterable[str]]:
    for track in tracks:
        track["stats"] = track.pop("plays", ""), track.pop("skips", "")

    return map(lambda t: list(map(lambda f: get_val(t, f), fields)), tracks)


def album_stats(tracks: List[JSONDict]) -> JSONDict:
    def agg(field: str) -> Iterable[int]:
        return map(lambda x: x.get(field) or 0, tracks)

    stats: JSONDict = dict(
        bpm=round(sum(agg("bpm")) / len(tracks)),
        rating=round(sum(agg("rating")) / len(tracks), 2),
        plays=sum(agg("plays")),
        skips=sum(agg("skips")),
        mtime=max(agg("mtime")),
        last_played=max(agg("last_played")),
    )
    stats["stats"] = str(stats.get("plays") or ""), str(stats.get("skips") or "")
    return stats


def add_colors(album: JSONDict) -> None:
    for field in "album", "albumartist":
        color = predictably_random_color(album[field])
        album[f"{field}_color"] = color
        album[field] = wrap(album[field], f"b i {color}")


def album_title(album: JSONDict) -> str:
    name = re.sub(r"\].* - ", "]", album["album"])
    artist = album.get("albumartist") or album.get("artist")
    genre = album.get("genre") or ""
    return wrap(f"  {name} by {artist}  ", "i white on grey3") + 10 * " " + genre


def album_info(tracks: List[JSONDict]) -> JSONDict:
    first = tracks[0]
    fields = set(first.keys()) - TRACK_FIELDS
    get = first.get

    album = dict(zip(fields, op.itemgetter(*fields)(first)))
    album.update(**album_stats(tracks), albumtype=get("albumtypes") or get("albumtype"))
    add_colors(album)
    for field, val in filter(op.truth, sorted(album.items())):
        album[field] = get_val(album, field)
    album["album_title"] = album_title(album)
    return album


def album_info_table(album: JSONDict) -> Table:
    def should_display(keyval: Tuple[str, Any]) -> bool:
        return keyval[1] and keyval[0] not in ALBUM_IGNORE

    items = filter(should_display, sorted(album.items()))
    table = new_table(rows=map(lambda x: (get_header(x[0]), x[1]), items))
    table.columns[0].style = "b " + album["album_color"]
    return table


def tracks_table(tracks, color="white", fields=TRACK_FIELDS, sort=True):
    # type: (List[JSONDict], str, List[str], bool) -> Table
    if sort:
        tracks = sorted(tracks, key=lambda x: x["track"])
    return new_table(
        *map(get_header, fields), rows=get_vals(fields, tracks), border_style=color
    )


def tracklist_summary(album: JSONDict, fields: List[str]) -> List[str]:
    fields[0] = "tracktotal"
    mapping = dict(zip(fields, map(lambda f: album.get(f, ""), fields)))
    return list(op.itemgetter(*fields)(mapping))


def track_fields(tracks: List[JSONDict]) -> List[str]:
    """Ignore the artist field if there is only one found."""
    if len(tracks) > 1 and len(set(map(lambda x: x.get("artist"), tracks))) == 1:
        return list(TRACK_FIELDS - {"artist"})
    return list(TRACK_FIELDS)


def detailed_album_panel(tracks: List[JSONDict]) -> Panel:
    album = album_info(tracks)

    t_fields = track_fields(tracks)
    tracklist = tracks_table(tracks, album["album_color"], t_fields)

    _, track = max(map(op.itemgetter("last_played", "track"), tracks))
    if track > 0:
        row_no = tracklist.columns[0]._cells.index(str(track))
        tracklist.rows[row_no].style = "b white on #000000"
        tracklist.add_row(*tracklist_summary(album, t_fields), style="d white on grey11")

    comments = album.get("comments")
    return border_panel(
        Group(
            album["album_title"],
            simple_panel(comments, style="grey54") if comments else "",
            new_table(rows=[map(simple_panel, [album_info_table(album), tracklist])]),
        ),
        box=box.DOUBLE_EDGE,
        style=album["albumartist_color"],
    )


def make_albums_table(all_tracks: List[JSONDict]) -> None:
    def is_single(track: JSONDict) -> bool:
        album, albumtype = track.get("album"), track.get("albumtype")
        return not album or not albumtype or albumtype == "single"

    for track in filter(is_single, all_tracks):
        track["album"] = "singles"
        track["albumartist"] = track["label"]
    for album_name, tracks in it.groupby(all_tracks, lambda x: x.get("album") or ""):
        print(detailed_album_panel(list(tracks)))


def make_tracks_table(all_tracks: List[JSONDict]) -> None:
    fields = OrderedSet([*all_tracks[0].keys()] + ["stats"]) - {"albumtypes"}

    for track in all_tracks:
        track["albumtype"] = track.pop("albumtypes", None) or track.pop("albumtype", None)
    print(tracks_table(all_tracks, "blue", fields, sort=False))
