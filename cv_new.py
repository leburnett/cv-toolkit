#!/usr/bin/env python3
"""
cv_new.py — start a new application folder.

    python3 cv_new.py 2026-10_acme_data-scientist

Creates applications/<name>/ containing:

    cv.md             a copy of cv_template.md, ready to tailor
    cover-letter.md   a skeleton letter
    jobad.txt         paste the job ad here (used by cv_criteria_check.py)

Then:

    python3 cv_build.py applications/2026-10_acme_data-scientist --max-pages 2 --pdf
    python3 cv_letter.py applications/2026-10_acme_data-scientist
    python3 cv_criteria_check.py applications/2026-10_acme_data-scientist/cv.md \\
        --criteria applications/2026-10_acme_data-scientist/jobad.txt

Naming them YYYY-MM_company_role keeps the folder sorted and self-explanatory
a year later. This script only copies files; there's nothing magic about it,
and `mkdir` plus `cp cv_template.md .../cv.md` does the same job.
"""

import argparse
import shutil
import sys
from pathlib import Path

TOOLKIT_DIR = Path(__file__).resolve().parent
TEMPLATE = TOOLKIT_DIR / "cv_template.md"
APPLICATIONS = TOOLKIT_DIR / "applications"

LETTER_SKELETON = """<!--
Cover letter. Write it as you'd write an email: a blank line starts a new
paragraph, single newlines are kept (so the signature block stays on
separate lines). Render it with:

    python3 cv_letter.py {folder}

Keep it short, around 250-300 words. Say why this employer specifically, what
you bring, and anything they'd otherwise wonder about. If you're pasting into
an email rather than attaching, you don't need to render it at all.
-->

Dear [name, or just "Hi,"],

[Why you're writing, and why this employer specifically.]

[What you bring. Concrete, and not a restatement of the CV.]

[Anything they would otherwise wonder about, said plainly.]

[A closing offer: a trial shift, a call, whatever fits.]

Best wishes,

[Your name]
[phone] · [email]
"""

JOBAD_SKELETON = """# Paste the job ad here, one criterion per line.
# cv_criteria_check.py reads this to tell you which of their requirements
# your CV never mentions. Lines starting with # are treated as text too,
# so delete these three before using it.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", help="Folder name, e.g. 2026-10_acme_data-scientist")
    ap.add_argument("--force", action="store_true", help="Add missing files to an existing folder")
    args = ap.parse_args()

    if not TEMPLATE.exists():
        sys.exit(f"Can't find {TEMPLATE.name} in {TOOLKIT_DIR}.")

    folder = APPLICATIONS / args.name
    if folder.exists() and not args.force:
        sys.exit(f"{folder} already exists. Use --force to fill in missing files, "
                 f"or pick another name.")
    folder.mkdir(parents=True, exist_ok=True)

    created, skipped = [], []
    targets = [
        (folder / "cv.md", lambda p: shutil.copy2(TEMPLATE, p)),
        (folder / "cover-letter.md",
         lambda p: p.write_text(LETTER_SKELETON.format(folder=folder.as_posix()), encoding="utf-8")),
        (folder / "jobad.txt", lambda p: p.write_text(JOBAD_SKELETON, encoding="utf-8")),
    ]
    for path, make in targets:
        if path.exists():
            skipped.append(path.name)
            continue
        make(path)
        created.append(path.name)

    rel = folder.relative_to(TOOLKIT_DIR).as_posix()
    print(f"Created {rel}/: {', '.join(created) if created else 'nothing new'}")
    if skipped:
        print(f"Left alone (already there): {', '.join(skipped)}")
    print()
    print("Next:")
    print(f"  1. Tailor {rel}/cv.md — paste bullets from the master doc, cut the rest")
    print(f"  2. python3 cv_build.py {rel} --max-pages 2 --pdf")
    print(f"  3. python3 cv_criteria_check.py {rel}/cv.md --criteria {rel}/jobad.txt")
    print(f"  4. python3 cv_letter.py {rel}")


if __name__ == "__main__":
    main()
