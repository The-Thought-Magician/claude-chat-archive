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
export_chats.py                converts the downloaded .jsonl into chats/
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
   `claude-conversations-YYYY-MM-DD.jsonl` downloads.

**Bookmarklet (one-click, after one-time setup):**
1. Create a new bookmark in your browser; for its URL, paste the entire contents
   of `bookmarklet/export-all.bookmarklet.txt`.
2. On any claude.ai tab, click the bookmark. Same download as above.

`export-current.bookmarklet.txt` does the same for only the conversation that's
currently open — handy for grabbing one chat without re-pulling everything.

How it behaves:
- **Resumable.** Every conversation is cached in the tab's IndexedDB the moment
  it's fetched. If a run is interrupted (tab closed, network drop, error), just
  run it again — it picks up from the cache instead of starting over.
- **Incremental.** Later runs only fetch conversations whose `updated_at`
  changed since the cached copy; everything else comes straight from the cache.
  A full re-export of thousands of chats takes seconds once cached.
- **Size-safe.** Output is JSONL (one conversation per line), built by
  serialising each conversation separately and streaming into a Blob. There's no
  single giant string, so archives of any size download fine.
- **Adaptive concurrency.** Starts at 8 parallel fetches (configurable). When
  the API answers 429 it honours `Retry-After`, pauses *all* workers together,
  and halves the in-flight limit; while requests keep succeeding the limit
  creeps back up. So a high setting can't cause failures — it converges on the
  fastest rate the API actually allows. The end-of-run summary reports how many
  429s were hit and where concurrency settled.
- Conversations that fail to fetch are reported in the console and included as
  title-only stubs with an `_export_error` field, so nothing is silently lost.
  They're not cached, so the next run retries them automatically.

Flags — set in the console before running, if needed:

| Set | Effect |
|-----|--------|
| `window.__CLAUDE_EXPORT_ORG = '<org uuid>'` | Use a specific organization (script prints all it can see) |
| `window.__CLAUDE_EXPORT_CONCURRENCY = 8` | Starting/max parallel fetches. Safe to set high — it self-tunes down on 429s — but past ~16 you mostly gain pauses, not speed |
| `window.__CLAUDE_EXPORT_FORCE = true` | Ignore the cache and refetch everything |
| `window.__CLAUDE_EXPORT_CLEAR = true` | Wipe the cache and stop (frees the browser storage) |

### 2. Convert into the archive

```
python3 export_chats.py ~/Downloads/claude-conversations-YYYY-MM-DD.jsonl
```

This writes `chats/markdown/*.md`, `chats/json/*.json`, and `chats/INDEX.md`.
Filenames are `<created-date>-<title-slug>-<uuid-prefix>`; a conversation whose
title changed since the last export replaces its old files rather than
duplicating them. The `.jsonl` is read line by line, so it doesn't need to fit
in memory.

Several sources can be passed at once (later ones win for the same conversation),
and the official claude.ai export zip (`data-export-*.zip`, where available) is
accepted too.

### 3. Commit

```
git add -A
git commit -m "Export chats $(date +%F)"
```

The downloaded `.jsonl` is gitignored; only the per-conversation files and the
index are tracked.

## Development

- `bookmarklet/export.js` is the source of truth. After editing it, run
  `python3 build_bookmarklet.py` to regenerate the bookmark URLs.
- Stdlib only — no dependencies to install for either script.
- The exporter relies on claude.ai's undocumented internal endpoints
  (`/api/organizations`, `.../chat_conversations`). If a run starts failing
  with 404s, the API has likely moved.
