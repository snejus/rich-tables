import itertools as it
import operator as op
from typing import Any, Dict, Iterable, List, Optional, Tuple

from rich import print
from rich.align import Align
from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from utils import (
    border_panel,
    colored_split,
    format_with_color,
    new_table,
    new_tree,
    predictably_random_color,
    simple_panel,
    time2human,
    wrap,
)

JSONDict = Dict[str, Any]
GroupsDict = Dict[str, List[JSONDict]]
bpm_rules = [
    (lambda bpm: bpm < 135, wrap("    🚀       ", "green")),
    (lambda bpm: bpm > 165, wrap("  🚀🚀🚀     ", "red")),
    (lambda bpm: True, wrap("   🚀🚀      ", "yellow")),
]


def format_bpm_plays_skips(data: JSONDict) -> JSONDict:
    # add bpm and play / skip counts at the end
    bpm: int = data.pop("bpm", 0)
    for check, fmt in bpm_rules:
        if check(bpm):
            data[fmt] = bpm
            break

    key = "  {} / {}      ".format(wrap("✔", "green"), wrap("🞬", "red"))
    data[key] = "{} / {}".format(data.pop("plays", "-"), data.pop("skips", "-"))
    return data


def map_track_fields(track: JSONDict) -> JSONDict:
    def pop(field: str, default: Any = "") -> Any:
        return track.pop(field, default) or default

    if "mtime" in track:
        mtime = pop("mtime", 0)
        track["modified"] = time2human(mtime) if mtime else "-"
    if "added" in track:
        added = pop("added", 0)
        track["added"] = time2human(added) if added else "-"
    if "last_played" in track:
        last = pop("last_played", 0)
        track["last_played_ts"] = last
        track["last_played"] = time2human(last) if last else "-"
    if "track" in track:
        track["#"] = pop("track")
    if "rating" in track:
        track["rating"] = round(track["rating"], 4)
    fields = ["albumdesc", "disctotal", "disc", "media", "bitdepth", "samplerate"]
    fields.extend(["day", "month", "year", "comments"])
    for field in fields:
        pop(field)

    return track


def map_album_fields(album: JSONDict, tracks: List[JSONDict]) -> JSONDict:
    def get(key: str, default: Any = "") -> Any:
        return album.get(key) or default

    def pop(field: str, default: Any = "") -> Any:
        return album.pop(field, default) or default

    def get_sum(field: str) -> int:
        return sum(map(lambda x: x.get(field) or 0, tracks))

    name = pop("album")
    if " - " not in name:
        name = " by ".join(map(format_with_color, [name, pop("albumartist")]))
    new_album = {"title": name}
    track_count = len(tracks)
    for field in sorted(album.keys()):
        value = get(field)
        if value is None:
            continue
        new_album[field] = value

        if field == "albumtype":
            style = f"bold black on {predictably_random_color(value)}"
            new_album[field] = wrap(f" {value} ", style)
        elif field == "style":
            new_album[field] = format_with_color(value)
        elif field == "genre":
            split_genre = value.split(", ")
            genre = "{:<4}{}".format(format_with_color(split_genre[0]), "")
            if len(split_genre) > 1:
                genre += "\n" + "\n".join(
                    map(
                        "{:<13}{}".format,
                        10 * [""],
                        map(format_with_color, split_genre[1:]),
                    )
                )
            new_album["genre"] = genre
        elif field == "last_played":
            new_album[field] = time2human(
                max(map(op.itemgetter("last_played_ts"), tracks))
            )
        elif field in {"bpm", "rating"}:
            new_album[field] = round(get_sum(field) / track_count, 2)
        elif field in {"plays", "skips"}:
            new_album[field] = str(get_sum(field))

    return format_bpm_plays_skips(new_album)


def make_release_table(data: JSONDict, ret: bool = False) -> Optional[Table]:
    rows = []
    for key, val in data.items():
        if key in {"genre", "style"}:
            content = colored_split(val)
            content.align = "left"
        elif key == "tracks":
            headers = list(val[0].keys())
            tracks_table = new_table(*headers)
            for track in val:
                tracks_table.add_row(*get_row(headers, track))
            content = Panel(tracks_table)
        else:
            content = str(val)
        rows.append([key, content])
    if ret:
        release_table = new_table()
        for row in rows:
            release_table.add_row(*row)
        return release_table
    # for row in rows:
    #     root.add_row(*row)
    # root.columns[0].style = "bold misty_rose1"
    # console.print(root)


def make_albums_table(albums: Iterable[JSONDict]) -> None:
    tracks: Iterable[JSONDict]
    singles: List[JSONDict] = []

    get_stats = op.itemgetter("bpm", "plays", "skips")
    h = "#", "artist", "title", "🚀", wrap("✔", "green"), wrap("🞬", "red"), "🎶 ⏰"

    def add_and_print(tracks: List[JSONDict], singles: bool = False) -> None:
        skip = {"#", "title", "artist", "length", "rating"}
        keep = {"plays", "skips", "last_played", "bpm"}
        fields = set(first_track.keys()) - skip
        # print(comments)
        common = set(
            filter(lambda x: len(set(map(op.itemgetter(x), tracks))) == 1, fields)
        ).union(keep)
        album = dict(zip(common, op.itemgetter(*common)(first_track)))
        album = map_album_fields(album, tracks)
        albumtable = new_table(title=album.pop("title"))

        tree = new_tree(guide_style="red", highlight=True)
        for field, value in album.items():
            if field[0].isalpha():
                fmt = "{:<20}{}"
            else:
                fmt = "{}{}"
            tree.add(fmt.format(wrap(field, "b"), value))

        tracklist = new_table(*h, border_style="red")
        for track in tracks:
            tracklist.add_row(
                str(track.get("#") or ""),
                track.get("artist", ""),
                track.get("title", ""),
                *map("{:2}".format, map(str, get_stats(track))),
                str(track.get("last_played")),
            )
        for col_idx in (1, 2, -1):
            tracklist.columns[col_idx].justify = "left"

        albumtable.title = wrap(albumtable.title, "b i magenta")
        albumtable.add_row(
            tree,
            simple_panel(Group(Align.left(Markdown(comments)), tracklist)),
        )
        print(albumtable)

    for album, tracks in it.groupby(albums, lambda x: x.get("album") or ""):
        tracks = list(tracks)
        comments = tracks[0].get("comments") or ""
        tracks = list(map(map_track_fields, tracks))
        first_track = tracks[0]

        def get(key: str, default: Any = "") -> Any:
            return first_track.get(key) or default

        albumtype = get("albumtype")
        if not album or not albumtype or albumtype == "single":
            singles.extend(tracks)
            continue

        add_and_print(tracks)
    if singles:
        tracklist = new_table(*h, border_style="red")
        for track in singles:
            tracklist.add_row(
                str(track.get("#") or ""),
                track.get("artist", ""),
                track.get("title", ""),
                *map("{:2}".format, map(str, get_stats(track))),
                str(track.get("last_played")),
            )
        for col_idx in (1, 2, -1):
            tracklist.columns[col_idx].justify = "left"
        print(
            border_panel(
                tracklist,
                title=wrap("Singles", "b blue"),
                style="cyan",
                title_align="center",
            )
        )
        # add_and_print(singles, singles=True)

    # else:
    #     title = albumartist + " - " + album

    # add_and_print(items, title)
    # if len(singles):
    # add_and_print(singles, "Singles")


def make_music_table(data: List[JSONDict], data_title: str="") -> None:
    data = list(map(map_track_fields, data))
    headers = list(filter(lambda x: x not in {"album", "albumartist"}, data[0].keys()))

    def with_colors(item):
        # type: (JSONDict) -> Tuple[Iterable[str], Optional[str]]
        row: Iterable[str]
        if "playlist" in item or "genre" or "style" in item:
            row = []
            for header in headers:
                if header in {"playlist", "genre", "style"}:
                    row.append(" ".join(map(format_with_color, item[header].split(", "))))
                elif header in {"artist", "title"}:
                    row.append(wrap(item[header], "b"))
                else:
                    row.append(str(item[header]))
            return row, None

        row = get_row(headers, item)
        plays, skips = int(item.get("plays") or 0), int(item.get("skips") or 0)
        if skips > plays:
            return map(lambda x: wrap(x, "b black"), row), "on red"
        elif plays >= 10 and skips < 2:
            return map(lambda x: wrap(x, "b black"), row), "on green"
        else:
            return row, None

    def add_and_print(
        items: Iterable[JSONDict], title: str, add_headers: bool = False
    ) -> None:
        if add_headers:
            table = new_table(*headers)
        else:
            table = new_table()
        for item in items:
            row, style = with_colors(item)
            table.add_row(*row, style=style)

        if title:
            table.title = format_with_color(title)
            table.title_justify = "left"

        return table

    singles: List[JSONDict] = []
    if "album" not in data[0]:
        title = ""
        add_headers = False
        if "group" in data_title.casefold():
            add_headers = True
        else:
            title = "tracks not groupped by album"
        print(add_and_print(data, title, add_headers=add_headers))
    else:
        for album, items in it.groupby(
            sorted(data, key=op.itemgetter("album")), op.itemgetter("album")
        ):
            first_item = next(items)
            items = it.chain([first_item], items)
            albumtype = first_item.get("albumtype", "")
            album = first_item.pop("album", "")
            albumartist = first_item.pop("albumartist", "")
            if not album or not albumtype or albumtype == "single":
                singles.extend(items)
                continue
            else:
                title = albumartist + " - " + album

            print(
                border_panel(
                    add_and_print(items, None),
                    title=wrap("   " + format_with_color(title) + "   ", "on grey3"),
                )
            )
        if len(singles):
            print(simple_panel(add_and_print(singles, "Singles")))
