#!/usr/bin/env python3
"""
cv_build.py — turn a CV content file into a finished, page-fitted CV.

    python3 cv_build.py my_application.md --max-pages 2 --pdf

One command does the whole chain:

    content file (.md / .json / .yaml)
        -> HTML (styled with cv_styles.css)
        -> fitted to your page budget by cv_optimiser.py
        -> optional PDF
        -> row recorded in application_log.csv

WHY MARKDOWN (and not JSON)
---------------------------
The intended workflow is "copy a bullet out of full_cv.md and paste it into
a per-job file". The full-CV store is markdown, so a markdown
template makes that paste an identity transform: no re-escaping, no quoting,
no worrying that an apostrophe or a colon or a ">150,000" will break the file.
JSON would need `\\"` around every italic journal name, forbids comments, and
fails the whole file on one stray comma.

JSON and YAML are still accepted (dispatch is on file extension) if you
prefer them — the parsed shape is identical. Only the ergonomics differ.

CONTENT FILE FORMAT (markdown)
------------------------------
A YAML header for the discrete header fields, then one `##` heading per
section. Each section declares how it should be rendered with a `{kind}`
annotation (or leave it off and the kind is inferred):

    ---
    name: Sam Rivera
    headline: Operations Coordinator | Logistics | Team Leadership
    email: sam@example.com
    location: Bristol, UK
    ---

    ## Profile {prose}

    One or more paragraphs of running text.

    ## Core Skills {skills}

    Rota planning · Stock control · Supplier liaison · Excel · SQL

    ## Experience {entries}

    ### Operations Coordinator — depot scheduling and supplier management
    org: Northwind Logistics
    dates: Mar 2021 – Present
    location: Bristol, UK

    - A bullet.
    - Another bullet.

    ## Additional Experience {bullets}

    - **Bold lead:** the rest of the bullet.

    ## Education {education}

    ### BSc Business Management (2:1)
    org: Example University
    dates: 2016 – 2019
    location: Leeds, UK

    ## Publications {numbered}

    Any summary line you want above the list.

    1. Author A, **Sam Rivera**, et al. Title of the paper.
       *Journal of Examples*. 2024;1(1):1-10.

    ## Awards {lines}

    - **Team of the Year**, Northwind Logistics (2023).

Section kinds:
    prose      running paragraphs (the Profile)
    skills     one line of `·`-separated items, rendered italic
    entries    `###` blocks with org/dates/location meta + bullets and/or prose
    education  same as entries, styled as education entries
    bullets    a `- ` list, `**bold leads**` supported
    numbered   an optional intro line (metrics) + a numbered list (publications)
    lines      each item on its own line (awards, references)
    ignore     parsed but left out of the CV — park unused material here

Inline formatting inside any text: `**bold**`, `*italic*`, `[text](url)`.
Everything else is escaped, so `>150,000` and `&` are safe to type literally.

To set a font or weight on one phrase, use `[text]{.class}`:

    Worked at [Acme Ltd]{.f-georgia}, with a note in [light type]{.light}.
    Several at once: [a phrase]{.f-georgia .large}

Available classes are generated from the font registry, so every font added
by cv_addfont.py gets one:

    .f-helvetica .f-arial .f-georgia .f-times .f-system    (fonts, plus
                                       one per font you add with cv_addfont.py)
    .light .regular .medium .bold                          (weights)
    .small .large                                          (size)
    .caps .nocaps                                          (capitalisation)

An unknown class is dropped with a warning rather than silently ignored.
Spans don't nest — `[outer [inner]{.light}]{.bold}` won't parse — so apply
one span per phrase.

Anything inside `<!-- HTML comments -->` is dropped, so you can comment out a
bullet for one application without deleting it.

An entry can carry more than one meta row (e.g. a degree held at two
institutions): just repeat the `org:`/`dates:`/`location:` trio.

OPTIONS
-------
    --max-pages N     page budget passed to cv_optimiser (default: 1)
    --pdf             also write a PDF next to the HTML
    --out PATH        HTML output path (default: <content stem>.html)
    --no-optimise     just render the HTML, skip the fitting step
    --no-log          don't touch application_log.csv
    plus the cv_optimiser passthroughs: --target-pt, --min-pt, --margin-in,
    --side-margin-in, --log-company, --log-role, --log-url, --log-deadline
"""

import argparse
import html as _html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import cv_optimiser

STYLESHEET = "cv_styles.css"
TOOLKIT_DIR = Path(__file__).resolve().parent


def stylesheet_href(out_path: Path) -> str:
    """Relative href from the output file to cv_styles.css.

    The stylesheet lives once, next to these scripts, but a CV can be written
    anywhere (typically applications/). Without this, a CV built into a
    subdirectory silently loses all styling — and an unstyled CV renders at
    browser-default sizes, which quietly turns into a 20-page "CV".
    """
    css = TOOLKIT_DIR / STYLESHEET
    if not css.exists():  # fall back to a sibling of the output file
        css = out_path.resolve().parent / STYLESHEET
    try:
        return os.path.relpath(css, out_path.resolve().parent)
    except ValueError:  # different drive on Windows; absolute is the best we can do
        return css.as_uri()

# Icons reused verbatim from the existing CV so rendered output is
# pixel-identical to the hand-built versions.
ICONS = {
    "phone": "M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1C10.6 21 3 13.4 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.2.2 2.4.6 3.6.1.4 0 .8-.3 1l-2.2 2.2z",
    "email": "M12 12.7 3 6.9V6c0-.6.4-1 1-1h16c.6 0 1 .4 1 1v.9l-9 5.8zm0 2.4 9-5.8V18c0 .6-.4 1-1 1H4c-.6 0-1-.4-1-1V9.3l9 5.8z",
    "website": "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm6.9 6h-2.6a15.3 15.3 0 0 0-1.3-3.3A8 8 0 0 1 18.9 8zM12 4c.8 1.1 1.4 2.5 1.8 4h-3.6c.4-1.5 1-2.9 1.8-4zM4.3 14a8 8 0 0 1 0-4h3a17.6 17.6 0 0 0 0 4zm.8 2h2.6c.3 1.2.8 2.3 1.3 3.3A8 8 0 0 1 5.1 16zM7.7 8H5.1a8 8 0 0 1 4-3.3C8.5 5.7 8 6.8 7.7 8zM12 20c-.8-1.1-1.4-2.5-1.8-4h3.6c-.4 1.5-1 2.9-1.8 4zm2.3-6H9.7a15.6 15.6 0 0 1 0-4h4.6a15.6 15.6 0 0 1 0 4zm.6 5.3c.5-1 1-2.1 1.3-3.3h2.6a8 8 0 0 1-3.9 3.3zM16.7 14a17.6 17.6 0 0 0 0-4h3a8 8 0 0 1 0 4z",
    "github": "M12 2a10 10 0 0 0-3.16 19.49c.5.09.68-.22.68-.48v-1.69c-2.78.6-3.37-1.34-3.37-1.34-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.61.07-.61 1 .07 1.53 1.03 1.53 1.03.89 1.53 2.34 1.09 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.65 0 0 .84-.27 2.75 1.02a9.56 9.56 0 0 1 5 0c1.91-1.29 2.75-1.02 2.75-1.02.55 1.38.2 2.4.1 2.65.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.69-4.57 4.94.36.31.68.92.68 1.85v2.74c0 .27.18.58.69.48A10 10 0 0 0 12 2z",
    "linkedin": "M4 3a2 2 0 1 1 0 4 2 2 0 0 1 0-4zM2 9h4v12H2V9zm6 0h3.8v1.9h.1c.5-1 1.8-2.2 3.7-2.2 4 0 4.7 2.6 4.7 6V21h-4v-5.6c0-1.3 0-3-1.9-3s-2.1 1.4-2.1 2.9V21H8V9z",
    "scholar": "M12 3 1 9l11 6 9-4.9V17h2V9L12 3zm0 9.5L4.8 9 12 5.5 19.2 9 12 12.5zM5 13.18v3.6c0 1.2 3.13 3.22 7 3.22s7-2.02 7-3.22v-3.6l-7 3.82-7-3.82z",
    "location": "M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z",
    "date": "M7 2v2H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2V2h-2v2H9V2H7zm12 7v10H5V9h14z",
}

# Header fields that become contact-row items, in this order if present.
CONTACT_FIELDS = ["phone", "email", "website", "github", "linkedin", "scholar", "orcid", "location"]
CONTACT_ICON = {"orcid": "website"}
NO_LINK = {"location", "phone"}

COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
FRONT_MATTER_RE = re.compile(r"\A\s*---\s*\n(.*?)\n---\s*\n", re.S)
HEADING_RE = re.compile(r"^(#{2,3})\s+(.*?)\s*(?:\{(\w+)\})?\s*$")
META_RE = re.compile(r"^(org|dates|location|title)\s*:\s*(.*)$", re.I)
LIST_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.*)$")


# ---------------------------------------------------------------------------
# Inline markdown -> HTML
# ---------------------------------------------------------------------------
# [text]{.class} sets a font or weight on one phrase. Only known classes are
# allowed through, so a stray brace in your prose can't inject markup and a
# typo shows up as a warning rather than silently doing nothing.
SPAN_RE = re.compile(r"\[([^\]\n]+)\]\{((?:\s*\.[A-Za-z0-9_-]+)+)\s*\}")
_span_warned: set[str] = set()


def known_span_classes() -> set[str]:
    classes = {f"f-{name}" for name in cv_optimiser.all_font_stacks()}
    classes |= set(cv_optimiser.WEIGHT_CLASSES)
    classes |= {"small", "large", "caps", "nocaps"}
    return classes


def _span(match: re.Match) -> str:
    text, raw = match.group(1), match.group(2)
    wanted = [c.lstrip(".") for c in raw.split()]
    allowed = known_span_classes()
    unknown = [c for c in wanted if c not in allowed]
    for c in unknown:
        if c not in _span_warned:
            _span_warned.add(c)
            print(f"WARNING: unknown span class '.{c}' — ignoring it. Known: "
                  f"{', '.join(sorted(allowed))}", file=sys.stderr)
    good = [c for c in wanted if c in allowed]
    if not good:
        return text
    return f'<span class="{" ".join(good)}">{text}</span>'


def smart_quotes(text: str) -> str:
    """Straight quotes -> typographic quotes, so pasted text matches the
    hand-set look of the original CV without you having to type “ ” ’."""
    # Opening quote after start-of-string, whitespace, or an opening bracket.
    text = re.sub(r'(^|[\s(\[{])"', r"\1“", text)
    text = re.sub(r'"', "”", text)              # every other " closes
    text = re.sub(r"(^|[\s(\[{])'(?=\w)", r"\1‘", text)
    text = re.sub(r"'", "’", text)               # the rest are apostrophes
    return text


def inline(text: str) -> str:
    """Escape HTML, then apply **bold**, *italic*, [text](url), smart quotes.

    Links are pulled out first so a URL can't be mangled by the italic or
    quote passes, then put back at the end.
    """
    out = _html.escape(text.strip(), quote=False)

    links: list[tuple[str, str]] = []

    def stash(match):
        links.append((match.group(1), match.group(2)))
        return f"\x00LINK{len(links) - 1}\x00"

    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", stash, out)
    out = smart_quotes(out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<i>\1</i>", out)
    out = SPAN_RE.sub(_span, out)
    for index, (label, href) in enumerate(links):
        anchor = f'<a href="{_html.escape(href, quote=True)}">{smart_quotes(label)}</a>'
        out = out.replace(f"\x00LINK{index}\x00", anchor)
    return out


# ---------------------------------------------------------------------------
# Parsing: markdown / json / yaml -> a common dict shape
#   {"header": {...}, "sections": [{"title", "kind", "text", "items", "entries"}]}
# ---------------------------------------------------------------------------
def infer_kind(section: dict) -> str:
    title = (section.get("title") or "").lower()
    if section.get("entries"):
        return "education" if "education" in title else "entries"
    if section.get("items"):
        if "publication" in title:
            return "numbered"
        if "award" in title or "funding" in title or "reference" in title:
            return "lines"
        return "bullets"
    text = section.get("text") or ""
    if "·" in text and "\n" not in text.strip():
        return "skills"
    return "prose"


def parse_markdown(raw: str) -> dict:
    raw = COMMENT_RE.sub("", raw)

    fm = FRONT_MATTER_RE.match(raw)
    if not fm:
        sys.exit(
            "No YAML header found. A content file must open with a '---' block "
            "giving at least 'name:', before the first '##' section, e.g.\n\n"
            "    ---\n    name: Your Name\n    email: you@example.com\n    ---\n\n"
            "If you have an instruction comment above it, check it doesn't contain "
            "a literal '-->' inside — that ends the comment early and pushes the "
            "header out of position."
        )
    import yaml  # stdlib-adjacent; only needed for the header block
    header = yaml.safe_load(fm.group(1)) or {}
    if not isinstance(header, dict) or not header.get("name"):
        sys.exit("The YAML header must include a 'name:' field.")
    raw = raw[fm.end():]

    sections: list[dict] = []
    section = None
    entry = None

    def flush_text(container, buffer):
        joined = " ".join(l.strip() for l in buffer if l.strip())
        if joined:
            container["text"] = (container.get("text", "") + " " + joined).strip()
        buffer.clear()

    buffer: list[str] = []
    for line in raw.splitlines():
        heading = HEADING_RE.match(line)
        if heading:
            hashes, title, kind = heading.groups()
            if len(hashes) == 2:
                if entry is not None and section is not None:
                    flush_text(entry, buffer)
                    entry = None
                elif section is not None:
                    flush_text(section, buffer)
                buffer.clear()
                section = {"title": title, "kind": kind, "text": "", "items": [], "entries": []}
                sections.append(section)
            else:  # ### — a new entry inside the current section
                if section is None:
                    section = {"title": "", "kind": None, "text": "", "items": [], "entries": []}
                    sections.append(section)
                if entry is not None:
                    flush_text(entry, buffer)
                buffer.clear()
                entry = {"title": title, "meta": [], "items": [], "text": ""}
                section["entries"].append(entry)
            continue

        if section is None:
            continue

        target = entry if entry is not None else section
        meta = META_RE.match(line) if entry is not None else None
        if meta:
            key, value = meta.group(1).lower(), meta.group(2).strip()
            if key == "title":
                entry["title"] = value
                continue
            # A new `org:` starts a new meta row, so an entry can list two
            # institutions (e.g. a degree with a study-abroad year).
            if key == "org" or not entry["meta"]:
                entry["meta"].append({})
            entry["meta"][-1][key] = value
            continue

        item = LIST_RE.match(line)
        if item:
            flush_text(target, buffer)
            target["items"].append(item.group(1).strip())
            continue

        if line.strip():
            buffer.append(line)
        else:
            flush_text(target, buffer)

    if entry is not None:
        flush_text(entry, buffer)
    elif section is not None:
        flush_text(section, buffer)

    for sec in sections:
        sec["kind"] = sec.get("kind") or infer_kind(sec)
    return {"header": header, "sections": sections}


def parse_structured(data: dict) -> dict:
    """Normalise a JSON/YAML document into the same shape as parse_markdown."""
    sections = []
    for sec in data.get("sections", []):
        norm = {
            "title": sec.get("title", ""),
            "kind": sec.get("kind"),
            "text": sec.get("text", "") or "",
            "items": list(sec.get("items", []) or []),
            "entries": [],
        }
        for ent in sec.get("entries", []) or []:
            meta = ent.get("meta")
            if meta is None:
                meta = [{k: ent[k] for k in ("org", "dates", "location") if ent.get(k)}]
            elif isinstance(meta, dict):
                meta = [meta]
            norm["entries"].append({
                "title": ent.get("title", ""),
                "meta": [m for m in meta if m],
                "items": list(ent.get("items", []) or []),
                "text": ent.get("text", "") or "",
            })
        norm["kind"] = norm.get("kind") or infer_kind(norm)
        sections.append(norm)
    return {"header": data.get("header", {}), "sections": sections}


def load_content(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in (".md", ".markdown", ".txt"):
        return parse_markdown(raw)
    if suffix == ".json":
        return parse_structured(json.loads(raw))
    if suffix in (".yaml", ".yml"):
        import yaml
        return parse_structured(yaml.safe_load(raw) or {})
    sys.exit(f"Don't know how to read '{path.suffix}'. Use .md, .json or .yaml.")


# ---------------------------------------------------------------------------
# Rendering -> HTML
# ---------------------------------------------------------------------------
def svg(icon: str) -> str:
    return f'<svg viewBox="0 0 24 24"><path d="{ICONS[icon]}"/></svg>'


def contact_row(header: dict) -> str:
    spans = []
    for field in CONTACT_FIELDS:
        value = header.get(field)
        if not value:
            continue
        icon = CONTACT_ICON.get(field, field)
        label = str(value).strip()
        if field in NO_LINK:
            body = _html.escape(label, quote=False)
        else:
            if field == "email":
                href = f"mailto:{label}"
            elif label.startswith(("http://", "https://")):
                href = label
            else:
                href = "https://" + label
            display = re.sub(r"^https?://", "", label).rstrip("/")
            # Long query-string URLs (Google Scholar) get a friendly label.
            if header.get(f"{field}_label"):
                display = str(header[f"{field}_label"])
            elif "?" in display:
                display = field.capitalize()
            body = f'<a href="{_html.escape(href, quote=True)}">{_html.escape(display, quote=False)}</a>'
        spans.append(f"    <span>{svg(icon)}{body}</span>")
    return "\n".join(spans)


def meta_row(meta: dict, org_class: str) -> str:
    bits = []
    if meta.get("org"):
        bits.append(f'<span class="{org_class}">{inline(meta["org"])}</span>')
    if meta.get("dates"):
        bits.append(f'<span class="bit">{svg("date")}{inline(meta["dates"])}</span>')
    if meta.get("location"):
        bits.append(f'<span class="bit">{svg("location")}{inline(meta["location"])}</span>')
    if not bits:
        return ""
    inner = "\n          ".join(bits)
    return f'        <div class="meta">\n          {inner}\n        </div>'


def render_entries(section: dict, education: bool = False) -> list[str]:
    out = []
    wrapper = "eduentry" if education else "entry"
    title_cls = "edutitle" if education else "role"
    org_cls = "uni" if education else "org"
    for ent in section["entries"]:
        parts = [f'      <div class="{wrapper}">']
        if ent.get("title"):
            title = inline(ent["title"])
            if education:
                # Education titles are bold up to the first parenthesis, so
                # so "(2:1)" or "(Distinction)" stays in normal weight.
                m = re.match(r"^(.*?)(\s*\(.*\))$", title)
                title = f"<b>{m.group(1)}</b>{m.group(2)}" if m else f"<b>{title}</b>"
            parts.append(f'        <div class="{title_cls}">{title}</div>')
        for meta in ent.get("meta", []):
            row = meta_row(meta, org_cls)
            if row:
                parts.append(row)
        if ent.get("items"):
            parts.append("        <ul>")
            parts += [f"          <li>{inline(i)}</li>" for i in ent["items"]]
            parts.append("        </ul>")
        if ent.get("text"):
            parts.append(f'        <div class="edesc">{inline(ent["text"])}</div>')
        parts.append("      </div>")
        out.append("\n".join(parts))
    return out


def render_section(section: dict) -> str:
    kind = section["kind"]
    if kind == "ignore":
        return ""
    parts = []
    if section.get("title"):
        parts.append(f'      <div class="sec">{inline(section["title"])}</div>')

    if kind == "prose":
        if section.get("text"):
            parts.append(f'      <p class="sum">{inline(section["text"])}</p>')
    elif kind == "skills":
        body = section.get("text") or " · ".join(section.get("items", []))
        parts.append(f'      <p class="sgroup"><i>{inline(body)}</i></p>')
    elif kind in ("entries", "education"):
        if section.get("text"):
            parts.append(f'      <p class="sum">{inline(section["text"])}</p>')
        parts += render_entries(section, education=(kind == "education"))
    elif kind == "bullets":
        if section.get("text"):
            parts.append(f'      <p class="sum">{inline(section["text"])}</p>')
        parts.append('      <ul class="list">')
        parts += [f"        <li>{inline(i)}</li>" for i in section.get("items", [])]
        parts.append("      </ul>")
    elif kind == "numbered":
        if section.get("text"):
            parts.append(f'      <div class="metrics">{inline(section["text"])}</div>')
        parts.append('      <ol class="pubs">')
        parts += [f"        <li>{inline(i)}</li>" for i in section.get("items", [])]
        parts.append("      </ol>")
    elif kind == "lines":
        for item in section.get("items", []):
            parts.append(f'      <div class="award">{inline(item)}</div>')
        if section.get("text"):
            parts.append(f'      <div class="award">{inline(section["text"])}</div>')
    else:
        sys.exit(f"Unknown section kind '{kind}' in section '{section.get('title')}'.")
    return "\n".join(p for p in parts if p)


def render_html(content: dict, css_href: str = STYLESHEET) -> str:
    header = content["header"]
    name = header.get("name", "Your Name")
    title = header.get("document_title") or f"{name} - CV"
    body = "\n\n".join(s for s in (render_section(sec) for sec in content["sections"]) if s)
    headline = (
        f'  <div class="headline">{inline(header["headline"]).replace("|", "&nbsp;|&nbsp;")}</div>\n'
        if header.get("headline") else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{_html.escape(str(title), quote=False)}</title>
  <link rel="stylesheet" href="{_html.escape(css_href, quote=True)}">
  <style>
    /* Placeholder — cv_optimiser.py replaces this block with fitted values. */
  </style>
</head>
<body>
<div class="page">

  <!-- ============================= HEADER ============================= -->
  <h1 class="name">{inline(str(name))}</h1>
{headline}  <div class="contact">
{contact_row(header)}
  </div>

  <div class="main">

{body}

  </div>
</div>
</body>
</html>
"""


def write_pdf(html_path: Path, pdf_path: Path, chrome: str | None = None) -> None:
    chrome_bin = cv_optimiser.find_chrome(chrome)
    subprocess.run(
        [chrome_bin, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()],
        capture_output=True, text=True, timeout=120,
    )
    if not pdf_path.exists():
        sys.exit(f"Chrome did not produce a PDF at {pdf_path}")


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
    ap.add_argument("content", type=Path,
                    help="Content file (.md/.json/.yaml), or an application folder containing cv.md")
    ap.add_argument("--out", type=Path, default=None, help="HTML output path (default: <content stem>.html)")
    ap.add_argument("--max-pages", type=int, default=1, help="Page budget (default: 1)")
    ap.add_argument("--pdf", action="store_true", help="Also write a PDF next to the HTML")
    ap.add_argument("--no-optimise", action="store_true", help="Render HTML only, skip page fitting")
    ap.add_argument("--target-pt", type=float, default=11.0)
    ap.add_argument("--min-pt", type=float, default=10.0)
    ap.add_argument("--margin-in", type=float, default=0.75)
    ap.add_argument("--side-margin-in", type=float, default=0.75)
    ap.add_argument("--paper", default="A4", help="Paper size: A4 (default, UK) or letter (US)")
    ap.add_argument("--body-font", default=None,
                    help="Body font: a shortcut (helvetica, arial, georgia, times, system, or one added by cv_addfont.py) or a CSS font-family list. Default: fonts.json, else helvetica")
    ap.add_argument("--title-font", default=None,
                    help="Font for the name at the top; same choices as --body-font. Default: fonts.json, else helvetica")
    ap.add_argument("--chrome", default=None)
    ap.add_argument("--no-log", action="store_true", help="Don't touch application_log.csv")
    ap.add_argument("--log-path", type=Path, default=None)
    ap.add_argument("--log-company", default=None)
    ap.add_argument("--log-role", default=None)
    ap.add_argument("--log-url", default=None)
    ap.add_argument("--log-deadline", default=None)
    args = ap.parse_args()

    source = resolve_content(args.content, "cv.md")
    content = load_content(source)
    out_html = args.out or source.with_suffix(".html")
    out_html.parent.mkdir(parents=True, exist_ok=True)

    css_href = stylesheet_href(out_html)
    resolved_css = (out_html.resolve().parent / css_href) if not css_href.startswith("file:") else None
    if resolved_css is not None and not resolved_css.exists():
        sys.exit(
            f"Cannot find {STYLESHEET} (looked for '{css_href}' relative to {out_html.parent}, "
            f"and in {TOOLKIT_DIR}). Without it the CV renders unstyled at browser-default "
            f"sizes, which silently balloons the page count — refusing to build."
        )

    out_html.write_text(render_html(content, css_href), encoding="utf-8")
    print(f"Rendered: {out_html}")

    final, ok = out_html, True
    if not args.no_optimise:
        result = cv_optimiser.optimise(
            out_html, out_html, args.max_pages, args.target_pt, args.min_pt,
            args.margin_in, args.side_margin_in, args.chrome, False, args.paper,
            args.body_font, args.title_font,
        )
        final, ok = result["output"], result["ok"]
        if ok:
            print(f"Fitted: body {result['font_pt']}pt, fill {result['fill']:.2f} "
                  f"-> {result['pages']} page(s) (budget {args.max_pages}).")
        else:
            print(f"WARNING: {result['warning']}", file=sys.stderr)

    if args.pdf:
        pdf_path = final.with_suffix(".pdf")
        write_pdf(final, pdf_path, args.chrome)
        print(f"PDF: {pdf_path}")

    if not args.no_log:
        log_path = args.log_path or cv_optimiser.default_log_path()
        action = cv_optimiser.update_application_log(
            log_path, cv_optimiser.log_key(final), company=args.log_company, role=args.log_role,
            url=args.log_url, deadline=args.log_deadline,
        )
        print(f"Application log {action}: {log_path}")

    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
