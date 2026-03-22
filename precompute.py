#!/usr/bin/env python3
"""
Pre-compute incorrect guess stats from a PostgreSQL dump and write one
JSON file per player into a data/ directory.

Each file (e.g. data/27.json) contains both result sets so the web app
can serve both modes (all incorrect / never-correct) with a single fetch.

Usage:
    python precompute.py
    python precompute.py --file songhistorydump.txt --out data --limit 100

Then commit the data/ folder alongside index.html and push to GitHub Pages.
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict

COLUMNS = ["quiz_id", "sp", "music_id", "user_id", "guess", "first_guess_ms",
           "is_correct", "is_on_list", "played_at", "guess_kind", "start_time", "duration"]

AM_COLUMNS = ["artist_id", "music_id", "role", "artist_alias_id"]
AA_COLUMNS = ["id", "artist_id", "latin_alias", "non_latin_alias", "is_main_name"]

VOCALIST_ROLE = 1  # only pull vocalists


def parse_dump(filepath, columns):
    """Yield dicts for every data row in a PostgreSQL COPY ... FROM stdin block."""
    if not os.path.exists(filepath):
        return
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


def load_artist_lookup(am_path, aa_path):
    """Returns music_id -> list of (artist_id, name) for the top-priority role."""
    # alias_id -> name
    alias_name = {}
    artist_main_name = {}
    artist_any_name = {}  # fallback: first available alias per artist_id
    for row in parse_dump(aa_path, AA_COLUMNS):
        alias_id  = int(row["id"])
        artist_id = int(row["artist_id"])
        name = row["latin_alias"] if row["latin_alias"] != "\\N" else None
        if name:
            alias_name[alias_id] = name
            if artist_id not in artist_any_name:
                artist_any_name[artist_id] = name
            if row["is_main_name"] == "t":
                artist_main_name[artist_id] = name

    # music_id -> role -> [(artist_id, alias_id)]
    music_roles = defaultdict(lambda: defaultdict(list))
    for row in parse_dump(am_path, AM_COLUMNS):
        music_roles[int(row["music_id"])][int(row["role"])].append(
            (int(row["artist_id"]), int(row["artist_alias_id"]))
        )

    # music_id -> [(artist_id, name)]
    music_to_artists = {}
    for music_id, roles in music_roles.items():
        if VOCALIST_ROLE not in roles:
            continue
        chosen = []
        seen = set()
        for artist_id, alias_id in roles[VOCALIST_ROLE]:
            name = alias_name.get(alias_id) or artist_main_name.get(artist_id)
            if name and artist_id not in seen:
                chosen.append((artist_id, name))
                seen.add(artist_id)
        if chosen:
            music_to_artists[music_id] = chosen

    return music_to_artists, artist_main_name, artist_any_name


def precompute(input_path: str, out_dir: str, limit: int, am_path: str, aa_path: str, msm_path: str):
    if not os.path.exists(input_path):
        print(f"Error: '{input_path}' not found.")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)

    # Load music_ids to ignore (linked to music_source_id 4 or 600)
    IGNORED_TYPE_IDS = {4, 600}
    ignored_music_ids = set()
    if os.path.exists(msm_path):
        print(f"Loading ignored music IDs from '{msm_path}'...")
        with open(msm_path, "r", encoding="utf-8") as f:
            in_block = False
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
                if len(parts) != 3:
                    continue
                music_id = int(parts[1])
                if int(parts[2]) in IGNORED_TYPE_IDS:
                    ignored_music_ids.add(music_id)
        print(f"  Ignoring {len(ignored_music_ids):,} music IDs linked to music types {IGNORED_TYPE_IDS}.")

    # Load artist lookup
    print("Loading artist data...")
    music_to_artists, artist_main_name, artist_any_name = load_artist_lookup(am_path, aa_path)
    print(f"  Loaded artist info for {len(music_to_artists):,} songs.")

    # Per-player accumulators — song guess (guess_kind=0)
    incorrect = defaultdict(Counter)
    total_guesses = defaultdict(Counter)
    correct = defaultdict(set)

    # Per-player accumulators — artist guess (guess_kind=1), keyed by artist_id
    art_incorrect = defaultdict(Counter)   # art_incorrect[user_id][artist_id] = count
    art_total     = defaultdict(Counter)   # art_total[user_id][artist_id] = count
    art_correct   = defaultdict(set)       # art_correct[user_id] = {artist_id, ...}

    in_copy_block = False
    total = 0

    print(f"Reading '{input_path}'...")

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")

            if line.startswith("COPY public.quiz_song_history"):
                in_copy_block = True
                continue
            if in_copy_block and line.strip() == "\\.":
                break
            if not in_copy_block:
                continue

            parts = line.split("\t")
            if len(parts) != len(COLUMNS):
                continue

            row = dict(zip(COLUMNS, parts))
            guess_kind = row["guess_kind"]
            if guess_kind not in ("0", "1"):
                continue

            user_id  = int(row["user_id"])
            if user_id > 100000:
                continue
            music_id = int(row["music_id"])
            if music_id in ignored_music_ids:
                continue

            if guess_kind == "0":
                if row["is_correct"] == "t":
                    correct[user_id].add(music_id)
                else:
                    incorrect[user_id][music_id] += 1
                total_guesses[user_id][music_id] += 1

            else:  # guess_kind == "1" — artist guess, aggregate by artist_id
                artists_for_song = music_to_artists.get(music_id, [])
                for artist_id, _ in artists_for_song:
                    if row["is_correct"] == "t":
                        art_correct[user_id].add(artist_id)
                    else:
                        art_incorrect[user_id][artist_id] += 1
                    art_total[user_id][artist_id] += 1

            total += 1
            if total % 500_000 == 0:
                print(f"  Processed {total:,} rows...", end="\r")

    print(f"\n  Processed {total:,} rows total.")
    print(f"Writing JSON files to '{out_dir}/'...")

    # artist_main_name already available from load_artist_lookup (is_main_name='t')

    all_users = set(incorrect.keys()) | set(correct.keys())

    for user_id in sorted(all_users):
        inc = incorrect[user_id]
        cor = correct.get(user_id, set())

        all_incorrect = [
            {"music_id": mid, "instances": cnt, "total": total_guesses[user_id][mid]}
            for mid, cnt in inc.most_common(limit)
        ]
        never_correct = [
            {"music_id": mid, "instances": cnt, "total": total_guesses[user_id][mid]}
            for mid, cnt in inc.most_common()
            if mid not in cor
        ][:limit]

        # Artist guess stats — keyed by artist_id
        art_inc = art_incorrect[user_id]
        art_cor = art_correct.get(user_id, set())

        all_art_incorrect = [
            {"artist_id": aid, "name": artist_main_name.get(aid) or artist_any_name.get(aid, str(aid)), "instances": cnt, "total": art_total[user_id][aid]}
            for aid, cnt in art_inc.most_common(limit)
        ]
        art_never_correct = [
            {"artist_id": aid, "name": artist_main_name.get(aid) or artist_any_name.get(aid, str(aid)), "instances": cnt, "total": art_total[user_id][aid]}
            for aid, cnt in art_inc.most_common()
            if aid not in art_cor
        ][:limit]

        payload = {
            "player_id":         user_id,
            "incorrect":         all_incorrect,
            "never_correct":     never_correct,
            "art_incorrect":     all_art_incorrect,
            "art_never_correct": art_never_correct,
        }

        # Skip players with no song with 5+ incorrect guesses
        if not any(e["instances"] >= 5 for e in all_incorrect):
            continue

        out_path = os.path.join(out_dir, f"{user_id}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))

    print(f"Done! Wrote {len(all_users):,} files to '{out_dir}/'.")

    pgdump_files = glob.glob("public_pgdump*.txt")
    if pgdump_files:
        print("Cleaning up pgdump files...")
        for path in pgdump_files:
            os.remove(path)
            print(f"  Deleted: {path}")

def main():
    parser = argparse.ArgumentParser(description="Pre-compute incorrect guess JSON files from a dump.")
    parser.add_argument("--file",  default="songhistorydump.txt",      help="Song history dump (default: songhistorydump.txt)")
    parser.add_argument("--out",   default="data",                     help="Output directory (default: data/)")
    parser.add_argument("--limit", default=100, type=int,              help="Max results per player (default: 100)")
    parser.add_argument("--am",    default="artist_music_dump.txt",    help="artist_music dump (default: artist_music_dump.txt)")
    parser.add_argument("--aa",    default="artist_alias_dump.txt",    help="artist_alias dump (default: artist_alias_dump.txt)")
    parser.add_argument("--msm",   default="music_source_music_dump.txt", help="music_source_music dump (default: music_source_music_dump.txt)")
    args = parser.parse_args()
    precompute(args.file, args.out, args.limit, args.am, args.aa, args.msm)


if __name__ == "__main__":
    main()