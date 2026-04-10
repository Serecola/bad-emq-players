import sys
import os
import json
import unicodedata
from collections import defaultdict

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

def normalize(s):
    """Apply replacements, decompose accents, strip non-alnum, lowercase."""
    if not s or s == r'\N':
        return ''
    for orig, repl in CHAR_REPLACEMENTS.items():
        s = s.replace(orig, repl)
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c) and c.isalnum())
    return s.lower()

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

                norm = normalize(latin)
                if not norm:
                    continue

                all_entries.append({
                    'sid': sid,
                    'latin': latin,
                    'lang': lang,
                    'norm': norm
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
        norm = entry['norm']
        sid = entry['sid']

        # 1. Prefix matches ALWAYS rank first in dropdowns
        for L in range(1, min(21, len(norm) + 1)):
            sub = norm[:L]
            if sub not in prefix_winners:
                prefix_winners[sub] = sid

        # 2. Infix matches rank second (only if no prefix winner exists)
        #    Track the FIRST infix match per substring according to sort order.
        seen_infix = set()
        for i in range(1, len(norm)):  # start at 1 to skip prefixes
            for L in range(1, min(21, len(norm) - i + 1)):
                sub = norm[i:i+L]
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
                norm = entry['norm']
                if len(norm) < L:
                    continue

                seen_subs = set()
                for i in range(len(norm) - L + 1):
                    sub = norm[i:i+L]
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

            results.append({
                "vn_id": vn_id_val,
                "jp_latin_title": jp_latin_title,
                "en_latin_title": en_latin_title,
                "shortcuts": final_shortcuts
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