#!/usr/bin/env python3
"""
Pre-compute incorrect guess stats from a PostgreSQL dump and write one
JSON file per player into a data/ directory.

Each file (e.g. data/27.json) contains both result sets so the web app
can serve both modes (all incorrect / never-correct) with a single fetch.

Usage:
    python precompute.py
    python precompute.py --file songhistorydump.txt
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


def precompute(input_path: str, out_dir: str, limit: int):
    if not os.path.exists(input_path):
        print(f"Error: '{input_path}' not found.")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)

    # Per-player accumulators
    incorrect = defaultdict(Counter)     # incorrect[user_id][music_id] = count
    total_guesses = defaultdict(Counter) # total_guesses[user_id][music_id] = count
    correct   = defaultdict(set)         # correct[user_id] = {music_id, ...}

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

            if row["guess_kind"] != "0":
                continue

            user_id  = int(row["user_id"])
            if user_id > 100000:
                continue
            music_id = int(row["music_id"])

            if row["is_correct"] == "t":
                correct[user_id].add(music_id)
            else:
                incorrect[user_id][music_id] += 1

            total_guesses[user_id][music_id] += 1

            total += 1
            if total % 500_000 == 0:
                print(f"  Processed {total:,} rows...", end="\r")

    print(f"\n  Processed {total:,} rows total.")
    print(f"Writing JSON files to '{out_dir}/'...")

    all_users = set(incorrect.keys()) | set(correct.keys())

    for user_id in sorted(all_users):
        inc = incorrect[user_id]
        cor = correct.get(user_id, set())

        # All incorrect, sorted by count desc
        all_incorrect = [
            {"music_id": mid, "instances": cnt, "total": total_guesses[user_id][mid]}
            for mid, cnt in inc.most_common(limit)
        ]

        # Never-correct: remove any music_id the player has ever gotten right
        never_correct = [
            {"music_id": mid, "instances": cnt, "total": total_guesses[user_id][mid]}
            for mid, cnt in inc.most_common()
            if mid not in cor
        ][:limit]

        payload = {
            "player_id":     user_id,
            "incorrect":     all_incorrect,
            "never_correct": never_correct,
        }

        out_path = os.path.join(out_dir, f"{user_id}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))

    print(f"Done! Wrote {len(all_users):,} files to '{out_dir}/'.")

    # Clean up any public_pgdump* files in the current directory
    pgdump_files = glob.glob("public_pgdump*.txt")
    if pgdump_files:
        print("Cleaning up pgdump files...")
        for path in pgdump_files:
            os.remove(path)
            print(f"  Deleted: {path}")

    print("\nNext steps:")
    print("  1. Commit the data/ folder and index.html to your repo")
    print("  2. Enable GitHub Pages (Settings → Pages → main branch / root)")
    print("  3. Done — no backend needed")


def main():
    parser = argparse.ArgumentParser(description="Pre-compute incorrect guess JSON files from a dump.")
    parser.add_argument("--file",  default="songhistorydump.txt", help="Path to the .txt dump file (default: songhistorydump.txt)")
    parser.add_argument("--out",   default="data",                help="Output directory (default: data/)")
    parser.add_argument("--limit", default=100, type=int,         help="Max results per player (default: 100)")
    args = parser.parse_args()
    precompute(args.file, args.out, args.limit)


if __name__ == "__main__":
    main()