#!/usr/bin/env python3
"""
cv_optimiser.py — auto-reformat a CV to fill its allowed page budget.

Built for this toolkit's CV structure (the .page / .sec / .entry / .role /
.meta / p.sum / ol.pubs / .list / .eduentry / .award / .sgroup classes, styled
via the shared cv_styles.css). It won't do anything useful on a CV that
doesn't use these class names.

WHAT IT DOES
------------
Finds the first <style>...</style> block in <head> (the hand-tuned
"spacing overrides" block every version of this CV has had) and replaces it
wholesale with one computed to:

  1. Use the largest body-text size that is both professionally acceptable
     and makes the content fit within --max-pages.
  2. Within that font size, spread out line-heights/margins as much as
     possible while still fitting --max-pages — so the page is used, not
     left half-blank.

FONT SIZE RATIONALE
-------------------
Professional consensus for printed resumes/CVs:
  - Body text: 10-12pt, start at 11pt; do not go below 10pt (harder to
    read, reads as trying to hide a length problem).
  - Name: 16-20pt. Section headings: 12-16pt (this template uses small
    uppercase eyebrow labels rather than full headings, so it gets a
    smaller share of that range, scaled off the body size instead).
  - Margins: 1in is the traditional standard; 0.5in is the accepted floor
    for print/ATS. Below 0.5in, ATS parsers can clip edge text.

This script defaults to --target-pt 11 --min-pt 10 --margin-in 0.75 and
will not go below 10pt body text or 0.5in margins no matter how large
--max-pages is set — if the content still doesn't fit, it says so instead
of quietly shrinking further.

USAGE
-----
    python3 cv_optimiser.py INPUT.html [options]

Options:
    --max-pages N       Maximum pages allowed (default: 1)
    --output PATH       Where to write the result (default: INPUT.optimised.html)
    --target-pt PT      Preferred body font size in points (default: 11)
    --min-pt PT         Hard floor for body font size in points (default: 10)
    --margin-in IN      Top/bottom page margin in inches (default: 0.75)
    --side-margin-in IN Left/right page margin in inches (default: 0.75)
    --chrome PATH       Path to a Chrome/Chromium binary (auto-detected if omitted)
    --keep-temp         Don't delete the intermediate PDFs (for debugging)

EXIT STATUS
-----------
0 normally. 2 if the content could not be made to fit --max-pages even at
--min-pt (the file is still written — best effort at the tightest allowed
settings — but you should raise --max-pages or trim content).
"""

import argparse
import csv
import datetime as _dt
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PT_TO_PX = 96 / 72  # CSS px per point, at the standard 96dpi CSS reference

# Font stacks. Body is what nearly all the text uses; title is just the name
# at the top. Named shortcuts can be passed to --body-font / --title-font, or
# give a full CSS font-family list of your own.
#
# Helvetica Neue ships with macOS and Chrome embeds it into the PDF, so a
# recipient on any platform sees it correctly. Fonts added with
# cv_addfont.py are embedded as base64 in cv_styles.css, so they need no
# system install either.
# Built-ins are only fonts that need no embedding, so these shortcuts work
# in any copy of the toolkit. Embedded fonts are registered in
# fonts/fonts.json by cv_addfont.py instead, because whether they exist
# depends on which stylesheet you have.
FONT_STACKS = {
    "helvetica": "'Helvetica Neue', Helvetica, Arial, sans-serif",
    "arial": "Arial, 'Helvetica Neue', Helvetica, sans-serif",
    "georgia": "Georgia, 'Times New Roman', Times, serif",
    "times": "'Times New Roman', Times, serif",
    "system": "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
}


def _registry() -> dict:
    registry = Path(__file__).resolve().parent / "fonts" / "fonts.json"
    if registry.exists():
        try:
            import json
            return json.loads(registry.read_text())
        except (ValueError, OSError):
            pass  # a broken registry shouldn't stop a CV from building
    return {}


def all_font_stacks() -> dict:
    """Built-in shortcuts plus anything cv_addfont.py has registered."""
    stacks = dict(FONT_STACKS)
    stacks.update({k: v for k, v in _registry().items() if not k.startswith("_")})
    return stacks


def default_font(slot: str) -> str:
    """Default body/title font, overridable per repo via fonts.json.

    Set it there rather than in this file, so the same script works whether
    or not a given font is actually embedded:

        { "_defaults": { "title": "yourfont", "body": "helvetica" } }
    """
    defaults = _registry().get("_defaults") or {}
    return defaults.get(slot) or "helvetica"


def embedded_families() -> set:
    """Families actually present as @font-face rules in the stylesheet."""
    css = Path(__file__).resolve().parent / "cv_styles.css"
    if not css.exists():
        return set()
    try:
        text = css.read_text()
    except OSError:
        return set()
    return set(re.findall(r"@font-face\{font-family:'([^']+)'", text))


_font_warned: set = set()

# Families we can rely on without embedding them.
SYSTEM_FAMILIES = {
    "helvetica neue", "helvetica", "arial", "georgia", "times new roman",
    "times", "courier new", "verdana", "tahoma", "trebuchet ms", "palatino",
    "baskerville", "system-ui", "-apple-system", "segoe ui", "roboto",
    "sans-serif", "serif", "monospace",
}


def font_stack(name: str, slot: str = "body") -> str:
    """Resolve a shortcut, or pass through a CSS font-family list unchanged.

    Warns rather than failing silently when a font can't actually be used:
    Chrome drops to the next family in the stack without any complaint, so an
    unembedded font or a typo'd shortcut otherwise produces a CV set in a
    font you didn't choose and never notice.
    """
    key = (name or "").strip()
    stacks = all_font_stacks()
    resolved = stacks.get(key.lower())

    if resolved is None:
        # Not a shortcut. A real CSS list has a comma or a quote; anything
        # else is almost certainly a misremembered shortcut name.
        if key and "," not in key and "'" not in key and key not in _font_warned:
            _font_warned.add(key)
            print(f"WARNING: '{key}' is not a known font shortcut and doesn't look like a "
                  f"CSS font-family list, so it will be ignored by the browser. "
                  f"Known: {', '.join(sorted(stacks))}", file=sys.stderr)
        resolved = key

    first = re.match(r"\s*'([^']+)'|\s*([A-Za-z][\w -]*)", resolved)
    if first:
        family = (first.group(1) or first.group(2) or "").strip()
        if (family and family.lower() not in SYSTEM_FAMILIES
                and family not in embedded_families()
                and family not in _font_warned):
            _font_warned.add(family)
            print(f"WARNING: '{family}' (for the {slot}) is neither a system font nor "
                  f"embedded in cv_styles.css, so the browser will quietly use the next "
                  f"font in the stack instead. Embed it with: "
                  f"python3 cv_addfont.py path/to/font.ttf --as <name>", file=sys.stderr)
    return resolved


# Utility classes, so any phrase in a content file can opt into a font or
# weight with the [text]{.class} syntax. Generated from the font registry, so
# a font added by cv_addfont.py gets its .f-<name> class automatically.
WEIGHT_CLASSES = {"light": 300, "regular": 400, "medium": 500, "bold": 700}


def font_utility_css(indent: str = "    ") -> str:
    rules = [f".f-{name}{{font-family:{stack};}}"
             for name, stack in sorted(all_font_stacks().items())]
    rules += [f".{name}{{font-weight:{weight};}}" for name, weight in WEIGHT_CLASSES.items()]
    rules += [".small{font-size:0.85em;}", ".large{font-size:1.25em;}",
              ".caps{text-transform:uppercase;}", ".nocaps{text-transform:none;}"]
    return ("\n" + indent).join(rules)

# ---------------------------------------------------------------------------
# Application log. "Date CV created" and "CV file used" are filled in
# automatically every time this script writes a CV; everything else is yours
# to fill in by hand (in Excel/Numbers/Sheets — it's ordinary CSV).
# Rows are keyed on "CV file used", so re-running the optimiser on the same
# CV updates that row's date instead of adding a duplicate.
# ---------------------------------------------------------------------------
LOG_FILENAME = "application_log.csv"
TOOLKIT_DIR = Path(__file__).resolve().parent


def default_log_path() -> Path:
    """The single tracker, kept beside the scripts.

    Deliberately NOT relative to the CV being built: CVs live in
    applications/, and defaulting to the output's own folder silently starts
    a second log there, splitting the history in two.
    """
    return TOOLKIT_DIR / LOG_FILENAME


def log_key(path: Path) -> str:
    """How a CV is identified in the log: its path relative to the toolkit.

    A bare filename is not enough once each application has its own folder,
    because every application's CV is called cv.html. Bare names would
    collide and each new application would overwrite the previous one's row.
    """
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(TOOLKIT_DIR).as_posix()
    except ValueError:  # built outside the toolkit folder
        return resolved.name


LOG_COLUMNS = [
    "Job application link",
    "Company",
    "Role",
    "Application deadline",
    "Date CV created",      # auto-filled
    "CV file used",         # auto-filled
    "Notes",
    "Job role",
    "Necessary Criteria",
    "Desirable Criteria",
    "Outcome",
    "Date of outcome",
]
AUTO_COLUMNS = ("Date CV created", "CV file used")


def warn_if_spreadsheet_newer(log_path: Path) -> None:
    """Spot edits made in Numbers/Excel that never reached the CSV.

    Double-clicking a .csv on macOS opens it in Numbers, and Cmd-S there
    writes a .numbers file, silently leaving the .csv untouched. You then
    believe you have recorded an outcome that the log does not actually
    contain. If a sibling spreadsheet is newer than the CSV, say so.
    """
    if not log_path.exists():
        return
    csv_mtime = log_path.stat().st_mtime
    for suffix in (".numbers", ".xlsx", ".xls", ".ods"):
        sibling = log_path.with_suffix(suffix)
        if sibling.exists() and sibling.stat().st_mtime > csv_mtime:
            print(f"NOTE: {sibling.name} is newer than {log_path.name}. If you edited it "
                  f"there, export back to CSV or those changes aren't in the log.",
                  file=sys.stderr)
            return


def update_application_log(log_path: Path, cv_filename: str, date_str: str | None = None,
                            company: str | None = None, role: str | None = None,
                            url: str | None = None, deadline: str | None = None) -> str:
    """Record (or refresh) this CV's row in the application log.

    Returns "created", "updated", or "appended" so the caller can report what
    happened. Never discards columns or rows it doesn't recognise: if you add
    your own columns in a spreadsheet, they survive.
    """
    warn_if_spreadsheet_newer(log_path)
    date_str = date_str or _dt.date.today().isoformat()
    supplied = {
        "Company": company, "Role": role,
        "Job application link": url, "Application deadline": deadline,
    }

    rows: list[dict] = []
    columns = list(LOG_COLUMNS)
    existed = log_path.exists()
    if existed:
        with log_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames:
                # Preserve the user's column order, appending any of ours
                # they don't have yet (e.g. after we add a new field).
                columns = list(reader.fieldnames) + [
                    c for c in LOG_COLUMNS if c not in reader.fieldnames
                ]
            rows = [dict(r) for r in reader]

    target = next((r for r in rows if (r.get("CV file used") or "").strip() == cv_filename), None)
    if target is None:
        target = {c: "" for c in columns}
        target["CV file used"] = cv_filename
        rows.append(target)
        action = "created" if not existed else "appended"
    else:
        action = "updated"
    target["Date CV created"] = date_str
    # Only fill supplied fields that are currently empty, so a value you
    # typed by hand is never overwritten by a command-line flag.
    for key, value in supplied.items():
        if value and not (target.get(key) or "").strip():
            target[key] = value

    tmp_path = log_path.with_suffix(log_path.suffix + ".tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})
    os.replace(tmp_path, log_path)  # atomic: never leaves a half-written log
    return action

# ---------------------------------------------------------------------------
# Spacing presets. Every value here was empirically validated by hand on this
# CV template (rendered to PDF and checked with headless Chrome) across
# several rounds of "too tight" / "too loose" / "just right" iteration.
# TIGHT = as dense as this template still reads comfortably.
# LOOSE = as spread out as still looks like a normal, uncrowded CV.
# fill (0..1) linearly interpolates between them.
# ---------------------------------------------------------------------------
TIGHT = dict(
    headline_mb=5, sec_mt=4, sec_mb=2, sec_pad=1, entry_mb=2, meta_mb=1,
    sum_lh=1.15, sum_mb=2, metrics_mb=2, pub_mb=1, pub_lh=1.14,
    ul_mt=1, ul_mb=2, li_lh=1.12, li_mb=0, edu_mb=3, award_lh=1.2, award_mb=3,
)
LOOSE = dict(
    headline_mb=8, sec_mt=9, sec_mb=5, sec_pad=2, entry_mb=12, meta_mb=3,
    sum_lh=1.35, sum_mb=4, metrics_mb=4, pub_mb=4, pub_lh=1.32,
    ul_mt=2, ul_mb=3, li_lh=1.32, li_mb=3, edu_mb=7, award_lh=1.3, award_mb=7,
)

# Font sizes for every other labelled element, expressed as a ratio against
# body size, fixed at the ratios this template has used throughout (so the
# visual hierarchy — name > headline > role > body > section-label — stays
# consistent as body size changes).
FONT_RATIOS = dict(
    name=2.65, headline=1.22, contact=1.02, sec=0.97, role=1.14,
    meta=0.97, sum=1.05, pub=0.97, edutitle=1.08,
)


def interp(t, l, fill):
    return t + (l - t) * fill


def build_style_block(body_pt: float, fill: float, margin_in: float,
                      side_margin_in: float, paper: str = "A4",
                      body_font: str | None = None, title_font: str | None = None) -> str:
    body = round(body_pt * PT_TO_PX, 2)
    body_stack = font_stack(body_font or default_font("body"), "body")
    title_stack = font_stack(title_font or default_font("title"), "title")
    utility_css = font_utility_css()
    sizes = {k: round(body * r, 2) for k, r in FONT_RATIOS.items()}
    s = {k: interp(TIGHT[k], LOOSE[k], fill) for k in TIGHT}

    def px(v):
        return round(v, 2)

    return f"""  <style>
    .sgroup{{font-size:{body}px;line-height:{s['sum_lh']:.3f};margin:0 0 {px(s['sum_mb'])}px;color:#3a3a3a;}}
    .sgroup b{{display:block;font-weight:500;color:#242424;font-size:{body}px;
      text-transform:none;letter-spacing:0;margin-bottom:1px;}}
    /* Auto-generated by cv_optimiser.py (body={body_pt}pt, fill={fill:.2f}) — re-run the script rather than hand-editing */
    @page{{size:{paper};margin:{margin_in}in {side_margin_in}in;}}
    html,body{{font-family:{body_stack};}}
    .name{{font-family:{title_stack};}}
    {utility_css}
    .name{{font-size:{sizes['name']}px;}}
    .headline{{font-size:{sizes['headline']}px;margin:0 0 {px(s['headline_mb'])}px;}}
    .contact{{font-size:{sizes['contact']}px;font-weight:300;}}
    .sec{{margin:{px(s['sec_mt'])}px 0 {px(s['sec_mb'])}px;padding:0 0 {px(s['sec_pad'])}px;font-size:{sizes['sec']}px;}}
    .entry{{margin-bottom:{px(s['entry_mb'])}px;}}
    .role{{font-size:{sizes['role']}px;}}
    .meta{{margin-bottom:{px(s['meta_mb'])}px;font-size:{sizes['meta']}px;}}
    p.sum{{font-size:{sizes['sum']}px;line-height:{s['sum_lh']:.3f};margin:2px 0 {px(s['sum_mb'])}px;}}
    .metrics{{margin-bottom:{px(s['metrics_mb'])}px;font-size:{sizes['meta']}px;}}
    ol.pubs{{margin-top:2px;}}
    ol.pubs li{{margin-bottom:{px(s['pub_mb'])}px;line-height:{s['pub_lh']:.3f};font-size:{sizes['pub']}px;}}
    ul{{margin:{px(s['ul_mt'])}px 0 {px(s['ul_mb'])}px;}}
    li{{line-height:{s['li_lh']:.3f};margin-bottom:{px(s['li_mb'])}px;font-size:{body}px;}}
    .list{{line-height:{s['li_lh']:.3f};}}
    .list li{{margin-bottom:{px(s['li_mb'])}px;}}
    /* Blue university names in Education, matching the .org colour */
    .uni{{color:var(--blue);}}
    .eduentry{{margin:0 0 {px(s['edu_mb'])}px;break-inside:avoid;}}
    .edutitle{{font-size:{sizes['edutitle']}px;color:#242424;margin:0 0 1px;line-height:1.2;}}
    .eduentry .meta{{margin-bottom:1px;}}
    /* Inline icon + muted text for compact meta lines */
    .iico{{width:11px;height:11px;fill:var(--gray);vertical-align:-1px;margin-right:3px;}}
    .mut{{color:var(--muted);}}
    .bitw{{font-size:{body}px;color:#3a3a3a;}}
    .edesc{{font-size:{body}px;line-height:{s['li_lh']:.3f};color:#3a3a3a;margin-top:1px;}}
    .award{{font-size:{sizes['meta']}px;line-height:{s['award_lh']:.3f};margin-bottom:{px(s['award_mb'])}px;}}
  </style>"""


STYLE_RE = re.compile(r"<style>.*?</style>", re.S)
WARNING_RE = re.compile(r"<!--\s*CV-OPTIMIZER WARNING.*?-->\s*\n?", re.S)


def apply_style(html: str, style_block: str) -> str:
    if STYLE_RE.search(html):
        return STYLE_RE.sub(lambda _m: style_block, html, count=1)
    # No existing <style> block — insert one just before </head>.
    return html.replace("</head>", style_block + "\n</head>", 1)


def strip_old_warning(html: str) -> str:
    return WARNING_RE.sub("", html)


def find_chrome(explicit: str | None) -> str:
    if explicit:
        return explicit
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    sys.exit(
        "Could not find a Chrome/Chromium binary. Pass one explicitly with --chrome "
        "(any Chromium-based browser that supports --headless --print-to-pdf works)."
    )


def render_page_count(html_path: Path, chrome: str, tmp_dir: Path, keep_temp: bool) -> int:
    pdf_path = tmp_dir / (html_path.stem + ".preview.pdf")
    result = subprocess.run(
        [
            chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri(),
        ],
        capture_output=True, text=True, timeout=60,
    )
    if not pdf_path.exists():
        raise RuntimeError(
            f"Chrome failed to render a PDF.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    data = pdf_path.read_bytes()
    if not keep_temp:
        pdf_path.unlink(missing_ok=True)
    return count_pdf_pages(data)


def count_pdf_pages(data: bytes) -> int:
    """Page count of an already-rendered PDF.

    Split out so callers that have written a PDF already can count it
    without paying for a second render.
    """
    # Count leaf page objects (/Type /Page, NOT /Type /Pages). Chrome writes
    # a hierarchical page tree for longer documents, with multiple internal
    # /Pages nodes each carrying their own /Count for their subtree — taking
    # the first /Count match (as a naive regex would) silently grabs a
    # subtree total instead of the whole document. Counting leaf /Page
    # objects directly sidesteps that and matches pdfinfo's page count.
    leaf_pages = re.findall(rb"/Type\s*/Page(?!s)", data)
    if not leaf_pages:
        raise RuntimeError("Could not find any page objects in the rendered PDF.")
    return len(leaf_pages)


def try_settings(base_html: str, in_place_path: Path, body_pt: float, fill: float,
                  margin_in: float, side_margin_in: float, chrome: str,
                  tmp_dir: Path, keep_temp: bool, paper: str = "A4",
                  body_font: str | None = None, title_font: str | None = None) -> int:
    style = build_style_block(body_pt, fill, margin_in, side_margin_in, paper,
                              body_font, title_font)
    html = apply_style(base_html, style)
    in_place_path.write_text(html, encoding="utf-8")
    return render_page_count(in_place_path, chrome, tmp_dir, keep_temp)


def max_fill_that_fits(base_html, probe_path, body_pt, margin_in, side_margin_in,
                        max_pages, chrome, tmp_dir, keep_temp, paper="A4",
                        body_font=None, title_font=None, iterations=10):
    """Binary-search the largest fill in [0,1] with page_count <= max_pages.
    Returns (fill, page_count) or None if even fill=0 doesn't fit."""
    pages_at_0 = try_settings(base_html, probe_path, body_pt, 0.0, margin_in,
                               side_margin_in, chrome, tmp_dir, keep_temp, paper,
                               body_font, title_font)
    if pages_at_0 > max_pages:
        return None
    lo, hi = 0.0, 1.0
    best_fill, best_pages = 0.0, pages_at_0
    for _ in range(iterations):
        mid = (lo + hi) / 2
        pages = try_settings(base_html, probe_path, body_pt, mid, margin_in,
                              side_margin_in, chrome, tmp_dir, keep_temp, paper,
                              body_font, title_font)
        if pages <= max_pages:
            best_fill, best_pages = mid, pages
            lo = mid
        else:
            hi = mid
    return best_fill, best_pages


def optimise(input_path: Path, output: Path | None = None, max_pages: int = 1,
             target_pt: float = 11.0, min_pt: float = 10.0, margin_in: float = 0.75,
             side_margin_in: float = 0.75, chrome: str | None = None,
             keep_temp: bool = False, paper: str = "A4",
             body_font: str | None = None, title_font: str | None = None) -> dict:
    """Fit a CV HTML file into max_pages and write the result.

    Returns a dict: {ok, output, font_pt, fill, pages, warning}. ok=False means
    the content did not fit even at min_pt; the file is still written (tightest
    possible) and "pages" says how many it actually needs.
    """
    # Both typography warnings live here rather than in main(), because
    # this is where the floors are applied: every caller then reports them
    # identically, instead of cv_build.py quietly accepting settings that
    # cv_optimiser.py would have queried.
    if min_pt < 10.0:
        print(f"WARNING: a {min_pt}pt floor is below the 10pt professional minimum for "
              f"printed body text. Proceeding anyway, but this is not recommended.",
              file=sys.stderr)
    if margin_in < 0.5 or side_margin_in < 0.5:
        print("WARNING: margins below 0.5in risk clipped text in ATS parsing and print "
              "trimming; clamping to 0.5in.", file=sys.stderr)
        margin_in, side_margin_in = max(margin_in, 0.5), max(side_margin_in, 0.5)

    chrome_bin = find_chrome(chrome)
    output = output or input_path.with_name(input_path.stem + ".optimised.html")
    base_html = strip_old_warning(input_path.read_text(encoding="utf-8"))
    # cv_styles.css is loaded by a relative <link>, so the probe file must
    # live alongside it (same directory as the input).
    probe_path = input_path.with_name("._cv_optimiser_probe.html")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            font_pt = target_pt
            solution = None  # (font_pt, fill, pages)
            while font_pt >= min_pt - 1e-9:
                result = max_fill_that_fits(
                    base_html, probe_path, font_pt, margin_in, side_margin_in,
                    max_pages, chrome_bin, tmp_dir, keep_temp, paper,
                    body_font, title_font,
                )
                if result is not None:
                    fill, pages = result
                    solution = (font_pt, fill, pages)
                    break
                font_pt = round(font_pt - 0.5, 2)

            if solution is None:
                # Even min_pt with the tightest layout doesn't fit. Report how
                # many pages it actually needs, and write that best-effort version.
                needed = try_settings(
                    base_html, probe_path, min_pt, 0.0, margin_in,
                    side_margin_in, chrome_bin, tmp_dir, keep_temp, paper,
                    body_font, title_font,
                )
                html = apply_style(base_html, build_style_block(min_pt, 0.0, margin_in, side_margin_in, paper,
                                                          body_font, title_font))
                warning = (
                    f"max-pages {max_pages} is too small for this content even at the minimum "
                    f"professional body font size ({min_pt}pt / {round(min_pt * PT_TO_PX, 1)}px) "
                    f"with the tightest layout this script allows. At {min_pt}pt it actually needs "
                    f"{needed} page(s). Raise max-pages to at least {needed}, or trim content."
                )
                html = html.replace("<head>", f"<head>\n<!-- CV-OPTIMIZER WARNING: {warning} -->", 1)
                output.write_text(html, encoding="utf-8")
                return dict(ok=False, output=output, font_pt=min_pt, fill=0.0,
                            pages=needed, warning=warning)

            font_pt, fill, pages = solution
            html = apply_style(base_html, build_style_block(font_pt, fill, margin_in, side_margin_in, paper,
                                                      body_font, title_font))
            output.write_text(html, encoding="utf-8")
            return dict(ok=True, output=output, font_pt=font_pt, fill=fill,
                        pages=pages, warning=None)
    finally:
        probe_path.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path, help="CV HTML file to optimise")
    ap.add_argument("--max-pages", type=int, default=1, help="Maximum pages allowed (default: 1)")
    ap.add_argument("--output", type=Path, default=None, help="Output path (default: INPUT.optimised.html)")
    ap.add_argument("--target-pt", type=float, default=11.0, help="Preferred body font size in pt (default: 11)")
    ap.add_argument("--min-pt", type=float, default=10.0, help="Hard floor for body font size in pt (default: 10; professional minimum)")
    ap.add_argument("--margin-in", type=float, default=0.75, help="Top/bottom page margin, inches (default: 0.75)")
    ap.add_argument("--side-margin-in", type=float, default=0.75, help="Left/right page margin, inches (default: 0.75)")
    ap.add_argument("--paper", default="A4", help="Paper size: A4 (default, UK) or letter (US)")
    ap.add_argument("--body-font", default=None,
                    help="Body font: a shortcut (helvetica, arial, georgia, times, system, or one added by cv_addfont.py) or a CSS font-family list. Default: fonts.json, else helvetica")
    ap.add_argument("--title-font", default=None,
                    help="Font for the name at the top; same choices as --body-font. Default: fonts.json, else helvetica")
    ap.add_argument("--chrome", default=None, help="Path to Chrome/Chromium binary (auto-detected if omitted)")
    ap.add_argument("--keep-temp", action="store_true", help="Keep intermediate PDFs for inspection")
    ap.add_argument("--no-log", action="store_true", help="Don't touch the application log")
    ap.add_argument("--log-path", type=Path, default=None, help=f"Application log CSV (default: {LOG_FILENAME} beside the scripts)")
    ap.add_argument("--log-company", default=None, help="Fill the Company column for this CV")
    ap.add_argument("--log-role", default=None, help="Fill the Role column for this CV")
    ap.add_argument("--log-url", default=None, help="Fill the Job application link column for this CV")
    ap.add_argument("--log-deadline", default=None, help="Fill the Application deadline column for this CV")
    args = ap.parse_args()

    # The --min-pt and margin warnings live in optimise(), beside the
    # floors they describe, so every script that calls it says the same.

    result = optimise(
        args.input, args.output, args.max_pages, args.target_pt, args.min_pt,
        args.margin_in, args.side_margin_in, args.chrome, args.keep_temp, args.paper,
        args.body_font, args.title_font,
    )

    if result["ok"]:
        print(
            f"OK: body text {result['font_pt']}pt ({round(result['font_pt'] * PT_TO_PX, 1)}px), "
            f"fill {result['fill']:.2f} (0=tightest, 1=most spread out) -> {result['pages']} page(s), "
            f"within the {args.max_pages}-page budget.\nWrote: {result['output']}"
        )
    else:
        print(f"WARNING: {result['warning']}\nWrote best-effort tightest version to: {result['output']}",
              file=sys.stderr)

    if not args.no_log:
        log_path = args.log_path or default_log_path()
        action = update_application_log(
            log_path, log_key(result["output"]), company=args.log_company,
            role=args.log_role, url=args.log_url, deadline=args.log_deadline,
        )
        print(f"Application log {action}: {log_path}")

    sys.exit(0 if result["ok"] else 2)


if __name__ == "__main__":
    main()
