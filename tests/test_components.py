import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fasthtml.common import to_xml

import components as comp


def _article(**kw):
    base = dict(
        id=1, title="T", source_type="paste", original_filename=None, folder=None,
        created_at="2026-08-12T10:00:00+00:00", last_segment_index=-1, last_played_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_fmt_minutes():
    assert comp._fmt_minutes(0.2) == "<1 min"
    assert comp._fmt_minutes(12.4) == "12 min"
    assert comp._fmt_minutes(60) == "1 h"
    assert comp._fmt_minutes(132) == "2 h 12 min"


def test_source_domain_only_for_url_articles():
    assert comp._source_domain(_article(source_type="url", original_filename="https://www.theguardian.com/x")) == "theguardian.com"
    assert comp._source_domain(_article(source_type="markdown_file", original_filename="notes.md")) == ""


def test_article_row_meta_shows_progress_domain_and_open_original():
    a = _article(source_type="url", original_filename="https://answer.ai/posts/x.html", last_segment_index=3)
    stats = {1: comp.ArticleStats(minutes=20, progress=0.25, minutes_left=15)}
    html = to_xml(comp._article_row(a, [], stats))
    assert "25% · 15 min left · answer.ai · Aug 12" in html
    assert 'class="progress-fill" style="width:25%"' in html
    assert "Open original" in html


def test_single_child_folder_chain_renders_as_one_row():
    a = _article(folder="Book/markdown_output/Book")
    html = to_xml(comp.library_page([a], stats={1: comp.ArticleStats(minutes=5)}))
    assert "markdown_output / Book" in html


def test_continue_listening_excludes_finished_and_unstarted():
    started = _article(id=1, title="Started", last_segment_index=2)
    finished = _article(id=2, title="Done", last_segment_index=9)
    fresh = _article(id=3, title="Fresh")
    stats = {
        1: comp.ArticleStats(minutes=10, progress=0.2, minutes_left=8),
        2: comp.ArticleStats(minutes=10, progress=0.99, minutes_left=0.1, finished=True),
        3: comp.ArticleStats(minutes=10),
    }
    html = to_xml(comp.library_page([started, finished, fresh], stats=stats))
    section = html.split('id="continue-section"')[1].split("</section>")[0]
    assert "Started" in section
    assert "Done" not in section and "Fresh" not in section


def test_article_page_renders_with_source_link():
    a = _article(
        source_type="url", original_filename="https://www.theguardian.com/x", markdown="# T\n\nHi.",
        last_voice=None, last_speed=None, content_hash="h",
    )
    html = to_xml(comp.article_page(a, "<p>Hi.</p>", []))
    assert "theguardian.com ↗" in html


def test_lan_address_shown_as_link_only_when_given():
    a = _article()
    with_lan = to_xml(comp.library_page([a], lan_url="http://192.0.2.10:5001", stats={1: comp.ArticleStats(minutes=1)}))
    assert 'class="lan-line"' in with_lan
    assert '<a href="http://192.0.2.10:5001" class="lan-url-link">http://192.0.2.10:5001</a>' in with_lan
    without = to_xml(comp.library_page([a], stats={1: comp.ArticleStats(minutes=1)}))
    assert 'class="lan-line"' not in without
