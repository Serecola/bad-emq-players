#!/usr/bin/env python3
"""
Pre-compute artist name lookups from dump files and write a single
artists.json file mapping music_id -> list of {i: artist_id, n: name} objects.

Role priority (lower = more important):
  1 = vocalist, 2 = composer, 5 = arranger, 6 = lyricist, 0 = other

Only role=1 (vocalist) artists are included. If none exist, falls back
to role=2 (composer).

Usage:
    python precompute_artist.py
    python precompute_artist.py --am artist_music_dump.txt
                                --aa artist_alias_dump.txt
                                --out data_artist/artists.json
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


def precompute(am_path, aa_path, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True) if os.path.dirname(out_path) else None

    # 1. artist_alias: alias_id -> name (prefer is_main_name = 't')
    #    also store by artist_id for fallback
    print(f"Reading '{aa_path}'...")
    alias_name = {}        # alias_id -> latin_alias
    artist_main_name = {}  # artist_id -> latin_alias (main name)
    for row in parse_dump(aa_path, ["id", "artist_id", "latin_alias", "non_latin_alias", "is_main_name"]):
        alias_id  = int(row["id"])
        artist_id = int(row["artist_id"])
        name = row["latin_alias"] if row["latin_alias"] != "\\N" else None
        if name:
            alias_name[alias_id] = name
            if row["is_main_name"] == "t":
                artist_main_name[artist_id] = name

    # 2. artist_music: music_id -> {role -> [(artist_id, alias_id), ...]}
    print(f"Reading '{am_path}'...")
    music_roles = defaultdict(lambda: defaultdict(list))  # music_id -> role -> [(artist_id, alias_id)]
    for row in parse_dump(am_path, ["artist_id", "music_id", "role", "artist_alias_id"]):
        music_id    = int(row["music_id"])
        artist_id   = int(row["artist_id"])
        alias_id    = int(row["artist_alias_id"])
        role        = int(row["role"])
        music_roles[music_id][role].append((artist_id, alias_id))

    # 3. Build output: for each music_id, pick vocalist(s) first, fall back to composer(s)
    print(f"Building artist lookup for {len(music_roles):,} music IDs...")

    ROLE_PRIORITY = [1, 2, 5, 6, 0]  # vocalist, composer, arranger, lyricist, other

    artists = {}
    for music_id, roles in music_roles.items():
        chosen = []
        seen_ids = set()
        for role in ROLE_PRIORITY:
            if role in roles:
                for artist_id, alias_id in roles[role]:
                    name = alias_name.get(alias_id) or artist_main_name.get(artist_id)
                    if name and artist_id not in seen_ids:
                        chosen.append({"i": artist_id, "n": name})
                        seen_ids.add(artist_id)
                break  # only use the highest-priority role present

        if chosen:
            artists[music_id] = chosen

    print(f"Writing '{out_path}'...")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(artists, f, separators=(",", ":"), ensure_ascii=False)

    size_mb = os.path.getsize(out_path) / 1_000_000
    print(f"Done! Wrote {len(artists):,} entries to '{out_path}' ({size_mb:.1f} MB).")


def main():
    parser = argparse.ArgumentParser(description="Pre-compute a single artists.json lookup.")
    parser.add_argument("--am",  default="artist_music_dump.txt",  help="artist_music dump (default: artist_music_dump.txt)")
    parser.add_argument("--aa",  default="artist_alias_dump.txt",  help="artist_alias dump (default: artist_alias_dump.txt)")
    parser.add_argument("--out", default="data_artist/artists.json", help="Output file (default: data_artist/artists.json)")
    args = parser.parse_args()
    precompute(args.am, args.aa, args.out)


if __name__ == "__main__":
    main()
