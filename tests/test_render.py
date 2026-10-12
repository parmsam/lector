import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from render import render_document


def test_emphasis_within_one_sentence_renders_with_real_formatting():
    html, _ = render_document("This is *italic* and **bold** text. Second sentence.")
    assert "<em>italic</em>" in html
    assert "<strong>bold</strong>" in html


def test_emphasis_spanning_two_sentences_falls_back_to_plain_text():
    # Real bug found via a user's actual document: a single *…* run wrapping
    # TWO full sentences gets split in half by sentence-boundary splitting,
    # leaving each half with only one of the two "*" delimiters. Rendering
    # each half as standalone inline markdown would print a literal, stray
    # "*" character (markdown-it can't pair an unmatched delimiter) -- worse
    # than the old plain-text-everywhere behavior. Must fall back to escaped
    # plain text for a sentence like this instead.
    html, _ = render_document(
        "*A prose pass through the outline. That file stays the source, not synced.*"
    )
    assert "*" not in html
    assert "<em>" not in html
    assert "A prose pass through the outline." in html
    assert "That file stays the source, not synced." in html


def test_highlight_within_one_sentence_renders_as_mark():
    # Obsidian's ==highlight== syntax -- markdown-it-py's "commonmark" preset
    # has no rule for it, so it was previously printed literally instead of
    # becoming a <mark> span.
    html, _ = render_document("This is ==highlighted== text. Second sentence.")
    assert "<mark>highlighted</mark>" in html


def test_highlight_can_nest_emphasis():
    html, _ = render_document("This is ==**bold and highlighted**== text. Second sentence.")
    assert "<mark><strong>bold and highlighted</strong></mark>" in html


def test_highlight_spanning_two_sentences_keeps_formatting_per_sentence():
    html, _ = render_document(
        "==A prose pass through the outline. That file stays the source, not synced.=="
    )
    assert "==" not in html
    assert "<mark>A prose pass through the outline.</mark>" in html
    assert "<mark>That file stays the source, not synced.</mark>" in html


def test_bold_spanning_sentences_keeps_bold_per_sentence():
    html, doc = render_document("**First bold. Second bold.** Plain after.")
    assert [s.text for s in doc.segments] == ["First bold.", "Second bold.", "Plain after."]
    assert "<strong>First bold.</strong>" in html
    assert "<strong>Second bold.</strong>" in html
    assert "**" not in html


def test_heading_sentences_are_word_highlightable_spans():
    html, doc = render_document("## Can it work? A survey.")
    assert html.startswith("<h2>")
    assert '<span data-seg="0" data-type="heading" data-words=' in html
    assert '<span data-seg="1" data-type="heading" data-words=' in html


def test_table_renders_with_one_seg_per_row():
    html, doc = render_document("| Term | Meaning |\n|:---|---:|\n| **Drift** | slow change |")
    assert "<table>" in html
    assert '<tr data-seg="0" data-type="tablerow"><th style="text-align:left">Term</th>' in html
    assert '<tr data-seg="1" data-type="tablerow"><td style="text-align:left"><strong>Drift</strong></td>' in html
    assert "---" not in html


def test_raw_html_is_escaped_not_executed():
    html, _ = render_document("This has a <script>alert(1)</script> tag. Second sentence.")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_literal_asterisk_in_prose_falls_back_gracefully():
    # An odd count of "*" that ISN'T a split emphasis marker (just a genuine
    # literal character) should still render safely as plain text rather than
    # crash or produce broken markup.
    html, _ = render_document("The result is 3 * 4 = 12 in this example.")
    assert "3 * 4 = 12" in html


def test_nested_list_renders_as_real_nested_markup():
    html, _ = render_document("- parent\n  - child\n  - child two\n- parent two")
    assert "<ul><li" in html
    # The nested <ul> must live inside the parent <li> (before it closes),
    # not as a sibling list after it -- and the marker must not leak through
    # as literal "- " text.
    assert re.search(r"<li[^>]*>parent<ul>", html)
    assert "- child" not in html
    assert html.count("<ul>") == 2
    assert html.count("</ul>") == 2


def test_mixed_ordered_and_nested_unordered_list():
    html, _ = render_document("1. one\n   - sub\n2. two")
    assert "<ol><li" in html
    assert re.search(r"<li[^>]*>one<ul><li", html)


def test_list_item_continuation_renders_as_one_item_not_two():
    html, _ = render_document("- one\n  more of one\n- two")
    assert html.count("<li") == 2
    assert "one more of one" in html


def test_list_immediately_after_bold_label_renders_as_real_list():
    html, _ = render_document("**Label:**\n- one\n- two\n- three")
    assert "<strong>Label:</strong>" in html
    assert "<ul><li" in html
    assert html.count("<li") == 3
    assert "- one" not in html


def test_bold_wrapped_punctuation_renders_without_literal_asterisks():
    html, _ = render_document("The distinction collapses**.** He suggested more.")
    assert "**" not in html
    assert "The distinction collapses." in html
