#!/usr/bin/env python3
"""
cv_criteria_check.py — which job criteria does a CV actually evidence?

    python3 cv_criteria_check.py applications/2026-10_acme.md
    python3 cv_criteria_check.py --cv 2026-10_acme.html --company "Acme Biotech"
    python3 cv_criteria_check.py applications/2026-10_acme.md --criteria jobad.txt

Reads the "Necessary Criteria" / "Desirable Criteria" (and optionally
"Job role") cells you pasted into application_log.csv, then reports which of
their meaningful terms appear anywhere in the CV, and which never do.

It is a spellcheck for coverage, not a judgement of fit. It cannot tell
whether a bullet *demonstrates* a criterion convincingly, only whether the
vocabulary is present at all. A "missing" term may be a genuine gap worth
addressing, or wording you deliberately avoided; a "covered" term may appear
somewhere that doesn't really evidence the criterion. You decide — the point
is to stop you sending a CV that never once says "stakeholder" to a job ad
that says it four times.

HOW MATCHING WORKS
------------------
Criteria and CV are both reduced to lowercase word tokens, with job-ad filler
("strong", "demonstrable", "experience of", "ability to") dropped. A criterion
term counts as covered if some CV token shares its first --prefix characters
(default 5), so pipeline/pipelines, model/modelling, analysis/analyses/
analytical all match each other without needing a stemmer. Two- and
three-word phrases from the criteria are also checked literally.

Content read from a .md file skips any `{ignore}` sections, since parked
material isn't on the finished CV.
"""

import argparse
import csv
import html as _html
import re
import sys
from pathlib import Path

DEFAULT_PREFIX = 5

# Job-ad filler. These words say nothing about the substance of a criterion,
# so flagging them as "missing" would be noise. Extend freely.
STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "with", "for", "on", "at",
    "by", "as", "is", "are", "be", "been", "being", "was", "were", "have",
    "has", "had", "will", "would", "can", "could", "should", "must", "may",
    "we", "you", "your", "our", "their", "they", "it", "its", "this", "that",
    "these", "those", "from", "into", "within", "across", "including", "such",
    "etc", "eg", "ie", "using", "use", "used", "able", "ability", "strong",
    "excellent", "good", "solid", "proven", "demonstrable", "demonstrated",
    "track", "record", "experience", "experienced", "knowledge", "familiarity",
    "understanding", "skills", "skill", "essential", "desirable", "required",
    "requirement", "requirements", "preferred", "plus", "work", "working",
    "working-knowledge", "role", "candidate", "candidates", "applicant",
    "applicants", "job", "position", "successful", "ideal", "highly", "well",
    "other", "others", "both", "all", "any", "more", "most", "least",
    "relevant", "appropriate", "effective", "effectively", "years", "year",
    "minimum", "desire", "willing", "via", "equivalent", "discipline",
    "disciplines", "practice", "practices", "apply", "applying", "applied",
    "build", "building", "built", "maintain", "maintaining", "develop",
    "developing", "deliver", "delivering", "support", "supporting", "environment",
    "environments", "team", "teams", "industry", "opportunity", "opportunities",
    "responsible", "responsibilities", "duties", "part", "day", "help", "new",
}

CRITERION_SPLIT = re.compile(r"(?:\r?\n|;|•|(?<=\.)\s+(?=[A-Z]))")
TOKEN_RE = re.compile(r"[a-z0-9+#.]+")
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
FRONT_MATTER_RE = re.compile(r"\A\s*---\s*\n.*?\n---\s*\n", re.S)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
IGNORE_SECTION_RE = re.compile(r"^##\s+.*\{ignore\}\s*$", re.I)
SECTION_RE = re.compile(r"^##\s+")


# ---------------------------------------------------------------------------
# Getting plain text out of a CV
# ---------------------------------------------------------------------------
def text_from_markdown(raw: str) -> str:
    raw = COMMENT_RE.sub(" ", raw)
    raw = FRONT_MATTER_RE.sub(" ", raw)
    kept, skipping = [], False
    for line in raw.splitlines():
        if SECTION_RE.match(line):
            skipping = bool(IGNORE_SECTION_RE.match(line))
        if not skipping:
            kept.append(line)
    text = "\n".join(kept)
    text = re.sub(r"[*_`#>]+", " ", text)                    # markdown syntax
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)      # links -> label
    return text


def text_from_html(raw: str) -> str:
    raw = SCRIPT_STYLE_RE.sub(" ", raw)
    raw = COMMENT_RE.sub(" ", raw)
    return _html.unescape(TAG_RE.sub(" ", raw))


def cv_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in (".md", ".markdown"):
        return text_from_markdown(raw)
    if suffix in (".html", ".htm"):
        return text_from_html(raw)
    if suffix == ".pdf":
        sys.exit("Point this at the .md or .html version, not the PDF "
                 "(reading PDFs would need an extra dependency).")
    return raw


# ---------------------------------------------------------------------------
# Tokens and matching
# ---------------------------------------------------------------------------
def tokens(text: str) -> list[str]:
    return [t.strip(".") for t in TOKEN_RE.findall(text.lower()) if t.strip(".")]


def content_terms(text: str) -> list[str]:
    """Meaningful terms from a criterion, in order, de-duplicated."""
    out, seen = [], set()
    for tok in tokens(text):
        if tok in STOPWORDS or len(tok) < 2 or tok.isdigit():
            continue
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def build_index(text: str, prefix: int) -> tuple[set[str], dict[str, str], str]:
    """exact token set, prefix -> shortest real CV word, and a flat string."""
    toks = tokens(text)
    exact = set(toks)
    by_prefix: dict[str, str] = {}
    for tok in toks:
        if len(tok) >= prefix:
            key = tok[:prefix]
            # Keep the shortest word for the prefix: it's the most likely
            # genuine root, and it's what gets shown to the reader.
            if key not in by_prefix or len(tok) < len(by_prefix[key]):
                by_prefix[key] = tok
    flat = " " + " ".join(toks) + " "
    return exact, by_prefix, flat


def covered(term: str, exact: set[str], by_prefix: dict[str, str], prefix: int):
    """Return None if absent, "" if exact, else the CV word that matched.

    Surfacing the matched word matters: at 5 characters, "complex" matches
    "complete". Showing it lets you spot that rather than trusting a tick.
    """
    if term in exact:
        return ""
    if len(term) >= prefix:
        hit = by_prefix.get(term[:prefix])
        if hit is not None:
            return hit
    return None


def phrases(text: str, sizes=(3, 2)) -> list[str]:
    toks = tokens(text)
    out = []
    for size in sizes:
        for i in range(len(toks) - size + 1):
            window = toks[i:i + size]
            if all(w in STOPWORDS for w in window):
                continue
            if window[0] in STOPWORDS or window[-1] in STOPWORDS:
                continue
            out.append(" ".join(window))
    return out


# ---------------------------------------------------------------------------
# Criteria sources
# ---------------------------------------------------------------------------
def split_criteria(blob: str) -> list[str]:
    items = []
    for chunk in CRITERION_SPLIT.split(blob or ""):
        chunk = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", chunk or "").strip()
        if len(chunk) > 2:
            items.append(chunk)
    return items


def criteria_from_log(log_path: Path, cv_name: str | None, company: str | None) -> dict:
    if not log_path.exists():
        sys.exit(f"No application log at {log_path}. Pass --criteria FILE instead.")
    with log_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        sys.exit(f"{log_path} has no rows yet. Pass --criteria FILE instead.")

    def matches(row):
        if company:
            return (row.get("Company") or "").strip().lower() == company.strip().lower()
        logged = (row.get("CV file used") or "").strip()
        if not logged:
            return False
        want = Path(cv_name or "")
        # Current format records a path relative to the toolkit, so cv.md and
        # cv.html in the same application folder both match that row.
        if Path(logged).with_suffix("") == want.with_suffix(""):
            return True
        # Rows written before applications had their own folders stored a bare
        # filename; fall back to comparing stems for those.
        return "/" not in logged and Path(logged).stem == want.stem

    found = [r for r in rows if matches(r)]
    if not found:
        wanted = f"company '{company}'" if company else f"CV file matching '{cv_name}'"
        sys.exit(
            f"No row in {log_path.name} for {wanted}.\n"
            f"Logged CVs: {', '.join(sorted({(r.get('CV file used') or '?') for r in rows}))}"
        )
    return found[-1]


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def assess(items: list[str], exact, by_prefix, flat, prefix: int) -> list[dict]:
    results = []
    for item in items:
        terms = content_terms(item)
        hits, misses, loose = [], [], []
        for term in terms:
            match = covered(term, exact, by_prefix, prefix)
            if match is None:
                misses.append(term)
            else:
                hits.append(term)
                if match:  # fuzzy, not exact — show what it actually matched
                    loose.append(f"{term}~{match}")
        matched_phrases = [p for p in phrases(item) if f" {p} " in flat]
        ratio = len(hits) / len(terms) if terms else 0.0
        if not terms:
            status = "skip"
        elif not misses:
            status = "covered"
        elif ratio >= 0.5:
            status = "partial"
        else:
            status = "weak"
        results.append(dict(text=item, status=status, hits=hits, misses=misses,
                            loose=loose, phrases=matched_phrases[:3], ratio=ratio))
    return results


MARK = {"covered": "[+]", "partial": "[~]", "weak": "[-]", "skip": "[ ]"}


def render_report(cv_path: Path, groups: dict, prefix: int) -> str:
    lines = [f"Criteria coverage for {cv_path.name}", "=" * 60, ""]
    never = {}
    for label, results in groups.items():
        if not results:
            continue
        counts = {k: sum(1 for r in results if r["status"] == k)
                  for k in ("covered", "partial", "weak")}
        lines.append(f"{label}  ({counts['covered']} covered, "
                     f"{counts['partial']} partial, {counts['weak']} barely covered)")
        lines.append("-" * 60)
        for r in results:
            if r["status"] == "skip":
                continue
            text = r["text"] if len(r["text"]) <= 90 else r["text"][:87] + "..."
            lines.append(f"{MARK[r['status']]} {text}")
            if r["phrases"]:
                lines.append(f"      phrase match: {', '.join(r['phrases'])}")
            if r["loose"]:
                lines.append(f"      loose match (check these): {', '.join(r['loose'])}")
            if r["misses"]:
                lines.append(f"      not in CV: {', '.join(r['misses'])}")
                for term in r["misses"]:
                    never.setdefault(term, 0)
                    never[term] += 1
        lines.append("")

    if never:
        ranked = sorted(never.items(), key=lambda kv: (-kv[1], kv[0]))
        lines.append("Terms the job asks for that your CV never uses")
        lines.append("-" * 60)
        lines.append(", ".join(t for t, _ in ranked))
        lines.append("")
        repeated = [t for t, n in ranked if n > 1]
        if repeated:
            lines.append("Asked for more than once (fix these first): "
                         + ", ".join(repeated))
            lines.append("")

    lines.append(f"Matching on first {prefix} characters per word. A term counted as")
    lines.append("covered still needs a bullet that genuinely evidences it.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cv", type=Path, nargs="?", help="CV content file (.md) or built CV (.html)")
    ap.add_argument("--cv", dest="cv_name", default=None,
                    help="Look the log row up by this CV filename instead (use with --company or alone)")
    ap.add_argument("--company", default=None, help="Look the log row up by Company instead")
    ap.add_argument("--criteria", type=Path, default=None,
                    help="Read criteria from a text file instead of the log (one per line)")
    ap.add_argument("--log-path", type=Path, default=None, help="Application log (default: application_log.csv beside the CV)")
    ap.add_argument("--include-job-role", action="store_true",
                    help="Also assess the pasted 'Job role' description, not just the criteria")
    ap.add_argument("--prefix", type=int, default=DEFAULT_PREFIX, help=f"Prefix length for fuzzy word matching (default: {DEFAULT_PREFIX})")
    ap.add_argument("--out", type=Path, default=None, help="Also write the report to this file")
    args = ap.parse_args()

    cv_path = args.cv
    if cv_path is None and args.cv_name:
        cv_path = Path(args.cv_name)
    if cv_path is None:
        sys.exit("Give the CV file to check, e.g. "
                 "`cv_criteria_check.py applications/2026-10_acme.md`.")
    if not cv_path.exists():
        sys.exit(f"No such file: {cv_path}")

    groups: dict[str, list[str]] = {}
    if args.criteria:
        groups["Criteria (from file)"] = split_criteria(args.criteria.read_text(encoding="utf-8"))
    else:
        log_path = args.log_path or cv_path.resolve().parent / "application_log.csv"
        if not log_path.exists():
            log_path = Path(__file__).resolve().parent / "application_log.csv"
        import cv_optimiser
        row = criteria_from_log(log_path, args.cv_name or cv_optimiser.log_key(cv_path),
                                args.company)
        groups["Necessary criteria"] = split_criteria(row.get("Necessary Criteria", ""))
        groups["Desirable criteria"] = split_criteria(row.get("Desirable Criteria", ""))
        if args.include_job_role:
            groups["Job role description"] = split_criteria(row.get("Job role", ""))
        if not any(groups.values()):
            company = row.get("Company") or "that row"
            sys.exit(f"No criteria recorded for {company} yet — paste the job ad's "
                     f"criteria into the 'Necessary Criteria' / 'Desirable Criteria' "
                     f"cells of {log_path.name} first, or use --criteria FILE.")

    exact, prefixes, flat = build_index(cv_text(cv_path), args.prefix)
    assessed = {label: assess(items, exact, prefixes, flat, args.prefix)
                for label, items in groups.items()}

    report = render_report(cv_path, assessed, args.prefix)
    print(report)
    if args.out:
        args.out.write_text(report + "\n", encoding="utf-8")
        print(f"\nWritten to {args.out}")


if __name__ == "__main__":
    main()
