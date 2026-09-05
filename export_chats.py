#!/usr/bin/env python3
"""Convert exported Claude.ai conversations into per-conversation Markdown + JSON files.

Usage:
    python3 export_chats.py ~/Downloads/claude-conversations-2026-09-05.jsonl  # from bookmarklet/export.js
    python3 export_chats.py path/to/data-export.zip                            # official export zip
    python3 export_chats.py path/to/extracted-export-dir/                      # ...or its extracted dir
    python3 export_chats.py full.jsonl one-more.jsonl                          # several sources; later wins

Accepts the .jsonl downloaded by bookmarklet/export.js (one conversation per
line, read in a streaming fashion so large archives don't need to fit in
memory), or the official claude.ai "Export data" zip / conversations.json.
All carry the same per-conversation shape: uuid, name, created_at, updated_at,
chat_messages[].
"""

import argparse
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
CHATS_DIR = REPO_ROOT / "chats"
MARKDOWN_DIR = CHATS_DIR / "markdown"
JSON_DIR = CHATS_DIR / "json"


def as_conversations(data):
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    sys.exit("Expected a list of conversations (or a single conversation object)")


def iter_conversations(source: Path):
    if source.is_dir():
        candidate = source / "conversations.json"
        if not candidate.exists():
            sys.exit(f"No conversations.json found in {source}")
        yield from as_conversations(json.loads(candidate.read_text()))
        return

    if source.suffix == ".zip":
        with zipfile.ZipFile(source) as zf:
            names = [n for n in zf.namelist() if n.endswith("conversations.json")]
            if not names:
                sys.exit("No conversations.json found inside the zip")
            yield from as_conversations(json.loads(zf.read(names[0])))
        return

    if source.suffix == ".jsonl":
        with source.open() as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"warning: skipping unreadable line {lineno} of {source.name}: {e}", file=sys.stderr)
        return

    if source.suffix == ".json":
        yield from as_conversations(json.loads(source.read_text()))
        return

    sys.exit(f"Don't know how to read: {source}")


def slugify(text: str, max_len: int = 60) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_len].rstrip("-") or "untitled"


def message_text(message: dict) -> str:
    blocks = message.get("content") or []
    if not blocks:
        return message.get("text") or ""
    parts = []
    for block in blocks:
        kind = block.get("type")
        if kind == "text" and block.get("text"):
            parts.append(block["text"])
        elif kind == "tool_use":
            parts.append(f"*[tool call: {block.get('name', 'unknown')}]*")
        elif kind == "tool_result":
            parts.append("*[tool result]*")
        elif kind == "thinking":
            continue
        elif kind:
            parts.append(f"*[{kind}]*")
    return "\n\n".join(parts) or (message.get("text") or "")


def format_markdown(convo: dict) -> str:
    title = convo.get("name") or "Untitled conversation"
    lines = [f"# {title}", ""]
    lines.append(f"- **UUID:** {convo.get('uuid', '')}")
    lines.append(f"- **Created:** {convo.get('created_at', '')}")
    lines.append(f"- **Updated:** {convo.get('updated_at', '')}")
    if convo.get("_export_error"):
        lines.append(f"- **Export error:** {convo['_export_error']} (messages not fetched)")
    lines += ["", "---", ""]

    for msg in convo.get("chat_messages", []) or []:
        sender = msg.get("sender", "unknown")
        role = "Human" if sender == "human" else "Assistant" if sender == "assistant" else sender.title()
        text = message_text(msg).strip() or "*(no text content)*"
        lines.append(f"### {role} — {msg.get('created_at', '')}")
        lines.append("")
        lines.append(text)
        lines.append("")

    return "\n".join(lines)


def date_prefix(convo: dict) -> str:
    created = convo.get("created_at", "")
    try:
        return datetime.fromisoformat(created.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return "0000-00-00"


def remove_stale(uuid8: str, keep: str):
    """Drop files for the same conversation written under an older title."""
    for directory, suffix in ((MARKDOWN_DIR, ".md"), (JSON_DIR, ".json")):
        for old in directory.glob(f"*-{uuid8}{suffix}"):
            if old.stem != keep:
                old.unlink()


def write_conversation(convo: dict) -> dict:
    title = convo.get("name") or "Untitled conversation"
    date = date_prefix(convo)
    uuid8 = (convo.get("uuid") or "")[:8] or "nouuid"
    basename = f"{date}-{slugify(title)}-{uuid8}"

    remove_stale(uuid8, basename)
    (MARKDOWN_DIR / f"{basename}.md").write_text(format_markdown(convo))
    (JSON_DIR / f"{basename}.json").write_text(json.dumps(convo, indent=2, ensure_ascii=False))

    label = title.replace("|", "\\|")
    if convo.get("_export_error"):
        label += " ⚠️ export failed"
    return {
        "date": date,
        "title": label,
        "count": len(convo.get("chat_messages", []) or []),
        "basename": basename,
    }


def write_index(entries):
    lines = [
        "# Conversation index",
        "",
        f"{len(entries)} conversations. Generated by `export_chats.py` — do not edit by hand.",
        "",
        "| Date | Title | Messages | Markdown | JSON |",
        "|------|-------|----------|----------|------|",
    ]
    for entry in sorted(entries, key=lambda e: e["date"], reverse=True):
        lines.append(
            f"| {entry['date']} | {entry['title']} | {entry['count']} "
            f"| [md](markdown/{entry['basename']}.md) "
            f"| [json](json/{entry['basename']}.json) |"
        )
    (CHATS_DIR / "INDEX.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="+", type=Path, help=".jsonl / .json / export .zip / extracted dir")
    args = parser.parse_args()

    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
    JSON_DIR.mkdir(parents=True, exist_ok=True)

    entries = {}
    failed = 0
    for source in args.sources:
        for convo in iter_conversations(source):
            entry = write_conversation(convo)
            entries[convo.get("uuid") or entry["basename"]] = entry
            failed += bool(convo.get("_export_error"))

    write_index(list(entries.values()))
    print(f"Wrote {len(entries)} conversations to {MARKDOWN_DIR.relative_to(REPO_ROOT)}/ and {JSON_DIR.relative_to(REPO_ROOT)}/")
    if failed:
        print(f"{failed} conversation(s) are title-only stubs (export failed) — re-run the browser export to retry them")
    print("Updated chats/INDEX.md")


if __name__ == "__main__":
    main()
