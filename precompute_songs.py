#!/usr/bin/env python3
"""
Pre-compute song title lookups from dump files and write a single
songs.json file mapping music_id -> {s: source_title, t: song_title}.

"Best" title means: prioritise is_main_title = 't', then fall back to any available title.

Usage:
    python precompute_songs.py
    python precompute_songs.py --msm music_source_music_dump.txt
                               --mst music_source_title_dump.txt
                               --mt  music_title_dump.txt
                               --out songs.json
"""

import argparse
import json
import os
import sys
from collections import defaultdict


def parse_dump(filepath, columns):
    """Yield dicts for every data row in a PostgreSQL COPY ... FROM stdin block."""
    if not os.path.exists(filepath):
        print(f"Error: '{filepath}' not found.")
        sys.exit(1)

    in_block = False
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if line.startswith("COPY ") and "FROM stdin" in line:
                in_block = True
                continue
            if in_block and line.strip() == "\\.":
                break
            if not in_block:
                continue
            parts = line.split("\t")
            if len(parts) != len(columns):
                continue
            yield dict(zip(columns, parts))


def best_title(entries):
    """Prefers is_main_title == 't'; falls back to the first available non-null title."""
    main_titles = [t for t, m in entries if m == "t" and t and t != "\\N"]
    if main_titles:
        return main_titles[0]
    fallback = [t for t, m in entries if t and t != "\\N"]
    return fallback[0] if fallback else None


def precompute(msm_path, mst_path, mt_path, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True) if os.path.dirname(out_path) else None
    # 1. music_source_music: music_id -> list of music_source_ids
    print(f"Reading '{msm_path}'...")
    music_to_sources = defaultdict(list)
    IGNORED_SOURCE_IDS = {4, 600}
    for row in parse_dump(msm_path, ["music_source_id", "music_id", "type"]):
        if int(row["music_source_id"]) in IGNORED_SOURCE_IDS:
            continue
        music_to_sources[int(row["music_id"])].append(int(row["music_source_id"]))

    # 2. music_source_title: music_source_id -> list of (latin_title, is_main_title)
    print(f"Reading '{mst_path}'...")
    source_titles = defaultdict(list)
    for row in parse_dump(mst_path, ["music_source_id", "latin_title", "non_latin_title", "language", "is_main_title"]):
        source_titles[int(row["music_source_id"])].append(
            (row["latin_title"], row["is_main_title"])
        )

    # 3. music_title: music_id -> list of (latin_title, is_main_title)
    print(f"Reading '{mt_path}'...")
    music_titles = defaultdict(list)
    for row in parse_dump(mt_path, ["music_id", "latin_title", "non_latin_title", "language", "is_main_title"]):
        music_titles[int(row["music_id"])].append(
            (row["latin_title"], row["is_main_title"])
        )

    # 4. Combine into a single dict keyed by music_id
    all_music_ids = set(music_titles.keys()) | set(music_to_sources.keys())
    print(f"Building lookup for {len(all_music_ids):,} music IDs...")

    songs = {}
    for music_id in sorted(all_music_ids):
        source_entries = []
        for src_id in music_to_sources.get(music_id, []):
            source_entries.extend(source_titles.get(src_id, []))

        songs[music_id] = {
            "s": best_title(source_entries),       # source_title
            "t": best_title(music_titles.get(music_id, [])),  # song_title
        }

    print(f"Writing '{out_path}'...")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(songs, f, separators=(",", ":"), ensure_ascii=False)

    size_mb = os.path.getsize(out_path) / 1_000_000
    print(f"Done! Wrote {len(songs):,} entries to '{out_path}' ({size_mb:.1f} MB).")


def main():
    parser = argparse.ArgumentParser(description="Pre-compute a single songs.json title lookup.")
    parser.add_argument("--msm", default="music_source_music_dump.txt", help="music_source_music dump")
    parser.add_argument("--mst", default="music_source_title_dump.txt", help="music_source_title dump")
    parser.add_argument("--mt",  default="music_title_dump.txt",        help="music_title dump")
    parser.add_argument("--out", default="data_songs/songs.json",       help="Output file (default: data_songs/songs.json)")
    args = parser.parse_args()
    precompute(args.msm, args.mst, args.mt, args.out)


if __name__ == "__main__":
    main()