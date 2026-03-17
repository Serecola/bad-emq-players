import glob
import os

START_LINE = "COPY public.quiz_song_history (quiz_id, sp, music_id, user_id, guess, first_guess_ms, is_correct, is_on_list, played_at, guess_kind, start_time, duration) FROM stdin;"
END_MARKER = "\\."

def trim_pgdump():
    # Find the file
    matches = glob.glob("public_pgdump*.txt")
    if not matches:
        print("No file matching 'public_pgdump*.txt' found in the current directory.")
        return

    filepath = matches[0]
    print(f"Found file: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Find start position
    start_idx = content.find(START_LINE)
    if start_idx == -1:
        print("ERROR: Start marker not found in file.")
        return

    # Find end position - first standalone \. line after the start
    lines = content[start_idx:].split("\n")
    end_offset = 0
    end_idx = -1
    for line in lines:
        if line.strip() == "\\.":
            end_idx = start_idx + end_offset
            break
        end_offset += len(line) + 1
    if end_idx == -1:
        print("ERROR: End marker not found in file.")
        return

    trimmed = content[start_idx:end_idx]

    # Write output
    output_path = "songhistorydump.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(trimmed)

    print(f"Done! Trimmed file saved as: {output_path}")

if __name__ == "__main__":
    trim_pgdump()