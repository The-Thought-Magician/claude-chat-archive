#!/usr/bin/env python3
"""Convert a Claude.ai data export into per-conversation Markdown + JSON files.

Usage:
    python3 export_chats.py path/to/data-export.zip
    python3 export_chats.py path/to/conversations.json
    python3 export_chats.py path/to/extracted-export-dir/

Input is whatever claude.ai gives you from Settings -> Data -> Export data:
a .zip containing conversations.json (plus users.json / projects.json,
which are ignored here).
"""

import argparse
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
MARKDOWN_DIR = REPO_ROOT / "chats" / "markdown"
JSON_DIR = REPO_ROOT / "chats" / "json"


def load_conversations(source: Path):
    if source.is_dir():
        candidate = source / "conversations.json"
        if not candidate.exists():
            sys.exit(f"No conversations.json found in {source}")
        return json.loads(candidate.read_text())

    if source.suffix == ".zip":
        with zipfile.ZipFile(source) as zf:
            names = [n for n in zf.namelist() if n.endswith("conversations.json")]
            if not names:
                sys.exit("No conversations.json found inside the zip")
            return json.loads(zf.read(names[0]))

    if source.suffix == ".json":
        return json.loads(source.read_text())

    sys.exit(f"Don't know how to read: {source}")


def slugify(text: str, max_len: int = 60) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_len].rstrip("-") or "untitled"


def message_text(message: dict) -> str:
    if message.get("text"):
        return message["text"]
    parts = []
    for block in message.get("content", []) or []:
        if block.get("type") == "text" and block.get("text"):
            parts.append(block["text"])
    return "\n\n".join(parts)


def format_markdown(convo: dict) -> str:
    title = convo.get("name") or "Untitled conversation"
    created = convo.get("created_at", "")
    updated = convo.get("updated_at", "")
    uuid = convo.get("uuid", "")

    lines = [f"# {title}", ""]
    lines.append(f"- **UUID:** {uuid}")
    lines.append(f"- **Created:** {created}")
    lines.append(f"- **Updated:** {updated}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for msg in convo.get("chat_messages", []):
        sender = msg.get("sender", "unknown")
        role = "Human" if sender == "human" else "Assistant" if sender == "assistant" else sender.title()
        ts = msg.get("created_at", "")
        text = message_text(msg).strip() or "*(no text content)*"
        lines.append(f"### {role} — {ts}")
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


def write_index(entries):
    index_path = REPO_ROOT / "README.md"
    lines = [
        "# Claude Chat Archive",
        "",
        "Personal archive of exported Claude.ai conversations.",
        "Run `python3 export_chats.py <export.zip>` to (re)generate this index.",
        "",
        "| Date | Title | Messages | Markdown | JSON |",
        "|------|-------|----------|----------|------|",
    ]
    for entry in sorted(entries, key=lambda e: e["date"], reverse=True):
        lines.append(
            f"| {entry['date']} | {entry['title']} | {entry['count']} "
            f"| [md](chats/markdown/{entry['basename']}.md) "
            f"| [json](chats/json/{entry['basename']}.json) |"
        )
    index_path.write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Path to export .zip, conversations.json, or extracted dir")
    args = parser.parse_args()

    conversations = load_conversations(args.source)
    if not isinstance(conversations, list):
        sys.exit("Expected conversations.json to contain a list of conversations")

    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
    JSON_DIR.mkdir(parents=True, exist_ok=True)

    index_entries = []
    for convo in conversations:
        title = convo.get("name") or "Untitled conversation"
        date = date_prefix(convo)
        uuid8 = (convo.get("uuid") or "")[:8]
        basename = f"{date}-{slugify(title)}-{uuid8}"

        (MARKDOWN_DIR / f"{basename}.md").write_text(format_markdown(convo))
        (JSON_DIR / f"{basename}.json").write_text(json.dumps(convo, indent=2))

        index_entries.append({
            "date": date,
            "title": title.replace("|", "\\|"),
            "count": len(convo.get("chat_messages", [])),
            "basename": basename,
        })

    write_index(index_entries)
    print(f"Exported {len(index_entries)} conversations to {MARKDOWN_DIR} and {JSON_DIR}")
    print("Updated README.md index")


if __name__ == "__main__":
    main()
