"""Quarto (.qmd) -> plain markdown, at upload time.

Lector reads a .qmd the way Quarto would *render* it, not its source: the
YAML front matter, chunk options, div fences, attribute lists and
shortcodes are all Quarto syntax that would otherwise be shown and read
aloud. Like pdf_ingest/url_ingest, this runs once when the file is added
and the result is stored as ordinary markdown -- segmentation.py and
render.py never need to know Quarto exists.

Nothing is executed: a code chunk stays a (skipped) code block, and its
output -- which only exists after rendering -- is not available.
"""
from __future__ import annotations

import re

_FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|\Z)", re.DOTALL)
_YAML_TITLE_RE = re.compile(r"^title:[ \t]*(.+?)[ \t]*$", re.MULTILINE)

_FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*(.*)$")
# "```{python}", "```{r, echo=FALSE}", "```{.python}", "```{=html}"
_CHUNK_HEADER_RE = re.compile(r"^\{\s*([=.]?)([\w+-]*)(.*)\}\s*$")
_CHUNK_HIDDEN_RE = re.compile(r"\b(?:echo|include)\s*[:=]\s*(?:false|FALSE|F)\b")
_DIV_FENCE_RE = re.compile(r"^(:{3,})\s*(.*?)\s*:*\s*$")
_CALLOUT_CLASS_RE = re.compile(r"\.?callout-(\w+)")
_TITLE_ATTR_RE = re.compile(r"""title\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_HEADING_LINE_RE = re.compile(r"^#{1,6}\s+(.*)$")

_SHORTCODE_RE = re.compile(r"\{\{[<%].*?[>%]\}\}")
# "## Intro {#sec-intro}", "$$ x $$ {#eq-x}", ": Caption {#tbl-x}"
_TRAILING_ATTRS_RE = re.compile(r"\s*\{[#.][^{}]*\}\s*$")
# "![cap](a.png){width=50%}", "[link](url){target=_blank}"
_LINK_ATTRS_RE = re.compile(r"(\]\([^()\s]*(?:\s+\"[^\"]*\")?\))\{[^{}]*\}")
# "[small caps]{.smallcaps}" -- a span, not a link (no "(" after "]")
_SPAN_RE = re.compile(r"\[([^\[\]]+)\]\{[^{}]*\}")
# Quarto renders "@fig-plot" as "Figure 1"; without rendering there's no
# number, so it's read as just the kind.
_XREF_KINDS = {
    "fig": "Figure", "tbl": "Table", "sec": "Section", "eq": "Equation",
    "lst": "Listing", "thm": "Theorem", "lem": "Lemma", "cor": "Corollary",
    "prp": "Proposition", "cnj": "Conjecture", "def": "Definition",
    "exm": "Example", "exr": "Exercise",
}
_XREF_RE = re.compile(r"(?<![\w@])@(" + "|".join(_XREF_KINDS) + r")-[\w-]*\w")


def front_matter_title(qmd: str) -> str | None:
    m = _FRONT_MATTER_RE.match(qmd)
    if not m or not (t := _YAML_TITLE_RE.search(m.group(1))):
        return None
    title = t.group(1)
    if len(title) >= 2 and title[0] == title[-1] and title[0] in "\"'":
        title = title[1:-1]
    return title.strip() or None


def _inline(line: str) -> str:
    line = _SHORTCODE_RE.sub("", line)
    line = _LINK_ATTRS_RE.sub(r"\1", line)
    line = _SPAN_RE.sub(r"\1", line)
    line = _TRAILING_ATTRS_RE.sub("", line)
    return _XREF_RE.sub(lambda m: _XREF_KINDS[m.group(1)], line)


def _code_block(lines: list[str], i: int) -> tuple[list[str], int]:
    """The fenced block starting at lines[i] -> (its output lines, index
    after it). An executable chunk ("```{python}") becomes a plain
    "```python" block without its "#|" option lines; a chunk Quarto hides
    (echo/include false) and a raw block ("```{=html}") are dropped."""
    indent, fence, info = _FENCE_RE.match(lines[i]).groups()
    j = i + 1
    while j < len(lines):
        m = _FENCE_RE.match(lines[j])
        if m and m.group(2)[0] == fence[0] and len(m.group(2)) >= len(fence) and not m.group(3):
            break
        j += 1
    body = lines[i + 1:j]
    end = min(j + 1, len(lines))
    header = _CHUNK_HEADER_RE.match(info)
    if not header:
        return lines[i:end], end
    raw, lang, opts = header.groups()
    options = "\n".join(l for l in body if l.strip().startswith("#|")) + opts
    if raw == "=" or _CHUNK_HIDDEN_RE.search(options):
        return [], end
    body = [l for l in body if not l.strip().startswith("#|")]
    return [f"{indent}{fence}{lang}", *body, f"{indent}{fence}"], end


def _convert(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _FENCE_RE.match(line):
            block, i = _code_block(lines, i)
            out += block
            continue
        div = _DIV_FENCE_RE.match(line)
        if div and div.group(2):
            inner, i = _div_body(lines, i + 1)
            out += _div(div.group(2), _convert(inner))
            continue
        if div:
            i += 1  # stray closing fence
            continue
        out.append(_inline(line))
        i += 1
    return out


def _div_body(lines: list[str], i: int) -> tuple[list[str], int]:
    """Lines inside the div opened just before lines[i], up to its matching
    closing ":::" (skipping over code blocks and nested divs)."""
    start, depth = i, 1
    while i < len(lines):
        if _FENCE_RE.match(lines[i]):
            i = _code_block(lines, i)[1]
            continue
        div = _DIV_FENCE_RE.match(lines[i])
        if div:
            depth += 1 if div.group(2) else -1
            if depth == 0:
                return lines[start:i], i + 1
        i += 1
    return lines[start:], i


def _div(attrs: str, body: list[str]) -> list[str]:
    """A Quarto callout becomes an Obsidian-style "> [!kind] Title" callout
    (which Lector already renders and reads, title first). Any other div --
    columns, panel-tabset, margin content -- is just its contents."""
    callout = _CALLOUT_CLASS_RE.search(attrs)
    if not callout:
        return ["", *body, ""]
    title_attr = _TITLE_ATTR_RE.search(attrs)
    title = _inline(next(g for g in title_attr.groups() if g is not None)) if title_attr else ""
    content = list(body)
    while content and not content[0].strip():
        content.pop(0)
    if not title and content and (h := _HEADING_LINE_RE.match(content[0])):
        title = h.group(1)
        content.pop(0)
    while content and not content[-1].strip():
        content.pop()
    header = f"> [!{callout.group(1).lower()}] {title}".rstrip()
    return ["", header, *(f"> {l}".rstrip() for l in content), ""]


def qmd_to_markdown(qmd: str) -> str:
    qmd = qmd.replace("\r\n", "\n").replace("\r", "\n")
    title = front_matter_title(qmd)
    body = _FRONT_MATTER_RE.sub("", qmd, count=1)
    markdown = "\n".join(_convert(body.split("\n")))
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    # Quarto renders the front matter title as the page's heading.
    if title and not markdown.startswith("# "):
        markdown = f"# {title}\n\n{markdown}"
    return markdown
