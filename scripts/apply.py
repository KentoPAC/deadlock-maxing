"""Apply translations to a build and produce the in-game "Paste build" code.

Usage: python3 -I apply.py <folder> [--lang fr|en] [--tr <json|->] [--no-clipboard] [--keep-layout]

Reads <folder>/original.json and <folder>/strings.json (with the --lang field filled in, "fr" by default; --fr is
kept as a shortcut for --lang fr --tr), writes <folder>/build_<lang>.json and the code (code.txt for French,
code.<lang>.txt otherwise), and copies it to the clipboard (wl-copy / xclip). Texts already in the target language
(the author's own language, or texts generated from the locales) are filled in automatically.
"""
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from codec import encode, encode_build  # noqa: E402
from common import GAME_LANGUAGE, fill, localize_generated, read_json, write_json, write_text  # noqa: E402
from i18n import CONTENT_LANG, LANGS  # noqa: E402

MAX_BUILD_BYTES = 16000  # limit enforced by the game
# The game only offers "Paste build" when the author account id field is present, but any value works:
# 0 keeps codes anonymous (verified in game).
ANONYMOUS_AUTHOR = 0


# --- Category layout ----------------------------------------------------------
# The game draws each category with the width/height stored in the build (UI pixels) and cuts
# overflowing text with "...". A translation longer than the original therefore needs new sizes.
# Constants calibrated on an in-game screenshot (1 unit ~ 1 px):
CHAR_W = 7.2      # average width of a description character (spacing included)
LABEL_CHAR_W = 8  # width of a category title character
LINE_H = 19       # height of a description line
MOD_W = 82        # width of an item card
CARD_H = 125      # height of an item card (icon + two-line name)
MAX_W = 1000      # maximum category width
ROW_W = 1060      # width of the build area (measured in game, 2026-11-18): a row of 1050 fits, 1070 wraps; wider blocks are cut to 1060
GAP = 10          # space the game leaves between two categories of a row (measured in game, 2026-11-18)
BUILTIN_LABELS = {"#Citadel_HeroBuilds_EarlyGame": "Early Game",
                  "#Citadel_HeroBuilds_MidGame": "Mid Game",
                  "#Citadel_HeroBuilds_LateGame": "Late Game"}


def wrap_lines(text, chars_per_line):
    """Number of lines the text takes once word-wrapped."""
    lines = 0
    for paragraph in text.split("\n"):
        lines += 1
        current = 0
        for word in paragraph.split():
            if current and current + 1 + len(word) > chars_per_line:
                lines += 1
                current = len(word)
            else:
                current += (1 if current else 0) + len(word)
    return lines


def _label_w(cat):
    label = BUILTIN_LABELS.get(cat.get("name") or "", cat.get("name") or "")
    return 30 + len(label) * LABEL_CHAR_W


def _desc_lines(cat, width):
    desc = (cat.get("description") or "").strip()
    return wrap_lines(desc, max(5, int((width - _label_w(cat) - 25) / CHAR_W))) if desc else 0


def min_width(cat, max_lines=4):
    """Narrowest width that shows the title, the items on one line (up to a full row) and the description
    within max_lines lines."""
    n = len(cat.get("mods") or [])
    width = min(ROW_W, max(_label_w(cat) + 20, 20 + n * MOD_W, 100))
    while width < ROW_W and _desc_lines(cat, width) > max_lines:
        width += 20
    return min(width, ROW_W)


def height_at(cat, width):
    """Height of a category drawn at this width: header (title + wrapped description) + rows of item cards."""
    n = len(cat.get("mods") or [])
    per_line = max(1, int((width - 20) / MOD_W))
    card_rows = -(-n // per_line) if n else 0
    header_h = max(28, _desc_lines(cat, width) * LINE_H)
    return 22 + header_h + (12 + card_rows * CARD_H if n else 0) + 10


def layout(cat):
    """Size one category on its own (kept for single-category use)."""
    w = min_width(cat)
    cat["width"], cat["height"] = float(w), float(height_at(cat, w))


def _row(cats):
    """Widths and height of a row holding these categories, or None if they cannot share one row.
    Descriptions first get up to 4 lines, then up to 7 if that is what lets the categories fit."""
    for max_lines in (4, 7):
        mins = [min_width(c, max_lines) for c in cats]
        free = ROW_W - sum(mins) - GAP * (len(cats) - 1)
        if free >= 0:
            widths = [int(w + free * w / sum(mins)) for w in mins]
            widths[-1] += ROW_W - GAP * (len(cats) - 1) - sum(widths)   # the row ends exactly at ROW_W
            return widths, max(height_at(c, w) for c, w in zip(cats, widths))
    return None


def pack(cats):
    """Place the categories like the game does (left to right, wrapping past ROW_W), keeping their order.
    Every way of cutting them into rows is tried; the one that takes the least height on screen wins.
    Each row is filled to ROW_W and its categories share one height."""
    n = len(cats)
    best = [0] + [None] * n          # best[i]: (height, cut) for the first i categories
    for i in range(1, n + 1):
        for j in range(i - 1, -1, -1):
            row = _row(cats[j:i]) if j < i - 1 else _row(cats[j:i]) or ([ROW_W], height_at(cats[j], ROW_W))
            if row is None:
                break                    # adding more categories to the left only makes the row wider
            total = (best[j][0] if j else 0) + row[1]
            if best[i] is None or total < best[i][0]:
                best[i] = (total, j, row)
    rows, i = [], n
    while i:
        _, j, (widths, h) = best[i]
        for cat, w in zip(cats[j:i], widths):
            cat["width"], cat["height"] = float(w), float(h)
        rows.insert(0, cats[j:i])
        i = j
    return rows


def has_cjk(text):
    return any("぀" <= ch <= "鿿" or "가" <= ch <= "힯" for ch in text)


def copy_to_clipboard(code):
    for cmd in (["wl-copy", "-n"], ["xclip", "-selection", "clipboard"]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, input=code.encode(), check=True)
            return True
    return False


def fill_known_texts(original, strings, lang):
    """Fill the `lang` texts that need no translator: the author's own language, or texts generated from the locales."""
    native = original.get("language") == GAME_LANGUAGE.get(lang)
    for s in strings:
        if not s.get(lang):
            s[lang] = s["text"] if native else localize_generated(s["text"], lang) or ""
    return strings


def output_paths(folder, lang):
    code = f"{folder}/code.txt" if lang == CONTENT_LANG else f"{folder}/code.{lang}.txt"
    return f"{folder}/build_{lang}.json", code


def option(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None


def main():
    folder = sys.argv[1]
    lang = "fr" if "--fr" in sys.argv else option("--lang") or CONTENT_LANG
    if lang not in LANGS:
        sys.exit(f"Unknown language {lang!r}: expected one of {LANGS}")
    src = option("--fr") or option("--tr")
    if src:  # translations as JSON (ordered list or {n: text}): a file, or "-" for stdin
        fill(folder, json.load(sys.stdin) if src == "-" else read_json(src), lang)
    original = read_json(f"{folder}/original.json")
    strings = fill_known_texts(original, read_json(f"{folder}/strings.json"), lang)
    write_json(f"{folder}/strings.json", strings, compact=True)

    missing = [s["text"][:40] for s in strings if not s.get(lang)]
    if missing:
        sys.exit(f"Missing {lang} translations: {missing}")
    for s in strings:
        node = original
        for key in s["path"][:-1]:
            node = node[key]
        node[s["path"][-1]] = s[lang]

    if "--keep-layout" not in sys.argv:
        pack(original["details"]["mod_categories"])

    # Mirror exactly what the in-game "Copy to clipboard" button produces.
    build = {
        "hero_build_id": 3,
        "hero_id": original["hero_id"],
        "author_account_id": ANONYMOUS_AUTHOR,
        "last_updated_timestamp": int(time.time()),
        "name": original.get("name"),
        "description": original.get("description") or "",
        "language": 0,
        "version": 0,
        "details": original["details"],
        "tags": original.get("tags") or [],
    }
    cut = [c.get("name") for c in build["details"]["mod_categories"] if len((c.get("description") or "").encode()) > 1024]
    if cut:
        print(f"WARNING, the game cuts these category descriptions at 1,024 bytes: {cut}", file=sys.stderr)
    leftovers = [t for t in json.dumps(build, ensure_ascii=False).split('"') if has_cjk(t)]
    if leftovers:
        print("WARNING, untranslated text left:", leftovers[:5], file=sys.stderr)

    raw = encode_build(build)
    if len(raw) > MAX_BUILD_BYTES:
        sys.exit(f"Build too large ({len(raw)} bytes > {MAX_BUILD_BYTES}): shorten the texts")
    code = encode(build)  # no trailing newline: the game rejects it
    build_path, code_path = output_paths(folder, lang)
    write_json(build_path, build, indent=1)
    write_text(code_path, code)
    print(f"{len(raw)} bytes, code: {code_path}")

    if "--no-clipboard" not in sys.argv:
        if copy_to_clipboard(code):
            print("Code copied to the clipboard")
        else:
            print("No wl-copy/xclip: copy code.txt manually")


if __name__ == "__main__":
    main()
