#!/usr/bin/env python3
"""Convert exported Claude.ai conversations into per-conversation Markdown + JSON files.

Usage:
    python3 export_chats.py ~/Downloads/claude-conversations-2026-09-05.jsonl  # from bookmarklet/export.js
    python3 export_chats.py path/to/data-export.zip                            # official export zip
    python3 export_chats.py path/to/extracted-export-dir/                      # ...or its extracted dir
    python3 export_chats.py full.jsonl one-more.jsonl                          # several sources; later wins
    python3 export_chats.py dump.jsonl --out ~/archive --project <project uuid> # elsewhere, one project only

Accepts the .jsonl downloaded by bookmarklet/export.js (one conversation per
line, read in a streaming fashion so large archives don't need to fit in
memory), or the official claude.ai "Export data" zip / conversations.json.
All carry the same per-conversation shape: uuid, name, created_at, updated_at,
chat_messages[], and project_uuid when the chat belongs to a Claude Project.

Output goes to <out>/markdown/, <out>/json/ and <out>/INDEX.md; <out> defaults
to the chats/ directory next to this script.
"""

import argparse
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = REPO_ROOT / "chats"


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


# Markdown rendering limits. Anything clipped here is still complete in the JSON file.
TOOL_INPUT_LIMIT = 4000
TOOL_RESULT_LIMIT = 6000
SILENT_BLOCKS = {"thinking", "token_budget"}


def clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [truncated {len(text) - limit:,} more characters — full content in the JSON file]"


def fenced(text: str, lang: str = "") -> str:
    fence = "````" if "```" in text else "```"
    return f"{fence}{lang}\n{text.rstrip()}\n{fence}"


def details(summary: str, body: str) -> str:
    return f"<details>\n<summary>{summary}</summary>\n\n{body}\n\n</details>"


def tool_result_text(block: dict) -> str:
    parts = []
    for item in block.get("content") or []:
        if not isinstance(item, dict):
            parts.append(str(item))
        elif item.get("text"):
            parts.append(item["text"])
        else:
            parts.append(f"[{item.get('type', 'item')}]")
    return "\n".join(parts)


def render_blocks(message: dict) -> list:
    """One Markdown chunk per content block, in order. Falls back to the legacy text field."""
    blocks = message.get("content") or []
    if not blocks:
        text = (message.get("text") or "").strip()
        return [text] if text else []
    out = []
    for block in blocks:
        kind = block.get("type")
        if kind == "text":
            text = (block.get("text") or "").strip()
            if text:
                out.append(text)
        elif kind == "tool_use":
            name = block.get("name") or "tool"
            note = block.get("message")
            summary = f"🔧 {name}" + (f" — {note}" if note and note != name else "")
            body = json.dumps(block.get("input"), indent=2, ensure_ascii=False)
            out.append(details(summary, fenced(clip(body, TOOL_INPUT_LIMIT), "json")))
        elif kind == "tool_result":
            name = block.get("name") or "tool"
            text = tool_result_text(block)
            flag = " ⚠️ error" if block.get("is_error") else ""
            summary = f"📄 {name} result{flag} ({len(text):,} chars)"
            out.append(details(summary, fenced(clip(text, TOOL_RESULT_LIMIT))))
        elif kind in SILENT_BLOCKS:
            continue
        elif kind:
            out.append(f"*[{kind}]*")
    return out


def render_attachments(message: dict) -> list:
    """Pasted text attachments (with content) and uploaded files (metadata only)."""
    out = []
    for att in message.get("attachments") or []:
        name = att.get("file_name") or "pasted text"
        meta = [att.get("file_type"), f"{att.get('file_size')} bytes" if att.get("file_size") else None]
        meta = ", ".join(str(m) for m in meta if m)
        summary = f"📎 {name}" + (f" ({meta})" if meta else "")
        content = att.get("extracted_content") or ""
        out.append(details(summary, fenced(content)) if content else summary)
    for f in message.get("files") or []:
        name = f.get("file_name") or f.get("file_uuid") or "file"
        out.append(f"🖼️ {name} ({f.get('file_kind') or 'file'}; binary content is not included in the export)")
    return out


def ordered_messages(convo: dict):
    """Messages along the branch currently shown in the UI (leaf -> root), plus how many
    sit on other branches (edits/regenerations). Falls back to array order if the
    conversation has no tree information."""
    messages = convo.get("chat_messages") or []
    leaf = convo.get("current_leaf_message_uuid")
    by_uuid = {m.get("uuid"): m for m in messages}
    if not leaf or leaf not in by_uuid or not all(m.get("parent_message_uuid") for m in messages):
        return messages, 0
    path, seen, cur = [], set(), leaf
    while cur in by_uuid and cur not in seen:
        seen.add(cur)
        path.append(by_uuid[cur])
        cur = by_uuid[cur].get("parent_message_uuid")
    path.reverse()
    return path, len(messages) - len(path)


def format_markdown(convo: dict) -> str:
    title = convo.get("name") or "Untitled conversation"
    lines = [f"# {title}", ""]
    lines.append(f"- **UUID:** {convo.get('uuid', '')}")
    lines.append(f"- **Created:** {convo.get('created_at', '')}")
    lines.append(f"- **Updated:** {convo.get('updated_at', '')}")
    if convo.get("project_uuid"):
        lines.append(f"- **Project:** {convo['project_uuid']}")
    if convo.get("model"):
        lines.append(f"- **Model:** {convo['model']}")
    if convo.get("_export_error"):
        lines.append(f"- **Export error:** {convo['_export_error']} (messages not fetched)")

    messages, omitted = ordered_messages(convo)
    if omitted:
        lines.append(f"- **Branches:** {omitted} message(s) on other branches (edits/regenerations) "
                     f"are omitted here but present in the JSON file")
    lines += ["", "---", ""]

    for msg in messages:
        sender = msg.get("sender", "unknown")
        role = "Human" if sender == "human" else "Assistant" if sender == "assistant" else sender.title()
        chunks = render_attachments(msg) + render_blocks(msg)
        lines.append(f"### {role} — {msg.get('created_at', '')}")
        lines.append("")
        lines.append("\n\n".join(chunks) or "*(no text content)*")
        lines.append("")

    return "\n".join(lines)


def date_prefix(convo: dict) -> str:
    created = convo.get("created_at", "")
    try:
        return datetime.fromisoformat(created.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return "0000-00-00"


def remove_stale(out: Path, uuid8: str, keep: str):
    """Drop files for the same conversation written under an older title."""
    for directory, suffix in ((out / "markdown", ".md"), (out / "json", ".json")):
        for old in directory.glob(f"*-{uuid8}{suffix}"):
            if old.stem != keep:
                old.unlink()


def write_conversation(out: Path, convo: dict) -> dict:
    title = convo.get("name") or "Untitled conversation"
    date = date_prefix(convo)
    uuid8 = (convo.get("uuid") or "")[:8] or "nouuid"
    basename = f"{date}-{slugify(title)}-{uuid8}"

    remove_stale(out, uuid8, basename)
    (out / "markdown" / f"{basename}.md").write_text(format_markdown(convo))
    (out / "json" / f"{basename}.json").write_text(json.dumps(convo, indent=2, ensure_ascii=False))

    label = title.replace("|", "\\|")
    if convo.get("_export_error"):
        label += " ⚠️ export failed"
    return {
        "date": date,
        "title": label,
        "count": len(convo.get("chat_messages", []) or []),
        "basename": basename,
    }


def write_index(out: Path, entries, projects):
    scope = f" from project(s) {', '.join(projects)}" if projects else ""
    lines = [
        "# Conversation index",
        "",
        f"{len(entries)} conversations{scope}. Generated by `export_chats.py` — do not edit by hand.",
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
    (out / "INDEX.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="+", type=Path, help=".jsonl / .json / export .zip / extracted dir")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help=f"output directory (default: {DEFAULT_OUT})")
    parser.add_argument("--project", action="append", default=[], metavar="UUID",
                        help="keep only conversations in this Claude Project (repeatable)")
    args = parser.parse_args()

    out = args.out.expanduser().resolve()
    (out / "markdown").mkdir(parents=True, exist_ok=True)
    (out / "json").mkdir(parents=True, exist_ok=True)
    wanted = set(args.project)

    entries = {}
    failed = 0
    skipped = 0
    for source in args.sources:
        for convo in iter_conversations(source):
            if wanted and convo.get("project_uuid") not in wanted:
                skipped += 1
                continue
            entry = write_conversation(out, convo)
            entries[convo.get("uuid") or entry["basename"]] = entry
            failed += bool(convo.get("_export_error"))

    write_index(out, list(entries.values()), args.project)
    print(f"Wrote {len(entries)} conversations to {out}/markdown/ and {out}/json/")
    if wanted:
        print(f"Skipped {skipped} conversation(s) outside project(s) {', '.join(args.project)}")
    if failed:
        print(f"{failed} conversation(s) are title-only stubs (export failed) — re-run the browser export to retry them")
    print(f"Updated {out}/INDEX.md")


if __name__ == "__main__":
    main()
