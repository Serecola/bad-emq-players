# Song History — Incorrect Guesses

Fully static — no backend, no database, no API keys. Just GitHub Pages.

---

## How it works

`precompute.py` reads the dump once and writes a tiny JSON file per player
into a `data/` folder. The web app fetches only the file for the player being
looked up (a few KB), so users never download the full dataset.

```
your-repo/
├── index.html
├── data/
│   ├── 1.json
│   ├── 27.json
│   ├── 42.json
│   └── ...
└── README.md
```

---

## Setup

### 1. Generate the JSON files

```bash
python precompute.py --file songhistorydump.txt
# writes data/1.json, data/27.json, etc.
```

Optional flags:
```bash
--out data     # output directory (default: data/)
--limit 100    # max results per player (default: 100)
```

### 2. Push to GitHub and enable Pages

```bash
git add index.html data/ README.md
git commit -m "add song history app"
git push
```

Then: **Settings → Pages → Source: main branch / root → Save**

Your site will be live at `https://<you>.github.io/<repo>/`

---

## Notes

- The toggle (never-correct mode) uses the same fetched file — no second request.
- If a player ID has no data, the app shows a clear "not found" message.
- To update data, re-run `precompute.py` and push the new `data/` folder.
