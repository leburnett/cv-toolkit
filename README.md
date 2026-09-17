# cv-toolkit

Write your CV content once in markdown. Generate a tailored, correctly-fitted
PDF per job application. Check it against the job advert. Keep a record of
what you sent where.

**Content lives in markdown; presentation is handled by the scripts.** You
never hand-edit HTML or nudge font sizes to make something fit on the page.

```bash
git clone https://github.com/leburnett/cv-toolkit.git
cd cv-toolkit
cp full_cv.example.md full_cv.md          # your store of everything
python3 cv_new.py 2026-10_acme_data-analyst
# edit applications/2026-10_acme_data-analyst/cv.md
python3 cv_build.py applications/2026-10_acme_data-analyst --max-pages 2 --pdf
```

Requirements: Python 3.10+, PyYAML (`pip install pyyaml`), and Google Chrome
or any Chromium build. Chrome is used headlessly to measure real page counts
and write PDFs, so the page fitting is measured rather than estimated.

---

## The idea

Most CV pain comes from keeping several near-identical documents in sync, and
from fighting the layout when one bullet too many pushes you onto a second
page. This splits those apart:

| File | What it holds |
|---|---|
| `full_cv.md` | Everything you have ever done, plus several phrasings of each. Grows forever, never sent anywhere. |
| `cv_template.md` | The facts that don't change — contact details, education — as the starting point for each application. |
| `applications/<name>/` | One folder per job: the tailored content, and the PDFs built from it. |

Tailoring an application becomes: copy the template, paste in the relevant
bullets from your full CV, delete the rest, build. The build works out the
type size and spacing for you.

---

## Workflow

### 1. Fill in your full CV, once

```bash
cp full_cv.example.md full_cv.md
```

Then keep adding to it, for good. A paper published, a tool learned, a better
way of phrasing something — append it and don't tidy. Holding three versions
of the same bullet is what makes step 3 quick.

`full_cv.md` is git-ignored, so your content stays on your machine even if you
fork this repository.

### 2. Put your stable facts in the template

Edit `cv_template.md` once: name, contact details, education, anything else
that won't change between applications. Every new application starts as a copy
of it, so you are trimming rather than filling in a blank form.

### 3. Start an application

```bash
python3 cv_new.py 2026-10_acme_data-analyst
```

That creates `applications/2026-10_acme_data-analyst/` holding `cv.md` (a copy
of the template), a `cover-letter.md` skeleton, and an empty `jobad.txt`.
Naming folders `YYYY-MM_company_role` keeps them sorted and self-explanatory a
year later.

### 4. Tailor it

Work down `cv.md`: re-point the headline and profile at this employer, lead
your skills with the tools the advert names, and **cut each role's bullets to
the three or four that matter here**. Cutting is what gives a CV focus.

Two things make cutting safe: mark a section `{ignore}` and it stays in the
file but off the CV, or wrap anything in an HTML comment. There's a `Scratch`
section at the bottom of the template for exactly this.

### 5. Build it

```bash
python3 cv_build.py applications/2026-10_acme_data-analyst --max-pages 2 --pdf
```

Markdown goes in; a styled, page-fitted HTML and PDF come out, and a row is
added to `application_log.csv`.

```
Rendered: applications/2026-10_acme_data-analyst/cv.html
Fitted: body 11.0pt, fill 0.68 -> 2 page(s) (budget 2).
PDF: applications/2026-10_acme_data-analyst/cv.pdf
```

`fill 0.68` means the spacing sits 68% of the way between tightest and most
spacious. The point is that it spreads the content to use the page properly
rather than leaving a half-empty last page.

You can record the job details at the same time:

```bash
python3 cv_build.py applications/2026-10_acme_data-analyst \
    --max-pages 2 --pdf \
    --log-company "Acme Ltd" --log-role "Data Analyst" \
    --log-url "https://acme.example/jobs/123" --log-deadline "2026-10-31"
```

### 6. Check it against the advert

Paste the advert's requirements into `jobad.txt` (or into the log's
`Necessary Criteria` cell), then:

```bash
python3 cv_criteria_check.py applications/2026-10_acme_data-analyst/cv.md \
    --criteria applications/2026-10_acme_data-analyst/jobad.txt
```

The useful part is the last block:

```
Terms the job asks for that your CV never uses
------------------------------------------------------------
aws, cloud, dashboards, docker, stakeholder
```

Those are your omissions. Some are real gaps. Others are things you have
genuinely done but forgot to mention — and the wording is often already
sitting in `full_cv.md`.

### 7. Write the cover letter

Write it as plain markdown, as you would an email. A blank line starts a
paragraph; single newlines are kept, so a signature block stays on separate
lines.

```bash
python3 cv_letter.py applications/2026-10_acme_data-analyst
```

That produces a PDF in the same typeface as the CV, so the pair look like a
set. If you are pasting into an email instead, skip this — the markdown is
already what you want.

### 8. Send the PDF, and record what happened

Send the PDF rather than the HTML: the HTML carries generated-by comments
that don't appear in the PDF but are visible to anyone who opens the file in
a text editor.

Then fill in `Outcome` and `Date of outcome` in `application_log.csv` as
things happen. It's ordinary CSV — open it in Excel, Numbers or Sheets.

---

## Page fitting, and what it won't do

`cv_build.py` hands off to `cv_optimiser.py`, which finds the largest body
text size that fits your page budget, then opens the spacing out to use the
space properly.

It will not go below **10pt body text** or **0.5in margins**. Those are the
floors below which a printed CV stops looking professional: 10–12pt is the
usual range with 11pt a sensible default, 1in margins are traditional and
0.5in is the accepted minimum for print and for applicant tracking systems.

If your content cannot fit within those floors, it says so rather than
shrinking the type:

```
WARNING: max-pages 1 is too small for this content even at the minimum
professional body font size (10.0pt / 13.3px)... At 10.0pt it actually needs
2 page(s). Raise max-pages to at least 2, or trim content.
```

That is the tool telling you to cut content or accept another page. It will
not quietly make your CV unreadable to hit a target.

Paper defaults to **A4**; pass `--paper letter` for US applications.

---

## Content file format

A `---` YAML header for your name and contact details, then one `##` heading
per section, each declaring how it should be rendered:

```markdown
---
name: Your Name
headline: Job Title | Focus Area
email: you@example.com
location: City, Country
---

## Profile {prose}

A paragraph.

## Experience {entries}

### Job Title — what the role was about
org: Employer
dates: Jan 2024 – Present
location: City, Country

- A bullet.
```

Section kinds: `prose`, `skills`, `entries`, `education`, `bullets`,
`numbered`, `lines`, `ignore`. Inside `{entries}`, each `###` takes `org:`,
`dates:` and `location:` lines — repeat that trio to attach a second
institution to one entry.

Inline: `**bold**`, `*italic*`, `[links](url)`. Everything else is escaped, so
`>150,000` and `&` are safe to type literally. Straight quotes become
typographic ones automatically.

To set a font or weight on a single phrase, use `[text]{.class}` — for
example `[a phrase]{.f-georgia .large}` or `[quieter text]{.light}`. Fonts,
weights (`.light` `.regular` `.medium` `.bold`), sizes (`.small` `.large`) and
capitalisation (`.caps` `.nocaps`) are available. An unrecognised class is
dropped with a warning rather than failing silently. Spans don't nest.

Markdown rather than JSON, deliberately: your full CV is markdown, so moving
content between the two needs no re-escaping. No `\"` around every italic
journal name, no whole file broken by one missing comma, and comments are
allowed so you can keep a bullet in the file but off the CV. `.json` and
`.yaml` content files are also accepted if you prefer them.

---

## Fonts

No fonts are embedded. Your CV uses the system sans-serif — Helvetica Neue on
a Mac, Arial or similar elsewhere — which is perfectly respectable.

To use something else:

```bash
python3 cv_addfont.py path/to/YourFont.ttf --as yourfont
python3 cv_build.py applications/2026-10_acme --title-font yourfont --pdf
```

`cv_addfont.py` checks Chrome will accept the font, repairs it if it can,
embeds it in `cv_styles.css` as base64 so nothing needs installing
system-wide, and registers the shortcut. Font files are git-ignored, so
anything you embed stays on your machine — check a font's licence before
sharing it in a repository.

**Always verify what embedded.** Chrome runs webfonts through the OpenType
Sanitiser and *silently* refuses malformed ones: it doesn't warn, it falls
through to the next font in the stack, so a broken font can look like a
working one. One font tested during development failed with
`maxp: Bad maxZones: 3` and rendered as Georgia while appearing to work. So:

```bash
pdffonts applications/2026-10_acme/cv.pdf
```

That lists what genuinely made it into the PDF. `cv_addfont.py` runs the same
check before embedding, and repairs the common breakages, but confirming the
final output costs nothing.

---

## The application log

`application_log.csv` columns, in order:

`Job application link` · `Company` · `Role` · `Application deadline` ·
**`Date CV created`** · **`CV file used`** · `Notes` · `Job role` ·
`Necessary Criteria` · `Desirable Criteria` · `Outcome` · `Date of outcome`

The two bold columns fill themselves on every build; the rest are yours.

Rows are keyed on the CV's path, so rebuilding the same CV updates that row
rather than duplicating it. Values you typed by hand are never overwritten,
extra columns you add yourself survive, and the file is written atomically so
an interrupted run can't leave it half-written. It is git-ignored: your
application history stays on your machine.

Don't leave it open in Excel while a build runs — Excel holding a stale copy
and re-saving it is the one way to lose an edit.

---

## The scripts

| Script | Does |
|---|---|
| `cv_new.py` | Creates an application folder from the template |
| `cv_build.py` | Content file → styled HTML → page-fitted → PDF → logged |
| `cv_optimiser.py` | The page-fitting step. Also works on a hand-written HTML CV |
| `cv_letter.py` | Renders a cover letter to a PDF matching the CV |
| `cv_criteria_check.py` | Reports which of a job's requirements your CV evidences |
| `cv_addfont.py` | Validates, repairs, embeds and registers a font |

Run any of them with `--help` for its full options.

---

## Troubleshooting

**"No YAML header found"** — the `---` block must come before the first `##`
section. Most often caused by an instruction comment above it containing a
literal `-->`, which ends the comment early.

**"Cannot find cv_styles.css"** — the build refuses rather than producing an
unstyled CV, because unstyled HTML renders at browser-default sizes and
silently becomes a twenty-page document. Keep the scripts and the stylesheet
together.

**A `.gitignore` that does nothing** — if you created it in TextEdit, use
Format → Make Plain Text. TextEdit otherwise saves `.gitignore.rtf`, which
git ignores completely.

---

## Licence

MIT — use it, change it, share it. See `LICENSE`.

Questions or suggestions: leburnett3@gmail.com
