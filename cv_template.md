<!--
CV TEMPLATE — copy this per application, then edit. Format rules and a
tailoring checklist are at the bottom of this file.

    python3 cv_new.py 2026-10_acme_data-analyst
    # edit applications/2026-10_acme_data-analyst/cv.md
    python3 cv_build.py applications/2026-10_acme_data-analyst --max-pages 2 --pdf

Fill in the facts that never change (contact details, education, anything
else stable) once, here in the template. Then each application is a copy you
trim and re-angle, rather than a blank page.

Pull your bullets from full_cv.md — both files are markdown, so a paste is
just a paste.
-->
---
name: Your Name
headline: Job Title | Focus Area | Specialism
phone: 01234 567890
email: you@example.com
website: yoursite.example
location: City, Country
---

## Profile {prose}

Two or three sentences: how long you have been doing this, what you are good at, and one concrete result. Lead with what you do and the difference you make, not with what you are looking for. Swap the closing sentence per application so it points at the sector you are applying to.

## Core Skills {skills}

Skill · Tool · Language · Method · Technique · Another skill

## Experience {entries}

### Job Title — a short phrase on what the role was about
org: Employer or Institution
dates: Mon YYYY – Mon YYYY
location: City, Country

- Achievement-focused bullet: what you did, how, and what came of it. Numbers help.
- The tool or method you owned, and the outcome it produced.
- Something that shows scale, pace or responsibility.
- Collaboration, leadership or cross-team impact.

### Previous Job Title
org: Employer or Institution
dates: Mon YYYY – Mon YYYY
location: City, Country

- Keep three or four bullets per role at most. Cutting is what gives a CV focus.
- Prefer a specific, checkable claim over a general one.

### Earlier roles — a grouping line for older or shorter jobs
org: Employer, Employer & Employer
dates: YYYY – YYYY
location: City, Country

Older or briefer roles do not each need their own block. One paragraph covering several of them keeps the page for the things that matter.

## Additional Experience {bullets}

- **Bold lead-in:** then the detail. Lead with what you did rather than the name of the organisation, so a skim reads as a list of things you can do.
- **Another:** volunteering, teaching, mentoring, committee work, side projects.

## Education {education}

### Degree, Subject (Grade)
org: University
dates: Mon YYYY – Mon YYYY
location: City, Country

### Earlier Degree, Subject (Grade)
org: University
dates: Mon YYYY – Mon YYYY
location: City, Country

## Publications {numbered}

Any summary line you want above the list — citation counts, an index, a total.

1. Author A, Author B, **Your Name**, et al. Title of the paper. *Journal*. YYYY;1(1):1–10.
2. **Your Name**, Author C. Another title. *Journal*. YYYY;2(2):20–30.

## Awards {lines}

- **Award or grant name**, awarding body (YYYY).
- **Another**, awarding body (YYYY).

## References {lines}

- References available on request.

## Format reference — not rendered {ignore}

Section kinds, written as `## Title {kind}`:

- prose — running paragraphs
- skills — one line of items separated by the middle dot, rendered italic
- entries — `###` blocks with org/dates/location metadata, bullets and/or prose
- education — same as entries, styled as education entries
- numbered — an optional intro line followed by a numbered list
- bullets — a plain list; bold lead-ins with double asterisks work well
- lines — one item per line, no bullet glyph
- ignore — parsed but left off the CV, like this section

Inside an `{entries}` section, `### Entry title` starts a role, and the lines
`org:`, `dates:` and `location:` give its metadata. Repeat that trio to attach
a second institution to the same entry.

Inline formatting: double asterisks for bold, single for italic, standard
markdown links. Everything else is escaped, so characters like the
greater-than sign and ampersand are safe to type literally.

To set a font or weight on a single phrase, use `[text]{.class}`:

- `[a phrase]{.light}` or `[a phrase]{.f-georgia .large}`
- Fonts: `.f-helvetica` `.f-arial` `.f-georgia` `.f-times` `.f-system`, plus
  one per font you add with `cv_addfont.py`
- Weights: `.light` `.regular` `.medium` `.bold`
- Size: `.small` `.large`   Caps: `.caps` `.nocaps`

To keep material in the file but off the CV, move it under an `{ignore}`
section or wrap it in an HTML comment.

Tailoring checklist, per application:

- Headline — use the advert's own language
- Profile — re-point the closing sentence at this employer
- Core Skills — lead with the tools the advert actually names
- Bullets — keep the three or four most relevant per role, cut the rest
- Sections — delete, or mark `{ignore}`, anything this employer will not care about

## Scratch — not rendered {ignore}

Park bullets you cut from this application but might want back.
