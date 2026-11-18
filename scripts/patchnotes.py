"""Recent balance changes, read from the official patch notes: which item or hero changed, when, and how.

Patch notes list changes as lines "- <Item or hero name>: <change>". Builds read from players' games mix the
games before and after a change: an item nerfed after the start of the data window can look better than it is
(Radiant Regeneration, nerfed on 2026-10-14 and 2026-10-30, kept appearing in builds). find.py prints these
changes, knowledge.py writes them in items.md, and agent_build.py makes the agent account for them.

Usage: python3 -I patchnotes.py [days]     changes of the last <days> days (default 120)
"""
import html
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import get  # noqa: E402

LINE = re.compile(r"^\s*[-•*]\s*([^:]{2,60}?)\s*:\s*(.+)$")


def _lines(content):
    text = html.unescape(re.sub(r"<[^>]+>", "\n", content or ""))
    return [line.strip() for line in text.split("\n") if line.strip()]


def changes(days=120):
    """{"items": {item_id: [change]}, "heroes": {hero_id: [change]}}, newest first.
    A change is {"date": "YYYY-MM-DD", "ts": unix, "title": patch title, "text": the line after the name}."""
    items = {i["name"].lower(): i["id"] for i in get("/v1/assets/items") if i.get("type") == "upgrade" and i.get("shopable")}
    heroes = {h["name"].lower(): h["id"] for h in get("/v1/assets/heroes")}
    since = time.time() - days * 86400
    out = {"items": {}, "heroes": {}}
    for note in sorted(get("/v2/patches"), key=lambda n: n.get("pub_date") or "", reverse=True):
        date = (note.get("pub_date") or "")[:10]
        try:
            ts = int(time.mktime(time.strptime(date, "%Y-%m-%d")))
        except ValueError:
            continue
        if ts < since:
            continue
        for line in _lines(note.get("content")):
            m = LINE.match(line)
            if not m:
                continue
            name = m[1].strip().lower()
            entry = {"date": date, "ts": ts, "title": (note.get("title") or "").strip(), "text": m[2].strip()}
            if name in items:
                out["items"].setdefault(items[name], []).append(entry)
            elif name in heroes:
                out["heroes"].setdefault(heroes[name], []).append(entry)
    return out


def since(data, ts):
    """Only the changes made after `ts` (unix): those the data window mixes before and after."""
    return {kind: {k: [c for c in v if c["ts"] > ts] for k, v in d.items() if any(c["ts"] > ts for c in v)}
            for kind, d in data.items()}


if __name__ == "__main__":
    data = changes(int(sys.argv[1]) if len(sys.argv) > 1 else 120)
    names = {i["id"]: i["name"] for i in get("/v1/assets/items")}
    for item, cs in sorted(data["items"].items(), key=lambda x: names.get(x[0], "")):
        print(f"{names.get(item, item)}:")
        for c in cs:
            print(f"  {c['date']} {c['text']}")
