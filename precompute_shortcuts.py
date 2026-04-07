import sys
import os
import json
import unicodedata
from collections import defaultdict

def normalize(s):
    """Normalize string: decompose accents, remove combining chars & non-alnum, lowercase."""
    if not s or s == r'\N':
        return ''
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c) and c.isalnum())
    return s.lower()

def solve():
    input_file = 'music_source_title_dump.txt'
    output_dir = 'data_shortcuts'
    output_file = os.path.join(output_dir, 'shortcuts.json')
    os.makedirs(output_dir, exist_ok=True)

    print("Parsing database dump...")
    all_entries = []

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(' COPY'):
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

    # Sort case-insensitively to match standard UI dropdown behavior
    all_entries.sort(key=lambda x: x['latin'].lower())
    for idx, entry in enumerate(all_entries):
        entry['rank'] = idx
        
    print("Building Substring Frequency Map (Uniqueness Check)...")
    # Count how many titles contain each substring (up to length 20 for performance)
    occurrence_count = defaultdict(int)
    for entry in all_entries:
        norm = entry['norm']
        seen_in_entry = set()
        for i in range(len(norm)):
            for j in range(i + 1, min(i + 21, len(norm) + 1)):
                sub = norm[i:j]
                if sub in seen_in_entry:
                    continue
                seen_in_entry.add(sub)
                occurrence_count[sub] += 1

    print(f"Map built. Tracked {len(occurrence_count)} unique patterns.")

    # Group entries by ID
    id_groups = defaultdict(list)
    for entry in all_entries:
        id_groups[entry['sid']].append(entry)
        
    results = []
    processed_ids = 0
    sorted_ids = sorted(id_groups.keys(), key=lambda x: int(x) if x.isdigit() else x)

    print("Generating shortest unique shortcuts...")
    for sid in sorted_ids:
        entries = id_groups[sid]
        
        # Filter for JA/EN for shortcut generation
        ja_en_entries = [e for e in entries if e['lang'] in ('ja', 'en')]
        if not ja_en_entries:
            continue
            
        jp_latin_title = next((e['latin'] for e in entries if e['lang'] == 'ja'), None)
        en_latin_title = next((e['latin'] for e in entries if e['lang'] == 'en'), None)
            
        all_valid_shortcuts = set()
        found_shortcut = False
        
        # Find shortest length L where ANY title in this ID has a UNIQUE substring
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
                    
                    # Valid only if this substring/prefix appears in exactly ONE title globally
                    if occurrence_count.get(sub, 0) == 1:
                        current_len_shortcuts.add(sub)
                
            if current_len_shortcuts:
                all_valid_shortcuts = current_len_shortcuts
                found_shortcut = True
                break
                
        if found_shortcut:
            # Sort alphabetically and limit to 5 per your format
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
            print(f"  Processed {processed_ids} IDs...")
            
    with open(output_file, 'w', encoding='utf-8') as out:
        json.dump(results, out, ensure_ascii=False, indent=2)
        
    print(f"\nDone! Successfully generated shortcuts for {processed_ids} IDs.")
    print(f"Output saved to {output_file}")

if __name__ == '__main__':
    solve()