# Claude Chat Archive

Personal archive of my Claude.ai conversations, stored as Markdown (for reading)
and JSON (for fidelity), one file per conversation.

Works on any plan, including Enterprise where the built-in "Export data" option
isn't available: the exporter runs inside your logged-in claude.ai browser tab
and uses the same internal API the web app itself uses.

## Layout

```
bookmarklet/export.js          browser-side exporter (source)
bookmarklet/*.bookmarklet.txt  the same, packaged as javascript: bookmark URLs
build_bookmarklet.py           regenerates the .bookmarklet.txt files from export.js
export_chats.py                converts the downloaded JSON into chats/
chats/markdown/                one .md per conversation
chats/json/                    one .json per conversation (raw API payload)
chats/INDEX.md                 generated table of every conversation
```

## Exporting

### 1. Grab the conversations from claude.ai

Pick whichever is more convenient:

**Console (no setup):**
1. Open <https://claude.ai> in your browser, logged in.
2. Open DevTools (F12 / Ctrl+Shift+I / Cmd+Opt+I) → **Console** tab.
3. Paste the contents of `bookmarklet/export.js` and press Enter.
4. Watch progress in the console. When it finishes, a file named
   `claude-conversations-YYYY-MM-DD.json` downloads.

**Bookmarklet (one-click, after one-time setup):**
1. Run `python3 build_bookmarklet.py` once (already done — files are committed).
2. Create a new bookmark in your browser; for its URL, paste the entire contents
   of `bookmarklet/export-all.bookmarklet.txt`.
3. On any claude.ai tab, click the bookmark. Same download as above.

`export-current.bookmarklet.txt` does the same for only the conversation that's
currently open — handy for grabbing one chat without re-pulling everything.

Notes:
- If your account belongs to more than one organization, the script prints them
  all to the console and picks the active one. To force a specific org, run
  `window.__CLAUDE_EXPORT_ORG = '<org uuid>'` in the console first.
- Fetching is throttled (3 concurrent, small delay, backoff on 429). A few
  hundred conversations takes a minute or two.
- Any conversation that fails to fetch is listed in the console at the end and
  included in the download as a title-only stub, so nothing is silently lost.

### 2. Convert into the archive

```
python3 export_chats.py ~/Downloads/claude-conversations-YYYY-MM-DD.json
```

This writes `chats/markdown/*.md`, `chats/json/*.json`, and `chats/INDEX.md`.
Filenames are `<created-date>-<title-slug>-<uuid-prefix>`, so re-running on a
newer export updates existing conversations in place and adds new ones.

The official claude.ai export zip (`data-export-*.zip`, where available) is also
accepted as input — same command.

### 3. Commit

```
git add -A
git commit -m "Export chats $(date +%F)"
```

The downloaded source JSON is gitignored; only the per-conversation files and
the index are tracked.

## Development

- `bookmarklet/export.js` is the source of truth. After editing it, run
  `python3 build_bookmarklet.py` to regenerate the bookmark URLs.
- Stdlib only — no dependencies to install for either script.
