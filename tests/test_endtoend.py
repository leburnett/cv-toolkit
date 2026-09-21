"""End-to-end tests: markdown in, measured PDF out.

These invoke the scripts as real subprocesses, so they cover argument
parsing, exit codes and the Chrome round-trip — the parts a unit test can't
reach. They are much slower than the unit tests (each one drives a dozen or
so headless renders), so keep the number of them small and deliberate.

Every build writes into tmp_path and passes --no-log, so running the suite
never touches applications/ or application_log.csv in the working copy.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import cv_new
import cv_optimiser


def build(toolkit_dir: Path, content: Path, out: Path, *extra: str):
    """Run cv_build.py and return the CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(toolkit_dir / "cv_build.py"), str(content),
         "--out", str(out), "--no-log", *extra],
        capture_output=True, text=True, timeout=600,
    )


def pdfinfo_pages(pdf: Path):
    """An independent page count, when poppler is installed.

    Worth the trouble: it is the only check here that doesn't rely on the
    same count_pdf_pages() the tests are trying to verify.
    """
    if not shutil.which("pdfinfo"):
        return None
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    match = re.search(r"^Pages:\s+(\d+)", out, re.M)
    return int(match.group(1)) if match else None


def reported_pages(stdout: str) -> int:
    match = re.search(r"-> (\d+) page\(s\)", stdout)
    assert match, f"no page count in output:\n{stdout}"
    return int(match.group(1))


@pytest.fixture(scope="module")
def built(toolkit_dir, tmp_path_factory, chrome):
    """The shipped template, built once and asserted against several times.

    Each successful build costs ~11 headless renders (the fill binary
    search), so tests that can share a build do, rather than each paying
    that cost for one assertion.
    """
    # Deliberately nested: a CV built into a subdirectory is the case that
    # once lost its stylesheet and silently rendered as 20 pages.
    out = tmp_path_factory.mktemp("template") / "nested" / "cv.html"
    result = build(toolkit_dir, toolkit_dir / "cv_template.example.md", out,
                   "--max-pages", "1", "--pdf")
    assert result.returncode == 0, result.stderr
    return result, out


@pytest.mark.slow
class TestShippedTemplate:
    def test_builds_to_a_single_page_out_of_the_box(self, built):
        """The README promises the unedited template renders to one page.
        This is the check that the promise stays true."""
        result, out = built
        assert reported_pages(result.stdout) == 1

        pdf = out.with_suffix(".pdf")
        assert pdf.exists() and pdf.stat().st_size > 1000
        assert cv_optimiser.count_pdf_pages(pdf.read_bytes()) == 1
        if (independent := pdfinfo_pages(pdf)) is not None:
            assert independent == 1

    def test_the_fitted_html_carries_real_styling(self, built, toolkit_dir):
        """An unstyled CV silently balloons to ~20 pages, so verify the
        stylesheet link resolves and the optimiser's block replaced the
        placeholder."""
        _, out = built
        html = out.read_text(encoding="utf-8")
        assert "Placeholder" not in html
        assert "@page{size:A4" in html
        href = re.search(r'<link rel="stylesheet" href="([^"]+)"', html).group(1)
        assert (out.parent / href).resolve() == (toolkit_dir / "cv_styles.css")

    def test_body_type_stays_within_professional_limits(self, built):
        """10-12pt is the accepted range for printed body text; the whole
        point of the tool is that it never quietly breaks that."""
        _, out = built
        match = re.search(r"\n\s*li\{[^}]*font-size:([\d.]+)px", out.read_text(encoding="utf-8"))
        assert match, "no body font size in the fitted stylesheet"
        size_px = float(match.group(1))
        assert 10 <= size_px * 72 / 96 <= 12


@pytest.mark.slow
class TestPageBudget:
    def test_content_that_cannot_fit_warns_and_exits_2(self, toolkit_dir, tmp_path, chrome, cv_factory):
        """The behaviour that makes --max-pages trustworthy: rather than
        shrinking type below the professional floor, it says so, still
        writes a best-effort file, and exits non-zero so a script notices.

        Pinned to a single font size to keep the test to one descent pass.
        """
        content = cv_factory(entries=14, bullets=4)
        out = tmp_path / "big.html"
        result = build(toolkit_dir, content, out, "--max-pages", "1",
                       "--target-pt", "10", "--min-pt", "10")

        assert result.returncode == 2
        assert "too small for this content" in result.stderr
        assert out.exists(), "a best-effort file should still be written"
        assert "CV-OPTIMIZER WARNING" in out.read_text(encoding="utf-8")

    def test_a_larger_budget_lets_the_same_content_through(self, toolkit_dir, tmp_path, chrome, cv_factory):
        """Same content, bigger budget: max_pages is a real budget, not a
        hardcoded 1. Also the only test that exercises a genuinely
        multi-page PDF, which is where Chrome switches to a hierarchical
        page tree and where count_pdf_pages once reported 2 for 19 pages.
        """
        content = cv_factory(entries=14, bullets=4)
        out = tmp_path / "big.html"
        result = build(toolkit_dir, content, out, "--max-pages", "4", "--pdf",
                       "--target-pt", "10", "--min-pt", "10")

        assert result.returncode == 0, result.stderr
        pages = reported_pages(result.stdout)
        assert 1 < pages <= 4, "this content needs more than one page but must fit the budget"

        pdf = out.with_suffix(".pdf")
        assert cv_optimiser.count_pdf_pages(pdf.read_bytes()) == pages
        if (independent := pdfinfo_pages(pdf)) is not None:
            assert independent == pages, "count_pdf_pages disagrees with pdfinfo"

    def test_page_geometry_flags_reach_the_page_rule(self, toolkit_dir, tmp_path, chrome):
        """US Letter and the 0.5in margin floor in one build.

        The floor is enforced inside optimise(), and so is the warning
        about it — so cv_build.py reports the clamp rather than quietly
        ignoring the margin you asked for.
        """
        out = tmp_path / "cv.html"
        result = build(toolkit_dir, toolkit_dir / "cv_template.example.md", out, "--max-pages", "1",
                       "--paper", "letter", "--margin-in", "0.1", "--side-margin-in", "0.1")
        assert result.returncode == 0, result.stderr
        assert "@page{size:letter;margin:0.5in 0.5in;}" in out.read_text(encoding="utf-8")
        assert "clamping to 0.5in" in result.stderr

    def test_typography_warnings_are_printed_exactly_once(self, toolkit_dir, tmp_path,
                                                           chrome, cv_factory):
        """cv_optimiser.py used to print its own copies of these warnings.
        Now that optimise() owns them, running the fitter directly must
        still say each once — not twice, and not zero times."""
        html = tmp_path / "cv.html"
        prepared = build(toolkit_dir, cv_factory(entries=14, bullets=4), html, "--no-optimise")
        assert prepared.returncode == 0, prepared.stderr

        result = subprocess.run(
            [sys.executable, str(toolkit_dir / "cv_optimiser.py"), str(html),
             "--max-pages", "1", "--margin-in", "0.1", "--side-margin-in", "0.1",
             "--target-pt", "8", "--min-pt", "8", "--no-log"],
            capture_output=True, text=True, timeout=300)
        assert result.stderr.count("clamping to 0.5in") == 1, result.stderr
        assert result.stderr.count("below the 10pt professional minimum") == 1, result.stderr

    def test_type_below_the_professional_floor_is_warned_about(self, toolkit_dir, tmp_path,
                                                                chrome, cv_factory):
        """--min-pt 8 is honoured, not clamped — but cv_build.py must say
        so rather than quietly setting a CV in 8pt type."""
        out = tmp_path / "cv.html"
        result = build(toolkit_dir, cv_factory(entries=14, bullets=4), out,
                       "--max-pages", "1", "--target-pt", "8", "--min-pt", "8")
        assert "below the 10pt professional minimum" in result.stderr

    def test_normal_settings_are_not_warned_about(self, toolkit_dir, tmp_path, chrome, cv_factory):
        """Cheap to get wrong in the other direction: the defaults must
        stay silent. Uses content too big to fit, which fails fast at the
        first render instead of running the full binary search."""
        out = tmp_path / "cv.html"
        result = build(toolkit_dir, cv_factory(entries=14, bullets=4), out,
                       "--max-pages", "1", "--margin-in", "0.75",
                       "--target-pt", "10", "--min-pt", "10")
        assert "clamping" not in result.stderr
        assert "professional minimum" not in result.stderr


@pytest.mark.slow
class TestCoverLetter:
    def test_renders_a_one_page_pdf(self, toolkit_dir, tmp_path, chrome):
        letter = tmp_path / "cover-letter.md"
        letter.write_text(
            "---\nname: Test Person\nemail: test@example.com\n---\n\n"
            "Dear Jane,\n\nI am writing about the role.\n\n"
            "I would bring a decade of relevant work.\n\n"
            "Best wishes,\n\nTest Person\n01234 567890\n",
            encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(toolkit_dir / "cv_letter.py"), str(letter)],
            capture_output=True, text=True, timeout=300)

        assert result.returncode == 0, result.stderr
        pdf = letter.with_suffix(".pdf")
        assert pdf.exists()
        assert cv_optimiser.count_pdf_pages(pdf.read_bytes()) == 1
        assert "One page at 11.0pt on A4" in result.stdout

    def test_no_stray_preview_pdf_is_left_behind(self, toolkit_dir, tmp_path, chrome):
        """Regression: counting the pages used to render a second PDF,
        leaving cover-letter.preview.pdf in the application folder."""
        letter = tmp_path / "cover-letter.md"
        letter.write_text("Dear Jane,\n\nShort letter.\n", encoding="utf-8")
        subprocess.run([sys.executable, str(toolkit_dir / "cv_letter.py"), str(letter)],
                       capture_output=True, text=True, timeout=300)
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "cover-letter.html", "cover-letter.md", "cover-letter.pdf"]


class TestNewApplication:
    """Runs in-process against a redirected applications/ directory, so the
    tests never write into the real one. No Chrome needed."""

    @pytest.fixture(autouse=True)
    def _sandbox(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cv_new, "APPLICATIONS", tmp_path / "applications")
        monkeypatch.setattr(cv_new, "TOOLKIT_DIR", tmp_path)

    def test_creates_the_three_starter_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["cv_new.py", "2026-10_acme_analyst"])
        cv_new.main()

        folder = tmp_path / "applications" / "2026-10_acme_analyst"
        assert sorted(p.name for p in folder.iterdir()) == [
            "cover-letter.md", "cv.md", "jobad.txt"]
        assert "name:" in (folder / "cv.md").read_text(encoding="utf-8")

    def test_the_copied_template_is_buildable(self, tmp_path, monkeypatch):
        """A starter cv.md must parse, or the first thing a new user does
        fails."""
        monkeypatch.setattr(sys, "argv", ["cv_new.py", "acme"])
        cv_new.main()
        import cv_build
        parsed = cv_build.parse_markdown(
            (tmp_path / "applications" / "acme" / "cv.md").read_text(encoding="utf-8"))
        assert parsed["header"]["name"]
        assert parsed["sections"]

    def test_refuses_to_clobber_an_existing_folder(self, tmp_path, monkeypatch):
        (tmp_path / "applications" / "taken").mkdir(parents=True)
        monkeypatch.setattr(sys, "argv", ["cv_new.py", "taken"])
        with pytest.raises(SystemExit) as exc:
            cv_new.main()
        assert "already exists" in str(exc.value)

    def test_force_fills_in_only_the_missing_files(self, tmp_path, monkeypatch):
        folder = tmp_path / "applications" / "partial"
        folder.mkdir(parents=True)
        (folder / "cv.md").write_text("mine, keep me", encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["cv_new.py", "partial", "--force"])
        cv_new.main()
        assert (folder / "cv.md").read_text(encoding="utf-8") == "mine, keep me"
        assert (folder / "jobad.txt").exists()

    def test_non_interactive_with_no_name_fails_clearly(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["cv_new.py"])
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        with pytest.raises(SystemExit) as exc:
            cv_new.main()
        assert "No folder name given" in str(exc.value)

    # -- choosing between your template and the shipped example -----------

    def test_prefers_your_own_template(self, tmp_path, monkeypatch):
        mine = tmp_path / "cv_template.md"
        mine.write_text("---\nname: My Real Name\n---\n\n## Profile\n\nmine\n",
                        encoding="utf-8")
        monkeypatch.setattr(cv_new, "TEMPLATE", mine)
        monkeypatch.setattr(sys, "argv", ["cv_new.py", "acme"])
        cv_new.main()
        assert "My Real Name" in (
            tmp_path / "applications" / "acme" / "cv.md").read_text(encoding="utf-8")

    def test_falls_back_to_the_example_and_says_so(self, tmp_path, monkeypatch, capsys):
        """A fresh clone has no cv_template.md — it is git-ignored, so it
        is never checked out. Using the example silently would leave
        someone wondering why their own details weren't picked up."""
        # Correctly named but absent, as on a fresh clone.
        monkeypatch.setattr(cv_new, "TEMPLATE", tmp_path / "cv_template.md")
        monkeypatch.setattr(sys, "argv", ["cv_new.py", "acme"])
        cv_new.main()

        assert (tmp_path / "applications" / "acme" / "cv.md").exists()
        out = capsys.readouterr().out
        assert "cv_template.example.md" in out
        assert "cp cv_template.example.md cv_template.md" in out

    def test_fails_clearly_when_neither_template_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cv_new, "TEMPLATE", tmp_path / "nope.md")
        monkeypatch.setattr(cv_new, "TEMPLATE_EXAMPLE", tmp_path / "also-nope.md")
        monkeypatch.setattr(sys, "argv", ["cv_new.py", "acme"])
        with pytest.raises(SystemExit) as exc:
            cv_new.main()
        assert "Can't find" in str(exc.value)

    def test_your_template_is_git_ignored(self, toolkit_dir):
        """The whole point of the split: editing your contact details into
        cv_template.md must not stage them for commit."""
        ignored = subprocess.run(
            ["git", "check-ignore", "cv_template.md", "full_cv.md"],
            cwd=toolkit_dir, capture_output=True, text=True)
        assert ignored.returncode == 0
        assert set(ignored.stdout.split()) == {"cv_template.md", "full_cv.md"}

    def test_the_example_templates_are_tracked(self, toolkit_dir):
        tracked = subprocess.run(
            ["git", "ls-files", "cv_template.example.md", "full_cv.example.md"],
            cwd=toolkit_dir, capture_output=True, text=True)
        assert set(tracked.stdout.split()) == {
            "cv_template.example.md", "full_cv.example.md"}
