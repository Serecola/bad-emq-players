import sys
import os
import re
import json
import unicodedata
from collections import defaultdict

# ==========================================
# 0. BLACKLISTED CHARACTERS (untypable in dropdown)
# ==========================================
# The dropdown cannot accept these characters, so no shortcut may span
# across them.  We split the normalized string at every position where a
# blacklisted character appeared and generate substrings only within each
# resulting segment.
BLACKLISTED_CHARS = set('δΔκΚνΝοΟπΠσΣψΨχΧ')

# ==========================================
# 1. CUSTOM REPLACEMENT MAP
# ==========================================
CHAR_REPLACEMENTS = {
    # Multi-character replacements
    'Rë∀˥': 'Real',
    'βίος': 'Bios',
    
    # Single-character replacements
    '√': 'root',
    'α': 'a',
    'Λ': 'A',
    '∀': 'A',
    'μ': 'myu',
    'µ': 'myu',
    'φ': 'o',
    'Ω': '', 
    'Я': 'R',
    '×': 'x',
    '∃': 'E',
    'γ': 'y',
    'ß': 'ss',
    'ø': 'oe',
    'æ': 'ae',
    'œ': 'oe',
    'ć': 'c',
    'č': 'c',
    'đ': 'd',
    'š': 's',
    'ž': 'z',
    'ñ': 'n',
    'ü': 'u',
    'ä': 'a',
    'ö': 'o',
}

def normalize_segments(s):
    """
    Apply replacements, decompose accents, then return a list of alnum
    segments split at any blacklisted character.

    Each segment is a contiguous run of typable characters.  No shortcut
    may bridge two segments because the character between them cannot be
    typed in the dropdown.

    Returns a list of non-empty lowercase strings.
    """
    if not s or s == r'\N':
        return []
    for orig, repl in CHAR_REPLACEMENTS.items():
        s = s.replace(orig, repl)
    s = unicodedata.normalize('NFKD', s)

    segments = []
    current = []
    for c in s:
        if unicodedata.combining(c):
            continue
        cl = c.lower()
        if cl in BLACKLISTED_CHARS or c in BLACKLISTED_CHARS:
            # Blacklisted – flush current segment and start fresh
            if current:
                segments.append(''.join(current))
                current = []
        elif c.isalnum():
            current.append(cl)
        # Non-alnum, non-blacklisted (spaces, punctuation) are simply dropped
        # but do NOT split segments – only blacklisted chars split segments.
    if current:
        segments.append(''.join(current))

    return [seg for seg in segments if seg]

def normalize(s):
    """Convenience wrapper – returns the joined form (for sort key use only)."""
    return ''.join(normalize_segments(s))

def custom_sort_key(s):
    """Sort priority: spaces(0) > symbols(1) > numbers(2) > letters(3)"""
    res = []
    for c in s.lower():
        if c == ' ':
            cat = 0
        elif not c.isalnum():
            cat = 1
        elif c.isdigit():
            cat = 2
        else:
            cat = 3
        res.append((cat, c))
    return tuple(res)

def solve():
    input_file = 'music_source_title_dump.txt'
    output_dir = 'data_shortcuts'
    output_file = os.path.join(output_dir, 'shortcuts.json')
    os.makedirs(output_dir, exist_ok=True)

    print("Parsing database dump...  ")
    all_entries = []
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('   COPY'):
                    continue

                parts = line.split('\t')
                if len(parts) < 4:
                    continue

                sid, latin, _, lang = parts[0], parts[1], parts[2], parts[3]
                if latin == r'\N' or not latin:
                    continue

                segments = normalize_segments(latin)
                if not segments:
                    continue
                norm = ''.join(segments)  # joined form used only for sort key

                # Words: split the original latin on whitespace, normalize each
                # token individually, drop empties and blacklisted-only tokens.
                # A "word" here is whatever the user would type as one unbroken
                # token — we only keep tokens that survive normalization intact
                # (i.e. contain no blacklisted char that would split them).
                raw_words = re.split(r'[\s\-_/☆★·•]+', latin)
                words = []
                for w in raw_words:
                    w_segs = normalize_segments(w)
                    if len(w_segs) == 1:   # exactly one segment = no blacklisted split
                        words.append(w_segs[0])

                all_entries.append({
                    'sid': sid,
                    'latin': latin,
                    'lang': lang,
                    'norm': norm,
                    'segments': segments,
                    'words': words,
                })
    except FileNotFoundError:
        print(f"Error: {input_file} not found.")
        sys.exit(1)

    if not all_entries:
        print("No valid entries found.")
        sys.exit(1)

    # ==========================================
    # 2. SORT EXACTLY LIKE EMQ DROPDOWN
    # ==========================================
    print("Sorting entries by custom priority (space > symbol > number > letter)...  ")
    all_entries.sort(key=lambda x: custom_sort_key(x['latin']))

    # ==========================================
    # 3. BUILD EXACT UI RANKING MAP
    # ==========================================
    print("Building UI Priority Map (Prefix > Infix, then Sort Order)...  ")
    prefix_winners = {}
    infix_winners = {}

    for entry in all_entries:
        segments = entry['segments']
        sid = entry['sid']

        for seg_idx, seg in enumerate(segments):
            is_first_seg = (seg_idx == 0)

            if is_first_seg:
                # 1. Prefix matches from the first segment rank first in dropdowns
                for L in range(1, min(21, len(seg) + 1)):
                    sub = seg[:L]
                    if sub not in prefix_winners:
                        prefix_winners[sub] = sid

                # 2. Infix matches within the first segment rank second
                seen_infix = set()
                for i in range(1, len(seg)):
                    for L in range(1, min(21, len(seg) - i + 1)):
                        sub = seg[i:i+L]
                        if sub in seen_infix:
                            continue
                        seen_infix.add(sub)
                        if sub not in infix_winners:
                            infix_winners[sub] = sid
            else:
                # Non-first segments (came after a blacklisted char) are never
                # a prefix of the title — all their substrings are infix matches.
                seen_infix = set()
                for i in range(len(seg)):
                    for L in range(1, min(21, len(seg) - i + 1)):
                        sub = seg[i:i+L]
                        if sub in seen_infix:
                            continue
                        seen_infix.add(sub)
                        if sub not in infix_winners:
                            infix_winners[sub] = sid

    print(f"Map built. Prefix winners: {len(prefix_winners)}, Infix winners: {len(infix_winners)}")

    # ==========================================
    # 4. GENERATE SHORTCUTS
    # ==========================================
    id_groups = defaultdict(list)
    for entry in all_entries:
        id_groups[entry['sid']].append(entry)

    results = []
    processed_ids = 0
    sorted_ids = sorted(id_groups.keys(), key=lambda x: int(x) if x.isdigit() else x)

    print("Generating shortest 'first-in-dropdown' shortcuts...  ")
    for sid in sorted_ids:
        entries = id_groups[sid]
        ja_en_entries = [e for e in entries if e['lang'] in ('ja', 'en')]
        if not ja_en_entries:
            continue

        jp_latin_title = next((e['latin'] for e in entries if e['lang'] == 'ja'), None)
        en_latin_title = next((e['latin'] for e in entries if e['lang'] == 'en'), None)

        all_valid_shortcuts = set()
        found_shortcut = False

        for L in range(1, 21):
            current_len_shortcuts = set()
            for entry in ja_en_entries:
                segments = entry['segments']

                for seg in segments:
                    if len(seg) < L:
                        continue

                    seen_subs = set()
                    for i in range(len(seg) - L + 1):
                        sub = seg[i:i+L]
                        if sub in seen_subs:
                            continue
                        seen_subs.add(sub)

                        # Determine who actually wins this substring in the UI
                        actual_winner = prefix_winners.get(sub, infix_winners.get(sub))
                        if actual_winner == sid:
                            current_len_shortcuts.add(sub)

            if current_len_shortcuts:
                all_valid_shortcuts = current_len_shortcuts
                found_shortcut = True
                break

        if found_shortcut:
            final_shortcuts = sorted(list(all_valid_shortcuts))[:5]
            vn_id_val = int(sid) if sid.isdigit() else sid

            # ---- shortcuts_words: whole words that make this title win ----
            # Only generate word shortcuts if the title has more than one word
            title_to_check = jp_latin_title if jp_latin_title else en_latin_title
            word_count = len(title_to_check.split()) if title_to_check else 0
            
            word_shortcuts = None  # Default to None
            if word_count > 1:  # Only proceed if there are multiple words
                # Collect every normalized word across all ja/en entries, dedupe,
                # then keep only those where the whole word is itself a winning
                # shortcut (prefix or infix winner == sid).
                seen_words = set()
                word_shortcuts_list = []
                for entry in ja_en_entries:
                    for w in entry.get('words', []):
                        if w in seen_words or not w:
                            continue
                        seen_words.add(w)
                        actual_winner = prefix_winners.get(w, infix_winners.get(w))
                        if actual_winner == sid:
                            # Only add if this word is NOT already in final_shortcuts
                            if w not in final_shortcuts:
                                word_shortcuts_list.append(w)
                        if len(word_shortcuts_list) == 2:
                            break
                    if len(word_shortcuts_list) == 2:
                        break
                word_shortcuts = sorted(word_shortcuts_list)[:2] if word_shortcuts_list else None

            results.append({
                "vn_id": vn_id_val,
                "jp_latin_title": jp_latin_title,
                "en_latin_title": en_latin_title,
                "shortcuts": final_shortcuts,
                "shortcuts_words": word_shortcuts,
            })
            processed_ids += 1

        if processed_ids % 500 == 0:
            print(f"  Processed {processed_ids} IDs...  ")

    with open(output_file, 'w', encoding='utf-8') as out:
        json.dump(results, out, ensure_ascii=False, indent=2)

    print(f"\nDone! Successfully generated shortcuts for {processed_ids} IDs.")
    print(f"Output saved to {output_file}")

if __name__ == '__main__':
    solve()