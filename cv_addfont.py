#!/usr/bin/env python3
"""
cv_addfont.py — add a font to the toolkit so --body-font / --title-font can use it.

    python3 cv_addfont.py ~/Downloads/YourFont/YourFont.ttf --as yourfont

It does the whole job:

  1. Reads the font's internal family name.
  2. Renders a test page in headless Chrome and checks whether Chrome will
     actually accept the font.
  3. If Chrome rejects it, repairs the usual breakages with fontTools and
     re-tests.
  4. Copies the (repaired) font into fonts/ and embeds it as a base64
     @font-face in cv_styles.css, so nothing needs installing system-wide
     and the HTML stays self-contained.
  5. Registers a shortcut name in fonts/fonts.json so you can write
     `--title-font yourfont` instead of a full CSS font-family list.

WHY STEP 2 MATTERS
------------------
Chrome runs every webfont through the OpenType Sanitiser and silently
refuses anything malformed — it does not warn, it just falls through to the
next font in the stack. Fonts from free-download sites are frequently
malformed. One font tested while building this tool failed with:

    OTS parsing error: maxp: Bad maxZones: 3
    cmap: Failed to parse table

and rendered as Georgia while looking, at a glance, like it had worked. So
this script verifies rather than assumes, and after building a CV you should
still confirm with:

    pdffonts applications/.../cv.pdf

which lists what genuinely got embedded.

OPTIONS
-------
    --as NAME       Shortcut to use with --body-font / --title-font
                    (default: derived from the font's family name)
    --family NAME   CSS font-family name (default: the font's own, despaced)
    --weight W      font-weight for the @font-face (default: "400 700",
                    so any weight request uses the real glyphs rather than
                    a synthetic bold)
    --style S       font-style: normal (default) or italic
    --fallbacks F   Comma-separated fallback list for the shortcut
                    (default: Georgia, serif)
    --no-repair     Fail rather than attempting a repair
    --chrome PATH   Chrome/Chromium binary
"""

import argparse
import base64
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLKIT_DIR = Path(__file__).resolve().parent
FONTS_DIR = TOOLKIT_DIR / "fonts"
REGISTRY = FONTS_DIR / "fonts.json"
STYLESHEET = TOOLKIT_DIR / "cv_styles.css"


def read_family(path: Path) -> tuple[str, str]:
    """(family, subfamily) from the font's name table."""
    d = path.read_bytes()
    if d[:4] == b"ttcf":
        sys.exit("Font collections (.ttc) aren't supported; extract a single face first.")
    num = struct.unpack(">H", d[4:6])[0]
    tables = {}
    for i in range(num):
        off = 12 + i * 16
        tag = d[off:off + 4].decode("latin-1", "replace")
        o, ln = struct.unpack(">II", d[off + 8:off + 16])
        tables[tag] = (o, ln)
    if "name" not in tables:
        return path.stem, ""
    o, _ = tables["name"]
    count, stroff = struct.unpack(">HH", d[o + 2:o + 6])
    got = {}
    for i in range(count):
        rec = o + 6 + i * 12
        plat, _enc, _lang, nid, ln, off2 = struct.unpack(">HHHHHH", d[rec:rec + 12])
        if nid not in (1, 2):
            continue
        raw = d[o + stroff + off2: o + stroff + off2 + ln]
        try:
            txt = raw.decode("utf-16-be") if plat == 3 else raw.decode("latin-1")
        except Exception:
            continue
        if txt.strip():
            got.setdefault(nid, txt.strip())
    return got.get(1, path.stem), got.get(2, "")


def chrome_accepts(path: Path, chrome: str) -> tuple[bool, str]:
    """Does Chrome's sanitiser accept this font? Returns (ok, message)."""
    b64 = base64.b64encode(path.read_bytes()).decode()
    html = (
        "<!DOCTYPE html><html><head><meta charset=utf-8><style>"
        f"@font-face{{font-family:'PROBE';src:url(data:font/ttf;base64,{b64});}}"
        "</style></head><body><div style=\"font-family:'PROBE',monospace\">Probe</div>"
        "<script>document.fonts.ready.then(()=>{document.title='S:'+"
        "[...document.fonts].map(f=>f.status).join(',')});</script></body></html>"
    )
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "probe.html"
        page.write_text(html, encoding="utf-8")
        proc = subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--enable-logging=stderr",
             "--virtual-time-budget=4000", "--dump-dom", page.resolve().as_uri()],
            capture_output=True, text=True, timeout=90,
        )
    ok = "S:loaded" in (proc.stdout or "")
    reasons = re.findall(r"OTS parsing error: ([^\"]+)", proc.stderr or "")
    return ok, (reasons[0].strip() if reasons else ("accepted" if ok else "rejected, no reason given"))


def repair(path: Path, out: Path) -> str:
    """Fix the breakages that make Chrome reject a font. Returns a summary."""
    try:
        from fontTools.ttLib import TTFont
        from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
    except ImportError:
        sys.exit("Repair needs fontTools: python3 -m pip install fonttools")

    font = TTFont(str(path), fontNumber=0, lazy=False)
    notes = []

    maxp = font.get("maxp")
    if maxp is not None and getattr(maxp, "maxZones", None) not in (None, 1, 2):
        notes.append(f"maxp.maxZones {maxp.maxZones} -> 2")
        maxp.maxZones = 2

    if "cmap" in font:
        best = font["cmap"].getBestCmap()
        if best:
            subtables = []
            for plat, enc in ((3, 1), (0, 3)):
                sub = CmapSubtable.newSubtable(4)
                sub.platformID, sub.platEncID, sub.language = plat, enc, 0
                sub.cmap = dict(best)
                subtables.append(sub)
            font["cmap"].tables = subtables
            notes.append(f"cmap rebuilt from {len(best)} mappings")

    font.save(str(out))
    return "; ".join(notes) or "re-saved with no changes needed"


def embed(family: str, font_path: Path, weight: str, style: str) -> None:
    b64 = base64.b64encode(font_path.read_bytes()).decode()
    css = STYLESHEET.read_text()
    marker = f"/* ---- font: {family} ---- */"
    rule = (f"{marker}\n@font-face{{font-family:'{family}';font-style:{style};"
            f"font-weight:{weight};src:url(data:font/ttf;base64,{b64}) "
            f"format('truetype');}}\n")
    pattern = re.compile(re.escape(marker) + r".*?\}\n", re.S)
    if pattern.search(css):
        css = pattern.sub(rule, css)
        action = "replaced"
    else:
        css = css.rstrip("\n") + "\n\n" + rule
        action = "appended"
    STYLESHEET.write_text(css)
    print(f"  {action} @font-face for '{family}' in {STYLESHEET.name} "
          f"({len(b64) // 1024}KB base64)")


def register(shortcut: str, family: str, fallbacks: str) -> None:
    data = {}
    if REGISTRY.exists():
        data = json.loads(REGISTRY.read_text())
    data[shortcut] = f"'{family}', {fallbacks}"
    REGISTRY.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"  registered shortcut '{shortcut}' in {REGISTRY.relative_to(TOOLKIT_DIR)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("font", type=Path, help="Font file (.ttf or .otf)")
    ap.add_argument("--as", dest="shortcut", default=None, help="Shortcut name for --body-font/--title-font")
    ap.add_argument("--family", default=None, help="CSS font-family name")
    ap.add_argument("--weight", default="400 700", help='font-weight (default: "400 700")')
    ap.add_argument("--style", default="normal", choices=["normal", "italic"])
    ap.add_argument("--fallbacks", default="Georgia, serif", help="Fallback list for the shortcut")
    ap.add_argument("--no-repair", action="store_true")
    ap.add_argument("--chrome", default=None)
    args = ap.parse_args()

    if not args.font.exists():
        sys.exit(f"No such file: {args.font}")
    import cv_optimiser
    chrome = cv_optimiser.find_chrome(args.chrome)
    FONTS_DIR.mkdir(exist_ok=True)

    fam, sub = read_family(args.font)
    family = args.family or re.sub(r"[^A-Za-z0-9]", "", fam) or args.font.stem
    shortcut = (args.shortcut or re.sub(r"[^a-z0-9]", "", fam.lower().split()[0])) or family.lower()
    print(f"Font: {fam} {sub}".rstrip())
    print(f"  CSS family: '{family}'   shortcut: {shortcut}")

    print("Checking whether Chrome accepts it...")
    ok, why = chrome_accepts(args.font, chrome)
    source = args.font

    if ok:
        print(f"  accepted as-is")
    else:
        print(f"  REJECTED by Chrome: {why}")
        if args.no_repair:
            sys.exit("Not repairing (--no-repair). This font would silently fall back.")
        broken = FONTS_DIR / f"{family}.original-broken{args.font.suffix}"
        shutil.copy2(args.font, broken)
        fixed = FONTS_DIR / f"{family}.ttf"
        print("Repairing with fontTools...")
        print(f"  {repair(args.font, fixed)}")
        ok, why = chrome_accepts(fixed, chrome)
        if not ok:
            sys.exit(f"Still rejected after repair: {why}\n"
                     f"This font isn't usable in Chrome. Kept the original at {broken}.")
        print(f"  accepted after repair (original kept at {broken.relative_to(TOOLKIT_DIR)})")
        source = fixed

    target = FONTS_DIR / f"{family}.ttf"
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    print(f"Installing:")
    embed(family, target, args.weight, args.style)
    register(shortcut, family, args.fallbacks)

    print()
    print("Use it with:")
    print(f"  python3 cv_build.py applications/<folder> --title-font {shortcut} --pdf")
    print("Then confirm it really embedded:")
    print(f"  pdffonts applications/<folder>/cv.pdf")


if __name__ == "__main__":
    main()
