#!/usr/bin/env python3
"""
cv_letter.py — render a cover letter to a PDF that matches the CV.

    python3 cv_letter.py applications/2026-10_acme

Writes a .html and a .pdf beside the source, using the same typeface and
stylesheet as the CV so the two documents read as a matched pair.

INPUT FORMAT
------------
Plain markdown. Write the letter as you'd write it in an email:

    Dear Jane,

    First paragraph.

    Second paragraph.

    Best wishes,

    Your Name
    01234 567890 · you@example.com

Rules, all of them forgiving:

- A blank line starts a new paragraph.
- A single newline inside a paragraph becomes a line break, so a signature
  block or an address stays on separate lines.
- `**bold**`, `*italic*` and `[links](url)` work, and straight quotes become
  typographic ones — same as the CV.
- Anything inside `<!-- HTML comments -->` is dropped, so the instructions at
  the top of a letter file never reach the PDF.

An optional `---` YAML header can set any of:

    date: 16 September 2026     # omit for today's date, or "none" for no date
    name: Your Name             # adds a letterhead matching the CV's header
    phone: 01234 567890
    email: you@example.com
    location: London, UK
    recipient: |                # optional block above the greeting
      Jane Smith
      Acme Ltd

With no header at all, you get exactly what you wrote plus today's date.

WHY THIS ISN'T PART OF cv_build.py
-----------------------------------
A letter is prose, not a structured record. cv_build.py parses sections,
entries and metadata; cv_optimiser.py shrinks type to hit a page budget.
Neither is right here: a letter should be set at a comfortable reading size
and simply be short enough to fit. So this script uses fixed, generous
typography and warns if the letter runs over a page rather than shrinking it.

OPTIONS
-------
    --out PATH      HTML output path (default: alongside the source)
    --paper SIZE    A4 (default, UK) or letter (US)
    --pt SIZE       Body text size in points (default: 11)
    --margin-in IN  Page margin, inches (default: 1.0, the letter convention)
    --no-pdf        Write the HTML only
    --chrome PATH   Chrome/Chromium binary (auto-detected if omitted)
"""

import argparse
import datetime as _dt
import html as _html
import re
import sys
from pathlib import Path

import cv_build
import cv_optimiser

COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
FRONT_MATTER_RE = re.compile(r"\A\s*---\s*\n(.*?)\n---\s*\n", re.S)


def parse_letter(raw: str) -> tuple[dict, list[str]]:
    """Return (header, paragraphs). Header may be empty."""
    raw = COMMENT_RE.sub("", raw)
    header: dict = {}
    fm = FRONT_MATTER_RE.match(raw)
    if fm:
        import yaml
        header = yaml.safe_load(fm.group(1)) or {}
        if not isinstance(header, dict):
            sys.exit("The YAML header must be a set of key: value pairs.")
        raw = raw[fm.end():]
    # Blank line separates paragraphs; single newlines are kept as breaks.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    return header, paragraphs


# A short line carrying an email or a run of 5+ digits is contact detail
# (the signature block), not prose, so it gets the lighter weight. Kept
# deliberately narrow: prose lines are longer, and dates like "08:30 to
# 09:30" have no 5-digit run.
CONTACT_LINE_RE = re.compile(r"@|\d{5}")


def is_contact_line(line: str) -> bool:
    return len(line.strip()) <= 60 and bool(CONTACT_LINE_RE.search(line))


def render_paragraph(text: str) -> str:
    out = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        rendered = cv_build.inline(line)
        if is_contact_line(line):
            rendered = f'<span class="lmeta">{rendered}</span>'
        out.append(rendered)
    return "<p>" + "<br>".join(out) + "</p>"


def resolve_date(header: dict) -> str:
    value = header.get("date")
    if value is None:
        # Not strftime("%-d ..."): the no-padding flag is a Unix extension
        # and raises ValueError on Windows.
        today = _dt.date.today()
        return f"{today.day} {today:%B %Y}"
    if str(value).strip().lower() in ("none", "false", ""):
        return ""
    return str(value)


def letterhead(header: dict) -> str:
    """Optional name + contact block, styled like the CV header."""
    if not header.get("name"):
        return ""
    bits = [header[k] for k in ("phone", "email", "location") if header.get(k)]
    contact = (f'<div class="lcontact">{cv_build.inline(" · ".join(map(str, bits)))}</div>'
               if bits else "")
    return f'<h1 class="name">{cv_build.inline(str(header["name"]))}</h1>\n{contact}'


def render_html(header: dict, paragraphs: list[str], css_href: str,
                paper: str, pt: float, margin_in: float, title: str,
                body_font: str | None = None, title_font: str | None = None) -> str:
    body_px = round(pt * cv_optimiser.PT_TO_PX, 2)
    body_stack = cv_optimiser.font_stack(body_font or cv_optimiser.default_font("body"), "body")
    title_stack = cv_optimiser.font_stack(title_font or cv_optimiser.default_font("title"), "title")
    utility_css = cv_optimiser.font_utility_css()
    date = resolve_date(header)
    date_html = f'<div class="ldate">{cv_build.inline(date)}</div>' if date else ""
    recipient = header.get("recipient")
    recipient_html = (f'<div class="lrecipient">{render_paragraph(str(recipient).strip())}</div>'
                      if recipient else "")
    body = "\n".join(render_paragraph(p) for p in paragraphs)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{_html.escape(title, quote=False)}</title>
  <link rel="stylesheet" href="{_html.escape(css_href, quote=True)}">
  <style>
    /* Generated by cv_letter.py. A letter is set for comfortable reading,
       not squeezed to a page budget like the CV. */
    @page{{size:{paper};margin:{margin_in}in;}}
    html,body{{font-family:{body_stack};}}
    .letter{{font-family:{body_stack};font-size:{body_px}px;line-height:1.55;color:#2f2f2f;}}
    .letter p{{margin:0 0 {round(body_px * 0.85)}px;}}
    .name{{font-family:{title_stack};font-size:{round(body_px * 1.9)}px;margin:0 0 2px;}}
    .lcontact{{font-size:{round(body_px * 0.82, 1)}px;color:var(--muted);font-weight:300;
      margin:0 0 {round(body_px * 1.6)}px;}}
    .ldate{{color:var(--muted);font-weight:300;margin:0 0 {round(body_px * 1.6)}px;}}
    .lmeta{{font-weight:300;}}
    {utility_css}
    .lrecipient p{{margin:0 0 {round(body_px * 1.4)}px;}}
    @media print{{ .letter{{margin:0;}} }}
  </style>
</head>
<body>
<div class="page">
  <div class="letter">
{letterhead(header)}
{date_html}
{recipient_html}
{body}
  </div>
</div>
</body>
</html>
"""


def resolve_content(path: Path, default_name: str) -> Path:
    """Accept either a content file or an application folder.

    Each application lives in its own folder under applications/, so
    `cv_build.py applications/2026-10_acme` should just work and find cv.md
    inside it.
    """
    if not path.is_dir():
        return path
    candidate = path / default_name
    if candidate.exists():
        return candidate
    found = sorted(p for p in path.glob("*.md") if not p.name.startswith("."))
    if len(found) == 1:
        return found[0]
    if not found:
        sys.exit(f"{path} contains no .md file. Expected {default_name}.")
    names = ", ".join(p.name for p in found)
    sys.exit(f"{path} has several .md files ({names}). Expected {default_name}, "
             f"or name the file you want explicitly.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("letter", type=Path,
                    help="Cover letter .md, or an application folder containing cover-letter.md")
    ap.add_argument("--out", type=Path, default=None, help="HTML output path")
    ap.add_argument("--paper", default="A4", help="Paper size: A4 (default) or letter")
    ap.add_argument("--pt", type=float, default=11.0, help="Body text size in points (default: 11)")
    ap.add_argument("--margin-in", type=float, default=1.0, help="Page margin, inches (default: 1.0)")
    ap.add_argument("--body-font", default=None,
                    help="Body font: a shortcut (helvetica, arial, georgia, times, system, or one added by cv_addfont.py) or a CSS font-family list. Default: fonts.json, else helvetica")
    ap.add_argument("--title-font", default=None,
                    help="Font for the name at the top; same choices as --body-font. Default: fonts.json, else helvetica")
    ap.add_argument("--no-pdf", action="store_true", help="Write the HTML only")
    ap.add_argument("--chrome", default=None)
    args = ap.parse_args()

    if not args.letter.exists():
        sys.exit(f"No such file: {args.letter}")

    source = resolve_content(args.letter, "cover-letter.md")
    header, paragraphs = parse_letter(source.read_text(encoding="utf-8"))
    if not paragraphs:
        sys.exit(f"{source} has no letter text in it (only comments or an empty header?).")

    out_html = args.out or source.with_suffix(".html")
    out_html.parent.mkdir(parents=True, exist_ok=True)

    css_href = cv_build.stylesheet_href(out_html)
    resolved = (out_html.resolve().parent / css_href) if not css_href.startswith("file:") else None
    if resolved is not None and not resolved.exists():
        sys.exit(f"Cannot find {cv_build.STYLESHEET} (looked for '{css_href}' relative to "
                 f"{out_html.parent}, and in {cv_build.TOOLKIT_DIR}).")

    title = header.get("title") or f"{header.get('name', 'Cover letter')} — cover letter"
    out_html.write_text(
        render_html(header, paragraphs, css_href, args.paper, args.pt, args.margin_in,
                    title, args.body_font, args.title_font),
        encoding="utf-8")
    print(f"Rendered: {out_html}")

    if args.no_pdf:
        return

    pdf_path = out_html.with_suffix(".pdf")
    cv_build.write_pdf(out_html, pdf_path, args.chrome)
    print(f"PDF: {pdf_path}")

    pages = cv_optimiser.count_pdf_pages(pdf_path.read_bytes())
    if pages > 1:
        print(f"WARNING: this letter runs to {pages} pages. A cover letter should be one. "
              f"Cut a paragraph, or drop --pt to 10.5.", file=sys.stderr)
    else:
        print(f"One page at {args.pt}pt on {args.paper}.")


if __name__ == "__main__":
    main()
