import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qmd_ingest import front_matter_title, qmd_to_markdown
from segmentation import segment_document


def _spoken(qmd: str) -> list[str]:
    return [s.text for s in segment_document(qmd_to_markdown(qmd)).segments]


def test_front_matter_dropped_and_title_becomes_heading():
    qmd = '---\ntitle: "My Report"\nauthor: Me\nformat: html\n---\n\nIntro text.'
    assert front_matter_title(qmd) == "My Report"
    assert qmd_to_markdown(qmd) == "# My Report\n\nIntro text."


def test_existing_top_heading_not_duplicated():
    assert qmd_to_markdown("---\ntitle: T\n---\n\n# Own heading\n\nBody.") == "# Own heading\n\nBody."


def test_no_front_matter_leaves_thematic_break_alone():
    assert qmd_to_markdown("Text.\n\n---\n\nMore.") == "Text.\n\n---\n\nMore."


def test_chunk_becomes_plain_code_without_options():
    md = qmd_to_markdown("```{python}\n#| label: fig-x\nprint(1)\n```")
    assert md == "```python\nprint(1)\n```"


def test_hidden_chunks_and_raw_blocks_dropped():
    qmd = (
        "Before.\n\n```{r}\n#| echo: false\nx <- 1\n```\n\n"
        "```{r, include=FALSE}\ny <- 2\n```\n\n```{=html}\n<b>hi</b>\n```\n\nAfter."
    )
    assert qmd_to_markdown(qmd) == "Before.\n\nAfter."


def test_plain_fence_untouched_including_colons_inside():
    qmd = "```\n::: not a div\n## not a heading {#x}\n```"
    assert qmd_to_markdown(qmd) == qmd


def test_callout_with_heading_title():
    qmd = "::: {.callout-tip}\n## Pro tip\n\nDo the thing.\n:::"
    assert qmd_to_markdown(qmd) == "> [!tip] Pro tip\n>\n> Do the thing."
    assert _spoken(qmd) == ["Pro tip", "Do the thing."]


def test_callout_with_title_attribute_and_no_title():
    assert qmd_to_markdown('::: {.callout-warning title="Careful"}\nHot.\n:::') == "> [!warning] Careful\n> Hot."
    assert _spoken("::: callout-note\nJust a note.\n:::") == ["Note", "Just a note."]


def test_other_divs_unwrapped():
    qmd = ":::: {.columns}\n::: {.column width=\"50%\"}\nLeft.\n:::\n\n::: {.column}\nRight.\n:::\n::::"
    assert _spoken(qmd) == ["Left.", "Right."]


def test_inline_quarto_syntax_not_read():
    qmd = (
        "## Methods {#sec-methods}\n\n"
        "See @fig-plot and @sec-methods. [Small caps]{.smallcaps} here.{{< pagebreak >}}\n\n"
        "![A plot](plot.png){width=50%}"
    )
    doc = segment_document(qmd_to_markdown(qmd))
    assert doc.toc[0].text == "Methods"
    assert [s.text for s in doc.segments] == ["Methods", "See Figure and Section.", "Small caps here."]
    assert "{" not in qmd_to_markdown(qmd)


def test_email_not_treated_as_cross_reference():
    assert qmd_to_markdown("Mail me@fig-tree.com.") == "Mail me@fig-tree.com."
