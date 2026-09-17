# Fonts

This folder is empty on purpose. The toolkit embeds no fonts, so there are no
licences to worry about and nothing large in the repository.

By default your CV uses whatever system sans-serif you have — Helvetica Neue
on a Mac, Arial or a close equivalent elsewhere. That is perfectly
respectable for a CV.

## Adding a font

```bash
python3 cv_addfont.py path/to/YourFont.ttf --as yourfont
python3 cv_build.py applications/your-application --title-font yourfont --pdf
```

`cv_addfont.py` checks that Chrome will accept the font, repairs it if it can,
embeds it in `cv_styles.css` as base64 so nothing needs installing
system-wide, and registers the shortcut in `fonts.json`.

Both the font files and `fonts.json` are git-ignored, so a font you embed
stays on your machine. If you want to share a font with the repository, check
its licence allows redistribution first — many free-download fonts are
re-conversions of commercial typefaces and do not.

## Always verify

Chrome silently refuses malformed fonts: it does not warn, it just falls
through to the next font in the stack, so a broken font can look like a
working one. After building, check what genuinely got embedded:

```bash
pdffonts applications/your-application/cv.pdf
```
