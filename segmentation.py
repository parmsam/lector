"""Markdown -> reading-order segments + table of contents, in a single pass.

Ported from the proven, bug-fixed Python segmenter in v1's markdown-to-audio
skill (strip_markdown/has_speakable_content/split_sentences/segment_markdown),
combined with the richer typed structure of v1's TypeScript textSegmenter.ts.

v1 computed segments (for TTS) and the table of contents separately, as two
independent passes over the same markdown that happened to agree on heading
order by construction of the source text rather than by any actual link
between them. A heading segment that got filtered out (e.g. because it was
empty after stripping) could silently desync the two passes. Here, a
TocEntry is only ever created inside the same branch, at the same moment,
that its corresponding heading Segment is appended -- so a TocEntry can
never reference a heading that doesn't exist in `segments`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Segment:
    index: int
    text: str          # stripped plain text, sent to TTS
    raw_text: str       # original markdown source for this segment (for display)
    type: str           # "heading" | "paragraph" | "listitem" | "blockquote" | "code" | "tablerow"
    level: int | None   # heading level 1-6, else None
    block_index: int    # which top-level block (split on blank lines) this came from
    list_depth: int | None = None  # nesting depth for "listitem" segments (0 = top level), else None


@dataclass
class TocEntry:
    level: int
    text: str
    segment_index: int


@dataclass
class SegmentedDocument:
    segments: list[Segment] = field(default_factory=list)
    toc: list[TocEntry] = field(default_factory=list)
    # Raw (trimmed) text of every non-empty block, indexed by block_index -- including
    # blocks with NO segments (thematic breaks, raw HTML), so render.py can fall back
    # to plain markdown rendering for those without re-deriving the block split itself.
    blocks: list[str] = field(default_factory=list)


def strip_markdown(text: str) -> str:
    """Strip markdown formatting down to plain speakable text."""
    # Unescape CommonMark backslash-escapes (e.g. marker-pdf emits "\_\_\_\_" for
    # signature/blank lines) before the emphasis regexes below, so escaped runs of
    # punctuation don't survive as literal backslashes in the narrated text.
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!>~])", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"==(.+?)==", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    text = re.sub(r"!\[.*?\]\(.+?\)", "", text)
    # These four strip a block-level marker (heading/blockquote/list) only when
    # it's at the very start of the text being processed -- anchored to "^",
    # not a global unanchored match. Unanchored, they'd eat any coincidental
    # "* "/"- "/"> " substring appearing anywhere in ordinary prose (e.g. "3 *
    # 4 = 12" silently becoming "3 4 = 12", or "5 > 3" becoming "5 3") -- a
    # real bug inherited verbatim from v1 that a test caught while working on
    # something unrelated (see LEARNINGS.md).
    text = re.sub(r"^#{1,6}\s+", "", text)
    text = re.sub(r"^>\s+", "", text)
    text = re.sub(r"^[-*+]\s+", "", text)
    text = re.sub(r"^\d+\.\s+", "", text)
    return text.strip()


# Empty HTML anchor elements -- marker-pdf emits one per page break
# (`<span id="page-182-0"></span>`), often at the very start of a heading or
# paragraph. They carry no text, but left in place they showed up as literal
# tags (raw HTML is escaped, see render.py), leaked into the table of
# contents and the spoken text, and a block *starting* with one was taken
# for a raw-HTML block and skipped entirely. Only empty <span>/<a> with
# attributes are removed; any other HTML is left as-is.
_EMPTY_ANCHOR_RE = re.compile(r"<(span|a)\b[^<>]*>\s*</\1>", re.IGNORECASE)


def strip_empty_anchors(markdown: str) -> str:
    return _EMPTY_ANCHOR_RE.sub("", markdown)


def has_speakable_content(text: str) -> bool:
    """True if text has at least one letter or digit -- filters out lines that are
    pure punctuation/underscores (e.g. signature-line placeholders like "____")."""
    return bool(re.search(r"[A-Za-z0-9]", text))


def split_sentences(text: str) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z"\']|$)', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences if sentences else [text]


def _sentence_pairs(raw_block: str, plain_whole: str) -> list[tuple[str, str]]:
    """Pair each sentence's plain (TTS/word-highlighting) text with its raw
    (markdown-preserving, for display) text.

    The two are split independently: `plain_whole` (already fully stripped of
    markdown) via the proven approach, `raw_block` (markdown intact) so
    render.py can show real formatting. They're paired by index, which holds
    as long as both splits agree on sentence count -- true in the vast
    majority of real text, since the sentence-boundary regex only looks at
    `.!?` + whitespace + a capital letter, which markdown syntax elsewhere
    doesn't interfere with. If they ever disagree (some markdown construct
    that itself looks like a sentence boundary), raw_text falls back to the
    plain text for every sentence in this block -- this can only lose rich
    formatting for that block, never misattribute one sentence's raw markup
    to a different sentence, and never affects `text` (the field TTS and
    word-highlighting actually use), which is always computed the
    old/proven way regardless."""
    plain_sentences = split_sentences(plain_whole)
    raw_sentences = _split_raw_sentences(raw_block)
    if len(plain_sentences) != len(raw_sentences):
        raw_sentences = plain_sentences
    else:
        raw_sentences = _balance_emphasis(raw_sentences)
    return list(zip(plain_sentences, raw_sentences))


# Same boundary rule as split_sentences(), but tolerant of an emphasis
# delimiter sitting between the punctuation and the whitespace ("...end.**
# Next") or between the whitespace and the capital ("end. **Next"). Without
# this, a sentence that ends or starts in bold splits in the plain text but
# not the raw text, the counts disagree, and the whole block silently loses
# its formatting (_sentence_pairs' fallback). Fixed-width lookbehinds only
# (Python's re can't do variable-width), hence the alternation.
_RAW_SENTENCE_BOUNDARY_RE = re.compile(
    r"(?:(?<=[.!?])|(?<=[.!?][*_])|(?<=[.!?](?:\*\*|__|==|~~)))"
    r"\s+(?=(?:\*\*|__|==|~~|[*_])?[A-Z\"\']|$)"
)
_PAIRED_DELIMS = ("**", "__", "==", "~~")


def _split_raw_sentences(text: str) -> list[str]:
    sentences = [s.strip() for s in _RAW_SENTENCE_BOUNDARY_RE.split(text) if s.strip()]
    return sentences if sentences else [text]


def _balance_emphasis(raw_sentences: list[str]) -> list[str]:
    """A bold (or highlight/strikethrough) run can span several sentences --
    e.g. a whole paragraph wrapped in one `**...**`. Split per sentence, the
    first half gets only the opening `**` and the last only the closing one,
    so neither renders as bold (render.py falls back to plain text for an
    unbalanced sentence rather than show a stray `**`). Close any run still
    open at the end of a sentence and reopen it at the start of the next, so
    every sentence is self-contained markdown and keeps its formatting."""
    out = []
    carried: list[str] = []  # delimiters opened in an earlier sentence, still open
    for sentence in raw_sentences:
        sentence = "".join(carried) + sentence
        still_open = [d for d in _PAIRED_DELIMS if sentence.count(d) % 2]
        out.append(sentence + "".join(reversed(still_open)))
        carried = still_open
    return out


_HEADING_RE = re.compile(r"^(#{1,6})\s")
_THEMATIC_BREAK_RE = re.compile(r"^(-{3,}|\*{3,}|_{3,})$")
_HTML_BLOCK_RE = re.compile(r"^<")
_CODE_FENCE_RE = re.compile(r"^```")
_BLOCKQUOTE_RE = re.compile(r"^>")
_LIST_ITEM_RE = re.compile(r"^[-*+]\s|^\d+\.\s")
_LIST_ITEM_LINE_RE = re.compile(r"^(\s*)([-*+]\s+|\d+\.\s+)")
_TABLE_DELIM_ROW_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")


def _is_table_start(lines: list[str], i: int) -> bool:
    """GFM table: a row with a "|" immediately followed by a delimiter row
    ("|---|:---:|") that itself contains a "|"."""
    return (
        i + 1 < len(lines)
        and "|" in lines[i]
        and "|" in lines[i + 1]
        and bool(_TABLE_DELIM_ROW_RE.match(lines[i + 1]))
    )


def _split_headings_and_tables(block: str) -> list[str]:
    """An ATX heading is always exactly one line, and a table runs only
    until its first non-"|" line -- but this segmenter's block splitter only
    breaks on *blank* lines, so a heading with its body directly underneath
    ("## Overview\nThe body...", a very common real-world pattern) or a
    table directly under a heading used to land in one block, classified by
    its first line alone: the whole section -- body, bold labels, table and
    all -- became a single giant "heading" segment, read as one unbroken
    chunk instead of sentence by sentence. Split each heading line and each
    table out into its own block. A fenced code block is left whole (its
    "# comment" lines are not headings)."""
    if _CODE_FENCE_RE.match(block):
        return [block]
    lines = block.split("\n")
    pieces: list[str] = []
    current: list[str] = []

    def flush() -> None:
        text = "\n".join(current).strip()
        if text:
            pieces.append(text)
        current.clear()

    i = 0
    while i < len(lines):
        if _HEADING_RE.match(lines[i]):
            flush()
            pieces.append(lines[i].strip())
            i += 1
        elif _is_table_start(lines, i):
            flush()
            j = i + 2
            while j < len(lines) and "|" in lines[j] and lines[j].strip():
                j += 1
            pieces.append("\n".join(lines[i:j]).strip())
            i = j
        else:
            current.append(lines[i])
            i += 1
    flush()
    return pieces


def split_table_cells(row: str) -> list[str]:
    """Cells of one GFM table row (outer pipes optional, "\\|" is a literal
    pipe inside a cell). Shared with render.py so display and speech always
    agree on where cells begin and end."""
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", row)]


def _split_prose_and_list(block: str) -> list[str]:
    """A list can immediately follow other content with no blank line
    separating them -- e.g. a bold "label" line directly above its bullets,
    a very common real-world pattern. CommonMark treats that as the
    preceding content ending and a new list beginning ("a list can
    interrupt a paragraph"), but this segmenter's block splitter only looks
    for a *blank* line, so without this step the whole thing gets
    classified as one lump by its first line alone -- usually landing
    everything in the paragraph branch, bullets and all, as literal "- "
    text (a real bug found via a user's actual document). If an
    un-indented marker line starts partway through a block, split there:
    everything before becomes its own block, the marker line onward becomes
    its own (list) block. Only one split point is needed since, by
    construction, nothing before the first marker line can itself be a
    marker line.

    Deliberately uses _LIST_ITEM_RE (marker at column 0 only), not the
    indentation-tolerant _LIST_ITEM_LINE_RE: an *indented* marker later in
    the block is a nested sub-item of a list already underway (or this
    block already started as one), not a new list interrupting something
    else, and must be left for the existing list branch's own nesting logic
    -- splitting there instead corrupts it (the split pieces get `.strip()`ed
    independently, which silently eats the leading indentation that encodes
    its nesting depth)."""
    lines = block.split("\n")
    if _is_table_start(lines, 0):
        return [block]  # a table (see _split_headings_and_tables); its cells are never list items
    if _LIST_ITEM_RE.match(lines[0]):
        return [block]  # already list-first; the list branch handles all of it, nesting included
    for i, line in enumerate(lines):
        if i > 0 and _LIST_ITEM_RE.match(line):
            before = "\n".join(lines[:i]).strip()
            after = "\n".join(lines[i:]).strip()
            return [b for b in (before, after) if b]
    return [block]


def segment_document(markdown: str) -> SegmentedDocument:
    doc = SegmentedDocument()
    # Normalize CRLF/CR to LF before anything else. The block splitter below
    # requires two literal consecutive "\n" characters; "\r\n\r\n" (what
    # browsers submit for a <textarea>'s content, and what many
    # Windows-authored files already contain) never matches that, so an
    # un-normalized CRLF document collapses into a single giant unsplit block
    # instead of being segmented at all. Normalizing here (not just at the
    # point content is saved) means content already stored with CRLF renders
    # correctly on next view too, with no migration needed.
    markdown = markdown.replace("\r\n", "\n").replace("\r", "\n")
    markdown = strip_empty_anchors(markdown)
    raw_blocks = re.split(r"\n{2,}", markdown)
    block_index = 0

    for raw_block in raw_blocks:
        outer_trimmed = raw_block.strip()
        if not outer_trimmed:
            continue

        for structural in _split_headings_and_tables(outer_trimmed):
            for trimmed in _split_prose_and_list(structural):
                doc.blocks.append(trimmed)
                _segment_one_block(trimmed, block_index, doc)
                block_index += 1

    return doc


def _segment_one_block(trimmed: str, block_index: int, doc: SegmentedDocument) -> None:
    if _HTML_BLOCK_RE.match(trimmed):
        pass  # HTML block -- nothing to read aloud
    elif _THEMATIC_BREAK_RE.match(trimmed):
        pass  # thematic break (horizontal rule) -- nothing to read aloud
    elif (m := _HEADING_RE.match(trimmed)):
        # Read sentence by sentence like a paragraph (a long heading such as
        # "Can X do Y? A survey of Z" is two sentences), but still one TOC
        # entry -- for the whole heading, pointing at its first sentence.
        level = len(m.group(1))
        raw_no_prefix = re.sub(r"^#{1,6}\s+", "", trimmed)
        plain_whole = strip_markdown(raw_no_prefix)
        first_idx = None
        for plain_sentence, raw_sentence in _sentence_pairs(raw_no_prefix, plain_whole):
            plain_sentence = plain_sentence.strip()
            raw_sentence = raw_sentence.strip()
            if plain_sentence and has_speakable_content(plain_sentence):
                idx = len(doc.segments)
                if first_idx is None:
                    first_idx = idx
                doc.segments.append(Segment(
                    index=idx, text=plain_sentence, raw_text=raw_sentence,
                    type="heading", level=level, block_index=block_index,
                ))
        if first_idx is not None:
            doc.toc.append(TocEntry(level=level, text=plain_whole, segment_index=first_idx))
    elif _is_table_start(trimmed.split("\n"), 0):
        # One segment per row (header row included, delimiter row skipped),
        # spoken as its cells separated by commas. raw_text is the row's
        # source line, which render.py uses to match rows back to segments.
        rows = trimmed.split("\n")
        for row in rows[:1] + rows[2:]:
            cells = [strip_markdown(c) for c in split_table_cells(row)]
            plain = ", ".join(c for c in cells if has_speakable_content(c))
            if plain:
                idx = len(doc.segments)
                doc.segments.append(Segment(
                    index=idx, text=plain, raw_text=row.strip(),
                    type="tablerow", level=None, block_index=block_index,
                ))
    elif _CODE_FENCE_RE.match(trimmed):
        idx = len(doc.segments)
        doc.segments.append(Segment(
            index=idx, text="code block", raw_text=trimmed,
            type="code", level=None, block_index=block_index,
        ))
    elif _BLOCKQUOTE_RE.match(trimmed):
        # strip_markdown()'s own ">" removal only strips a single leading
        # marker (anchored to the very start of the string, not per-line --
        # see its docstring), so a multi-line blockquote's later lines would
        # keep their "> " prefix if left to strip_markdown alone. Remove all
        # of them here first (MULTILINE), then strip_markdown only has
        # inline formatting left to handle.
        raw_no_prefix = re.sub(r"^>\s?", "", trimmed, flags=re.MULTILINE)
        plain_whole = strip_markdown(raw_no_prefix)
        for plain_sentence, raw_sentence in _sentence_pairs(raw_no_prefix, plain_whole):
            plain_sentence = plain_sentence.strip()
            raw_sentence = raw_sentence.strip()
            if plain_sentence and has_speakable_content(plain_sentence):
                idx = len(doc.segments)
                doc.segments.append(Segment(
                    index=idx, text=plain_sentence, raw_text=raw_sentence,
                    type="blockquote", level=None, block_index=block_index,
                ))
    elif _LIST_ITEM_RE.match(trimmed):
        # Group lines into items first (a line starting with a marker
        # begins a new item; any other line -- a wrapped continuation, or
        # an indented sub-item -- attaches to the item currently being
        # built) before turning each into a Segment, rather than treating
        # every line as its own item: that previously turned a plain
        # wrapped continuation line into a bogus extra bullet, and an
        # indented sub-bullet's marker survived as literal "- " text
        # instead of being recognized as a nested item (its regex match
        # requires the marker at position 0, which leading indentation
        # broke). `list_depth` (indent width // 2, a heuristic like the
        # rest of this segmenter -- see module docstring) lets render.py
        # rebuild real nested <ul>/<ol> markup from this flat list.
        items: list[tuple[int, list[str]]] = []
        for line in trimmed.split("\n"):
            m = _LIST_ITEM_LINE_RE.match(line)
            if m:
                depth = len(m.group(1).expandtabs(4)) // 2
                items.append((depth, [line.strip()]))
            elif items:
                items[-1][1].append(line.strip())
        for depth, raw_lines in items:
            raw_joined = " ".join(raw_lines)
            plain = strip_markdown(raw_joined)
            if plain and has_speakable_content(plain):
                idx = len(doc.segments)
                doc.segments.append(Segment(
                    index=idx, text=plain, raw_text=raw_joined,
                    type="listitem", level=None, block_index=block_index,
                    list_depth=depth,
                ))
    else:
        plain_whole = strip_markdown(trimmed)
        for plain_sentence, raw_sentence in _sentence_pairs(trimmed, plain_whole):
            plain_sentence = plain_sentence.strip()
            raw_sentence = raw_sentence.strip()
            if plain_sentence and has_speakable_content(plain_sentence):
                idx = len(doc.segments)
                doc.segments.append(Segment(
                    index=idx, text=plain_sentence, raw_text=raw_sentence,
                    type="paragraph", level=None, block_index=block_index,
                ))
