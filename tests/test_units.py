"""Unit tests for the pure functions — no Chrome, no filesystem beyond tmp_path.

These run in well under a second, so they can be the thing you run constantly
while editing. The slower end-to-end tests live in test_endtoend.py.
"""

import csv
import datetime as _dt
import re
from pathlib import Path

import pytest

import cv_build
import cv_criteria_check as cc
import cv_letter
import cv_new
import cv_optimiser


# ---------------------------------------------------------------------------
# PDF page counting
# ---------------------------------------------------------------------------
class TestCountPdfPages:
    def test_counts_leaf_page_objects(self):
        data = b"/Type /Page ... /Type /Page ... /Type /Page"
        assert cv_optimiser.count_pdf_pages(data) == 3

    def test_ignores_the_pages_node(self):
        # /Type /Pages is the container, not a page. Counting it would
        # inflate every document by one per tree node.
        data = b"/Type /Pages /Count 2 /Type /Page /Type /Page"
        assert cv_optimiser.count_pdf_pages(data) == 2

    def test_ignores_a_subtree_count(self):
        """Regression: Chrome writes a hierarchical page tree for longer
        documents, with an internal /Pages node carrying its own /Count for
        its subtree. Reading the first /Count reported 2 for a 19-page PDF.
        """
        data = (b"/Type /Pages /Count 19 "
                + b"/Type /Pages /Count 2 /Type /Page /Type /Page "
                + b"/Type /Page " * 17)
        assert cv_optimiser.count_pdf_pages(data) == 19

    def test_tolerates_whitespace_variants(self):
        assert cv_optimiser.count_pdf_pages(b"/Type/Page /Type  /Page") == 2

    def test_raises_when_there_are_no_pages(self):
        with pytest.raises(RuntimeError, match="page objects"):
            cv_optimiser.count_pdf_pages(b"not a pdf at all")


# ---------------------------------------------------------------------------
# Application log
# ---------------------------------------------------------------------------
class TestLogKey:
    def test_path_inside_the_toolkit_is_relative(self, toolkit_dir):
        key = cv_optimiser.log_key(toolkit_dir / "applications" / "acme" / "cv.html")
        assert key == "applications/acme/cv.html"

    def test_path_outside_the_toolkit_falls_back_to_the_name(self, tmp_path):
        assert cv_optimiser.log_key(tmp_path / "cv.html") == "cv.html"

    def test_two_applications_do_not_collide(self, toolkit_dir):
        """Regression: keying on the bare filename meant every application's
        cv.html shared one row, so each build overwrote the last one."""
        a = cv_optimiser.log_key(toolkit_dir / "applications" / "acme" / "cv.html")
        b = cv_optimiser.log_key(toolkit_dir / "applications" / "globex" / "cv.html")
        assert a != b


class TestApplicationLog:
    def test_creates_a_log_with_the_standard_columns(self, tmp_path):
        log = tmp_path / "application_log.csv"
        action = cv_optimiser.update_application_log(log, "applications/a/cv.html")
        assert action == "created"
        rows = list(csv.DictReader(log.open(newline="", encoding="utf-8")))
        assert len(rows) == 1
        assert rows[0]["CV file used"] == "applications/a/cv.html"
        assert rows[0]["Date CV created"] == _dt.date.today().isoformat()
        for column in cv_optimiser.LOG_COLUMNS:
            assert column in rows[0]

    def test_rebuilding_updates_rather_than_duplicates(self, tmp_path):
        log = tmp_path / "log.csv"
        cv_optimiser.update_application_log(log, "applications/a/cv.html")
        action = cv_optimiser.update_application_log(log, "applications/a/cv.html")
        assert action == "updated"
        rows = list(csv.DictReader(log.open(newline="", encoding="utf-8")))
        assert len(rows) == 1

    def test_a_second_application_appends(self, tmp_path):
        log = tmp_path / "log.csv"
        cv_optimiser.update_application_log(log, "applications/a/cv.html")
        action = cv_optimiser.update_application_log(log, "applications/b/cv.html")
        assert action == "appended"
        rows = list(csv.DictReader(log.open(newline="", encoding="utf-8")))
        assert len(rows) == 2

    def test_hand_typed_values_are_never_overwritten(self, tmp_path):
        """The whole point of the log is that you annotate it by hand. A
        --log-company flag must not clobber what you typed."""
        log = tmp_path / "log.csv"
        cv_optimiser.update_application_log(log, "cv.html", company="Typed By Hand")
        cv_optimiser.update_application_log(log, "cv.html", company="From The Flag")
        rows = list(csv.DictReader(log.open(newline="", encoding="utf-8")))
        assert rows[0]["Company"] == "Typed By Hand"

    def test_a_flag_does_fill_an_empty_column(self, tmp_path):
        log = tmp_path / "log.csv"
        cv_optimiser.update_application_log(log, "cv.html")
        cv_optimiser.update_application_log(log, "cv.html", role="Data Analyst")
        rows = list(csv.DictReader(log.open(newline="", encoding="utf-8")))
        assert rows[0]["Role"] == "Data Analyst"

    def test_user_added_columns_and_notes_survive_a_rebuild(self, tmp_path):
        log = tmp_path / "log.csv"
        # newline="" so the embedded newline stays "\n" on Windows too;
        # write_text would translate it to "\r\n" and the assertion below
        # would then be testing Python's line-ending translation, not the
        # log's behaviour.
        with log.open("w", newline="", encoding="utf-8") as fh:
            fh.write("CV file used,Company,My Own Column\n"
                     'applications/a/cv.html,Acme,"a note\nover two lines"\n')
        cv_optimiser.update_application_log(log, "applications/a/cv.html")
        rows = list(csv.DictReader(log.open(newline="", encoding="utf-8")))
        assert rows[0]["My Own Column"] == "a note\nover two lines"
        assert rows[0]["Company"] == "Acme"
        assert rows[0]["Date CV created"]  # ours got added alongside

    def test_leaves_no_temporary_file_behind(self, tmp_path):
        log = tmp_path / "log.csv"
        cv_optimiser.update_application_log(log, "cv.html")
        assert list(tmp_path.iterdir()) == [log]

    def test_warns_when_a_spreadsheet_is_newer(self, tmp_path, capsys):
        log = tmp_path / "log.csv"
        cv_optimiser.update_application_log(log, "cv.html")
        numbers = tmp_path / "log.numbers"
        numbers.write_text("x", encoding="utf-8")
        import os
        future = log.stat().st_mtime + 100
        os.utime(numbers, (future, future))
        cv_optimiser.update_application_log(log, "cv.html")
        assert "log.numbers is newer" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Style block: page geometry and type scale
# ---------------------------------------------------------------------------
def _css_value(css: str, selector: str, prop: str) -> float:
    # Anchored to the start of a line so that asking for `li` doesn't match
    # the `ol.pubs li` rule, which carries a different font size.
    match = re.search(r"(?:^|\n)\s*" + re.escape(selector) + r"\{[^}]*"
                      + re.escape(prop) + r":([\d.]+)px", css)
    assert match, f"{prop} not found on {selector}"
    return float(match.group(1))


class TestStyleBlock:
    def test_paper_size_and_margins_reach_the_page_rule(self):
        css = cv_optimiser.build_style_block(11, 0.5, 0.75, 0.6, paper="A4")
        assert "@page{size:A4;margin:0.75in 0.6in;}" in css

    def test_us_letter_is_passed_through(self):
        css = cv_optimiser.build_style_block(11, 0.5, 1.0, 1.0, paper="letter")
        assert "size:letter" in css

    def test_type_scale_keeps_its_hierarchy(self):
        css = cv_optimiser.build_style_block(11, 0.5, 0.75, 0.75)
        body = _css_value(css, "li", "font-size")
        assert _css_value(css, ".name", "font-size") > _css_value(css, ".headline", "font-size")
        assert _css_value(css, ".headline", "font-size") > body

    def test_body_size_converts_points_to_px(self):
        css = cv_optimiser.build_style_block(12, 0.5, 0.75, 0.75)
        assert _css_value(css, "li", "font-size") == pytest.approx(12 * 96 / 72, abs=0.01)

    def test_higher_fill_spreads_the_content_out(self):
        """fill is the whole mechanism for using the page: 0 must be
        strictly tighter than 1, or the optimiser's binary search is
        searching over nothing."""
        tight = cv_optimiser.build_style_block(11, 0.0, 0.75, 0.75)
        loose = cv_optimiser.build_style_block(11, 1.0, 0.75, 0.75)
        assert (_css_value(loose, ".entry", "margin-bottom")
                > _css_value(tight, ".entry", "margin-bottom"))

    def test_records_its_settings_in_a_comment(self):
        css = cv_optimiser.build_style_block(10.5, 0.25, 0.75, 0.75)
        assert "body=10.5pt" in css and "fill=0.25" in css


def test_interp_is_linear():
    assert cv_optimiser.interp(0, 10, 0.0) == 0
    assert cv_optimiser.interp(0, 10, 1.0) == 10
    assert cv_optimiser.interp(2, 4, 0.5) == 3


class TestFontStack:
    def test_known_shortcut_resolves(self):
        assert "Helvetica Neue" in cv_optimiser.font_stack("helvetica")

    def test_a_css_list_passes_through_untouched(self):
        stack = "'My Font', serif"
        assert cv_optimiser.font_stack(stack) == stack

    def test_unknown_shortcut_warns(self, capsys):
        cv_optimiser._font_warned.clear()
        cv_optimiser.font_stack("garamnod")  # deliberate typo
        assert "not a known font shortcut" in capsys.readouterr().err

    def test_every_builtin_shortcut_is_a_system_font(self):
        """Built-ins must not need embedding, or a fresh clone silently
        renders in a fallback font nobody chose."""
        for name in cv_optimiser.FONT_STACKS:
            first = cv_optimiser.FONT_STACKS[name].split(",")[0].strip().strip("'")
            assert first.lower() in cv_optimiser.SYSTEM_FAMILIES, name


# ---------------------------------------------------------------------------
# Inline markdown
# ---------------------------------------------------------------------------
class TestInline:
    def test_escapes_html(self):
        assert cv_build.inline("a < b & c") == "a &lt; b &amp; c"

    def test_bold_and_italic(self):
        assert cv_build.inline("**bold**") == "<b>bold</b>"
        assert cv_build.inline("*italic*") == "<i>italic</i>"

    def test_links(self):
        assert cv_build.inline("[Label](https://example.com)") == (
            '<a href="https://example.com">Label</a>')

    def test_smart_quotes(self):
        assert cv_build.inline('He said "hi"') == "He said “hi”"
        assert cv_build.inline("don't") == "don’t"

    def test_a_url_is_not_mangled_by_the_quote_pass(self):
        """Links are stashed before smart quotes run, so a straight quote in
        a URL stays straight (HTML-escaped) rather than becoming a curly one
        the server would never recognise."""
        out = cv_build.inline("[x](https://example.com/a'b)")
        assert "&#x27;" in out
        assert "’" not in out

    def test_known_span_class_is_applied(self):
        assert cv_build.inline("[Name]{.bold}") == '<span class="bold">Name</span>'

    def test_unknown_span_class_is_dropped_with_a_warning(self, capsys):
        cv_build._span_warned.clear()
        assert cv_build.inline("[Name]{.nonsense}") == "Name"
        assert "unknown span class" in capsys.readouterr().err

    def test_font_classes_track_the_registry(self):
        for name in cv_optimiser.all_font_stacks():
            assert f"f-{name}" in cv_build.known_span_classes()


# ---------------------------------------------------------------------------
# Content parsing
# ---------------------------------------------------------------------------
class TestParseMarkdown:
    def test_reads_the_header_and_sections(self):
        parsed = cv_build.parse_markdown(
            "---\nname: A Person\nemail: a@example.com\n---\n\n"
            "## Profile {prose}\n\nSome words.\n")
        assert parsed["header"]["name"] == "A Person"
        assert parsed["sections"][0]["title"] == "Profile"
        assert parsed["sections"][0]["text"] == "Some words."

    def test_missing_header_exits_with_an_explanation(self):
        """Regression: the template's own instruction comment once contained
        a literal '-->', which ended the comment early and displaced the
        header. The failure must say so, not render 'YOUR NAME'."""
        with pytest.raises(SystemExit) as exc:
            cv_build.parse_markdown("## Profile\n\nwords\n")
        assert "No YAML header" in str(exc.value)

    def test_header_without_a_name_exits(self):
        with pytest.raises(SystemExit) as exc:
            cv_build.parse_markdown("---\nemail: a@example.com\n---\n\n## X\n\ny\n")
        assert "name" in str(exc.value)

    def test_comments_are_stripped(self):
        parsed = cv_build.parse_markdown(
            "<!-- instructions -->\n---\nname: A\n---\n\n## Profile\n\nwords\n")
        assert "instructions" not in parsed["sections"][0]["text"]

    def test_entry_meta_is_collected(self):
        parsed = cv_build.parse_markdown(
            "---\nname: A\n---\n\n## Experience {entries}\n\n"
            "### Job Title\norg: Acme\ndates: 2020 - 2021\nlocation: Bristol\n\n"
            "- Did a thing\n")
        entry = parsed["sections"][0]["entries"][0]
        assert entry["title"] == "Job Title"
        assert entry["meta"] == [{"org": "Acme", "dates": "2020 - 2021", "location": "Bristol"}]
        assert entry["items"] == ["Did a thing"]

    def test_a_second_org_starts_a_new_meta_row(self):
        parsed = cv_build.parse_markdown(
            "---\nname: A\n---\n\n## Education {entries}\n\n"
            "### BSc\norg: One University\ndates: 2015\norg: Two University\ndates: 2016\n")
        assert len(parsed["sections"][0]["entries"][0]["meta"]) == 2

    @pytest.mark.parametrize("title,body,expected", [
        ("Publications", "- A paper\n", "numbered"),
        ("Awards", "- A prize\n", "lines"),
        ("Outreach", "- Ran a workshop\n", "bullets"),
        ("Core Skills", "Python · SQL\n", "skills"),
        ("Profile", "A sentence.\n", "prose"),
    ])
    def test_section_kind_is_inferred(self, title, body, expected):
        parsed = cv_build.parse_markdown(f"---\nname: A\n---\n\n## {title}\n\n{body}")
        assert parsed["sections"][0]["kind"] == expected

    def test_an_explicit_kind_overrides_inference(self):
        parsed = cv_build.parse_markdown(
            "---\nname: A\n---\n\n## Publications {bullets}\n\n- A paper\n")
        assert parsed["sections"][0]["kind"] == "bullets"


def test_render_html_includes_the_name_and_stylesheet():
    parsed = cv_build.parse_markdown(
        "---\nname: A Person\nemail: a@example.com\n---\n\n## Profile\n\nwords\n")
    html = cv_build.render_html(parsed, "cv_styles.css")
    assert "A Person" in html
    assert 'href="cv_styles.css"' in html
    assert "mailto:a@example.com" in html


def _href_target(href: str, out: Path) -> Path:
    """Where a stylesheet href actually points.

    Usually a relative path. On Windows it can be a file:// URI instead:
    os.path.relpath refuses to relate two paths on different drives, and
    the repo and the temp directory often sit on different ones there.
    """
    if href.startswith("file:"):
        from urllib.parse import unquote, urlparse
        path = unquote(urlparse(href).path)
        return Path(path.lstrip("/") if re.match(r"/[A-Za-z]:", path) else path)
    return out.resolve().parent / href


class TestStylesheetHref:
    def test_resolves_back_to_the_real_stylesheet(self, tmp_path, toolkit_dir):
        """Regression: a CV built into applications/ used a bare relative
        href, lost all styling, and silently rendered as a 20-page CV."""
        out = tmp_path / "deep" / "cv.html"
        href = cv_build.stylesheet_href(out)
        assert _href_target(href, out).resolve() == (toolkit_dir / "cv_styles.css")

    def test_a_sibling_output_gets_a_bare_name(self, toolkit_dir):
        assert cv_build.stylesheet_href(toolkit_dir / "cv.html") == "cv_styles.css"


# ---------------------------------------------------------------------------
# Cover letters
# ---------------------------------------------------------------------------
class TestLetter:
    def test_blank_lines_separate_paragraphs(self):
        _, paragraphs = cv_letter.parse_letter("Dear Jane,\n\nOne.\n\nTwo.\n")
        assert paragraphs == ["Dear Jane,", "One.", "Two."]

    def test_single_newlines_become_breaks(self):
        html = cv_letter.render_paragraph("Your Name\n01234 567890")
        assert html.count("<br>") == 1

    def test_yaml_header_is_read_and_removed(self):
        header, paragraphs = cv_letter.parse_letter(
            "---\nname: A Person\ndate: 1 January 2026\n---\n\nDear Jane,\n")
        assert header["name"] == "A Person"
        assert paragraphs == ["Dear Jane,"]

    def test_comments_never_reach_the_letter(self):
        _, paragraphs = cv_letter.parse_letter("<!-- how to write this -->\n\nDear Jane,\n")
        assert paragraphs == ["Dear Jane,"]

    def test_date_defaults_to_today_without_a_platform_specific_format(self):
        """Regression: strftime('%-d') is a Unix extension and raises
        ValueError on Windows."""
        today = _dt.date.today()
        assert cv_letter.resolve_date({}) == f"{today.day} {today:%B %Y}"

    def test_date_can_be_suppressed(self):
        assert cv_letter.resolve_date({"date": "none"}) == ""

    @pytest.mark.parametrize("line,expected", [
        ("01234 567890 · you@example.com", True),
        ("you@example.com", True),
        ("I spent five years building data pipelines for a research group.", False),
        ("The shift runs 08:30 to 09:30 each day.", False),
    ])
    def test_contact_lines_are_detected(self, line, expected):
        assert cv_letter.is_contact_line(line) is expected


# ---------------------------------------------------------------------------
# New application folders
# ---------------------------------------------------------------------------
class TestNaming:
    @pytest.mark.parametrize("raw,expected", [
        ("Acme Ltd & Co.", "acme-ltd-co"),
        ("  Spaces  Everywhere  ", "spaces-everywhere"),
        ("Data Scientist (Senior)", "data-scientist-senior"),
        ("", ""),
    ])
    def test_slugify(self, raw, expected):
        assert cv_new.slugify(raw) == expected

    def test_suggest_name_uses_the_dated_convention(self):
        name = cv_new.suggest_name("Acme Ltd", "Data Analyst")
        assert name == f"{_dt.date.today():%Y-%m}_acme-ltd_data-analyst"

    def test_role_is_optional(self):
        name = cv_new.suggest_name("Acme Ltd", "")
        assert name == f"{_dt.date.today():%Y-%m}_acme-ltd"


# ---------------------------------------------------------------------------
# Criteria checking
# ---------------------------------------------------------------------------
class TestCriteria:
    def test_tokens_lowercases_and_splits(self):
        assert cc.tokens("Python, SQL and R") == ["python", "sql", "and", "r"]

    def test_tokens_keeps_language_names_intact(self):
        assert cc.tokens("C++ and C#") == ["c++", "and", "c#"]

    def test_content_terms_drops_filler(self):
        terms = cc.content_terms("Strong experience with Python and SQL")
        assert terms == ["python", "sql"]

    def test_exact_match_reports_no_substitute(self):
        exact, by_prefix, _ = cc.build_index("python and sql", 5)
        assert cc.covered("python", exact, by_prefix, 5) == ""

    def test_absent_term_returns_none(self):
        exact, by_prefix, _ = cc.build_index("python and sql", 5)
        assert cc.covered("rust", exact, by_prefix, 5) is None

    def test_loose_prefix_match_names_the_word_it_matched(self):
        """At 5 characters 'complex' matches 'complete'. The tool must show
        the word it actually found so you can judge it, not just tick."""
        exact, by_prefix, _ = cc.build_index("completed the work", 5)
        assert cc.covered("complex", exact, by_prefix, 5) == "completed"

    def test_stemming_still_matches_genuine_roots(self):
        exact, by_prefix, _ = cc.build_index("analysing timeseries", 5)
        assert cc.covered("analysis", exact, by_prefix, 5) == "analysing"

    @pytest.mark.parametrize("blob,expected", [
        ("- Python\n- SQL", ["Python", "SQL"]),
        ("Python; SQL; Bash", ["Python", "SQL", "Bash"]),
        ("1. Python\n2. SQL", ["Python", "SQL"]),
        ("• Python\n• SQL", ["Python", "SQL"]),
        ("Writes Python. Knows SQL well.", ["Writes Python.", "Knows SQL well."]),
    ])
    def test_split_criteria_handles_common_job_ad_shapes(self, blob, expected):
        assert cc.split_criteria(blob) == expected

    def test_criteria_shorter_than_three_characters_are_dropped(self):
        """Documents current behaviour: the length filter removes numbering
        debris, but it also drops one- and two-letter skills such as R and
        Go, which a job ad may genuinely list on their own."""
        assert cc.split_criteria("- R\n- Go\n- Python") == ["Python"]

    def test_ignored_sections_are_not_counted_as_cv_content(self):
        text = cc.text_from_markdown(
            "---\nname: A\n---\n\n## Skills\n\nPython\n\n"
            "## Parked {ignore}\n\nHaskell\n")
        assert "Python" in text
        assert "Haskell" not in text

    def test_html_tags_are_stripped(self):
        assert "Python" in cc.text_from_html("<p>Python</p><style>p{color:red}</style>")
        assert "color" not in cc.text_from_html("<p>Python</p><style>p{color:red}</style>")
