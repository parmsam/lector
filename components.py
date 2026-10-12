"""FT (FastHTML component) builders for every page in the app.

Kept separate from app.py so route handlers stay thin: each route calls one of
these builders and returns the result.
"""
from __future__ import annotations

import re
import time
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse
from pathlib import Path

from fasthtml.common import (
    A, Audio, Body, Blockquote, Button, Datalist, Details, Div, Form, H1, H2,
    Head, Hr, Html, Img, Input, Label, Link, Main, Meta, NotStr, Nav, Option, P,
    Script, Section, Select, Span, Style, Summary, Textarea, Title,
)

from db import SORT_OPTIONS, DEFAULT_SORT
from tts import VOICES, DEFAULT_VOICE, DEFAULT_SPEED
from update_check import REPO, release_url

APP_NAME = "Lector"
REPO_URL = f"https://github.com/{REPO}"
CHANGELOG_URL = f"{REPO_URL}/blob/main/CHANGELOG.md"
# GitHub's mark (Octicons "mark-github", 16px), filled with currentColor so it
# follows the theme.
_GITHUB_ICON = NotStr(
    '<svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true" fill="currentColor">'
    '<path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49'
    '-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82'
    '.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15'
    '-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82'
    ' 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48'
    ' 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>'
)
SPEEDS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5]

# Single source of truth is pyproject.toml's [project].version -- read once at
# import time rather than duplicating the number here.
APP_VERSION = tomllib.loads(
    (Path(__file__).parent / "pyproject.toml").read_text()
)["project"]["version"]

# Cache-busting query param for static assets, fixed at process start. Static
# files are served with a far-future Cache-Control (see app.py's get_static),
# so this is what forces phones/browsers to fetch the new player.js/style.css
# after an edit + restart instead of silently keeping a stale cached copy
# (bit us in practice: iOS Safari cached player.js across a fix that needed
# it, see LEARNINGS.md).
_STATIC_VERSION = str(int(time.time()))

# A ~0.1s silent WAV, played (looped) on first touch/click on iOS. iOS Safari
# puts pages that only use the Web Audio API into the "ambient" audio session
# category, which is muted by the hardware ring/silent switch; playing *any*
# HTML <audio> element flips the page into the "playback" category for the
# rest of the session, so our AudioBufferSourceNode-based playback is audible
# even with the switch flipped to silent. See player.js's unlockAudio().
SILENT_WAV_DATA_URI = (
    "data:audio/wav;base64,"
    + "UklGRmQGAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YUAGAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)


def _head(title: str):
    return Head(
        # Sets data-theme on <html> from localStorage *before* the stylesheet
        # loads, so a saved light/dark choice applies on first paint instead
        # of flashing the system-default theme first. Kept inline (not
        # deferred) and ordered before the Link below for that reason --
        # static/theme.js (deferred) owns the toggle button's click handling.
        Script(NotStr(
            "(function(){try{"
            "var t=localStorage.getItem('theme');"
            "if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t);"
            "}catch(e){}})();"
        )),
        Meta(charset="utf-8"),
        Meta(name="viewport", content="width=device-width, initial-scale=1, viewport-fit=cover"),
        Title(title),
        Link(rel="icon", type="image/svg+xml", href=f"/static/favicon.svg?v={_STATIC_VERSION}"),
        Link(rel="apple-touch-icon", href=f"/static/apple-touch-icon.png?v={_STATIC_VERSION}"),
        # Web App Manifest (name/icons/display/share_target) -- Android's
        # equivalent of the apple-touch-icon/apple-mobile-web-app-* pair
        # below, plus what lets "Add to Home Screen" register this app as a
        # native Share Target (see README's "Share from your phone").
        Link(rel="manifest", href=f"/static/manifest.json?v={_STATIC_VERSION}"),
        # Address-bar/status-bar tint. Static default here for pre-JS paint;
        # theme.js keeps this in sync with the effective (system or manually
        # toggled) theme afterward.
        Meta(name="theme-color", id="theme-color-meta", content="#ffffff"),
        Meta(name="apple-mobile-web-app-capable", content="yes"),
        Meta(name="apple-mobile-web-app-title", content=APP_NAME),
        Link(rel="stylesheet", href=f"/static/style.css?v={_STATIC_VERSION}"),
        Script(src=f"/static/player.js?v={_STATIC_VERSION}", defer=True),
        Script(src=f"/static/library.js?v={_STATIC_VERSION}", defer=True),
        Script(src=f"/static/theme.js?v={_STATIC_VERSION}", defer=True),
        Script(src=f"/static/upload.js?v={_STATIC_VERSION}", defer=True),
    )


def _nav(lan_url: str | None = None):
    """Top bar: brand, Add, theme toggle, and a ⋯ menu holding the
    rarely-needed bits (version/update check, and -- on the library page,
    browsing from this machine -- the LAN address to open on a phone) so
    they don't compete with the content."""
    phone_items = []
    if lan_url:
        phone_items = [
            Div(
                Span("Open on your phone", cls="popover-label"),
                A(lan_url, href=lan_url, cls="lan-url-link"),
                cls="popover-field",
            ),
            Button("Copy address", type="button", cls="popover-item copy-lan-url", data_url=lan_url),
            Hr(cls="popover-sep"),
        ]
    return Nav(
        Div(
            A(
                Img(src=f"/static/favicon.svg?v={_STATIC_VERSION}", alt="", width="22", height="22", cls="brand-logo"),
                Span(APP_NAME, cls="brand-name"),
                href="/", cls="nav-link nav-brand",
            ),
            A(
                f"v{APP_VERSION}", href=release_url(APP_VERSION), cls="version-pill",
                target="_blank", rel="noopener", title=f"What's new in v{APP_VERSION}",
            ),
            cls="nav-brand-group",
        ),
        A("+ Add", href="/add", cls="nav-link nav-add", title="Add an article"),
        A(
            _GITHUB_ICON, href=REPO_URL, cls="nav-icon-btn", target="_blank", rel="noopener",
            title=f"{APP_NAME} on GitHub", aria_label=f"{APP_NAME} on GitHub",
        ),
        Button(
            id="theme-toggle", cls="theme-toggle", type="button",
            title="Toggle light/dark theme", aria_label="Toggle light/dark theme",
        ),
        Button("⋯", type="button", cls="nav-menu-btn", popovertarget="nav-menu", aria_label="More"),
        Div(
            *phone_items,
            Span(f"{APP_NAME} v{APP_VERSION}", cls="popover-label nav-menu-version"),
            A("Check for updates", href="#", id="check-update-link", cls="popover-item"),
            A("Changelog", href=CHANGELOG_URL, target="_blank", rel="noopener", cls="popover-item"),
            A("GitHub repository", href=REPO_URL, target="_blank", rel="noopener", cls="popover-item"),
            id="nav-menu", popover="auto", cls="popover-menu",
        ),
        cls="topnav",
    )


def _build_folder_tree(articles: list) -> tuple[list, dict]:
    """Split articles into (root_articles, tree): root_articles have no
    folder (rendered directly, unlabeled -- so a library that's never used
    folders looks exactly like it did before this feature existed); tree is
    a nested dict keyed by path segment, {"path": "A/B", "articles": [...],
    "children": {...}}, one level per "/" in `folder`. There's no separate
    folders table (see db.py's list_folders docstring), so this tree is
    rebuilt from the articles' own `folder` values every render -- cheap at
    personal-library scale, and it means a folder can never exist here
    without also being reachable via at least one real article."""
    root_articles = []
    tree: dict = {}
    for a in articles:
        if not a.folder:
            root_articles.append(a)
            continue
        level = tree
        node = None
        path_so_far = []
        for seg in a.folder.split("/"):
            path_so_far.append(seg)
            node = level.setdefault(seg, {"path": "/".join(path_so_far), "articles": [], "children": {}})
            level = node["children"]
        node["articles"].append(a)
    return root_articles, tree


def _count_descendants(children: dict) -> int:
    return sum(len(n["articles"]) + _count_descendants(n["children"]) for n in children.values())


def _all_created_ats(node: dict) -> list[str]:
    """created_at of every article anywhere in this folder's subtree (ISO
    8601 UTC strings -- see db.py's _now() -- so plain string min/max already
    sorts correctly, no parsing needed)."""
    dates = [a.created_at for a in node["articles"] if a.created_at]
    for child in node["children"].values():
        dates.extend(_all_created_ats(child))
    return dates


def _sorted_folder_entries(items, sort: str) -> list:
    """Order a folder level (siblings at the same depth) the same way the
    "Sort by" control orders articles, recursively -- so under "Recently
    added" the folder holding the newest article floats up too, not just
    the articles inside it once you open it. Title sorts order folders by
    their own name (case-insensitively, ascending/descending to match);
    "recent"/"oldest" order by the most/least recent created_at anywhere in
    that folder's subtree, since a folder has no created_at of its own."""
    entries = list(items)
    if sort in ("title_asc", "title_desc"):
        return sorted(entries, key=lambda kv: kv[0].lower(), reverse=(sort == "title_desc"))
    is_oldest = sort == "oldest"
    default = "9999" if is_oldest else ""
    return sorted(
        entries,
        key=lambda kv: (min if is_oldest else max)(_all_created_ats(kv[1]), default=default),
        reverse=not is_oldest,
    )


def _sort_articles(articles: list, sort: str) -> list:
    """Python-side equivalent of db.py's SORT_OPTIONS, since a single SQL
    query can't give different folders different orders -- this is what
    lets each folder's *own* effective sort (inherited or overridden, see
    _render_folder_node) actually take effect on its direct articles."""
    if sort == "title_asc":
        return sorted(articles, key=lambda a: (a.title or "").lower())
    if sort == "title_desc":
        return sorted(articles, key=lambda a: (a.title or "").lower(), reverse=True)
    if sort == "oldest":
        return sorted(articles, key=lambda a: a.created_at or "")
    return sorted(articles, key=lambda a: a.created_at or "", reverse=True)  # "recent" (default/fallback)


def _html_id(s: str) -> str:
    """A folder path ("Notes/Work") into something safe to use as an HTML
    id/popovertarget pair -- "/" is technically legal in an id, but not
    worth the risk given how much else (CSS, querySelector) treats it
    specially elsewhere in this app."""
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", s)


def _folder_sort_select(path: str, inherited_sort: str, overrides: dict) -> Select:
    override = overrides.get(path)
    inherited_label = SORT_OPTIONS.get(inherited_sort, SORT_OPTIONS[DEFAULT_SORT])[0]
    options = [Option(f"Default ({inherited_label})", value="inherit", selected=override is None)]
    options += [
        Option(label, value=key, selected=(override == key))
        for key, (label, _) in SORT_OPTIONS.items()
    ]
    return Select(*options, name="sort", cls="folder-sort-select", title="Sort just this folder")


def _render_folder_node(name: str, node: dict, all_folders: list[str], inherited_sort: str, overrides: dict, stats: dict) -> Details:
    # A folder holding nothing but a single subfolder (e.g. an import's
    # "markdown_output/Book Title" wrapper) is shown as one combined row,
    # "markdown_output / Book Title", rather than two levels of nesting for
    # one item. Actions (rename/delete/sort) then apply to the deepest one.
    while not node["articles"] and len(node["children"]) == 1:
        child_name, node = next(iter(node["children"].items()))
        name = f"{name} / {child_name}"

    # Each folder's *own* effective sort: its explicit override if it has
    # one, else whatever it inherits from its nearest ancestor (ultimately
    # the global "Sort by" at the root) -- passed down as `inherited_sort`
    # for descendants that don't have their own override either.
    my_sort = overrides.get(node["path"], inherited_sort)
    total = len(node["articles"]) + _count_descendants(node["children"])
    rows = [_article_row(a, all_folders, stats) for a in _sort_articles(node["articles"], my_sort)]
    children = [
        _render_folder_node(child_name, child, all_folders, my_sort, overrides, stats)
        for child_name, child in _sorted_folder_entries(node["children"].items(), my_sort)
    ]
    menu_id = f"folder-menu-{_html_id(node['path'])}"
    return Details(
        Summary(
            Span("", cls="folder-chevron", aria_hidden="true"),
            Span(name, cls="folder-name"),
            Span(str(total), cls="folder-count", title=f"{total} article{'s' if total != 1 else ''}"),
            Button(
                "⋯", type="button", cls="kebab-btn",
                popovertarget=menu_id, aria_label=f"Actions for folder {name}",
            ),
        ),
        # Deliberately a *sibling* of <summary>, not nested inside it: a
        # popover's content still bubbles click events through its DOM
        # ancestors even though it's painted in the top layer, so anything
        # inside here would need the same click-toggles-details guard as
        # the trigger button otherwise.
        Div(
            Form(
                Label("Sort", _folder_sort_select(node["path"], inherited_sort, overrides), cls="popover-field"),
                Input(type="hidden", name="folder", value=node["path"]),
                method="post", action="/folders/sort", cls="folder-sort-form",
            ),
            Button("Rename", type="button", cls="popover-item folder-rename-btn", data_folder_path=node["path"]),
            Button(
                "Delete", type="button", cls="popover-item popover-item-danger folder-delete-btn",
                data_folder_path=node["path"], data_folder_count=str(total),
                title="Permanently deletes this folder's articles (and cached audio) -- cannot be undone",
            ),
            id=menu_id, popover="auto", cls="popover-menu",
        ),
        Div(*children, *rows, cls="folder-contents"),
        # Collapsed by default; library.js reopens whichever folders this
        # browser last had open (and opens matching ones while searching).
        cls="folder-group",
        data_folder_path=node["path"],
    )


def _sort_form(sort: str) -> Form:
    options = [Option(label, value=key, selected=(key == sort)) for key, (label, _) in SORT_OPTIONS.items()]
    return Form(
        Label(Span("Sort by", cls="sort-label"), Select(*options, name="sort", id="sort-select")),
        method="get", action="/", id="sort-form", cls="sort-form",
    )


def library_page(
    articles: list, lan_url: str | None = None, notice: str | None = None,
    sort: str = DEFAULT_SORT, folder_sort_overrides: dict | None = None,
    update_available: str | None = None, stats: dict | None = None,
) -> Html:
    folder_sort_overrides = folder_sort_overrides or {}
    stats = stats or {}
    has_folders = any(a.folder for a in articles)
    if not articles:
        body = Div(
            P("Your library is empty."),
            A("Add your first article", href="/add", cls="btn btn-primary"),
            P("Or drop a .md, .txt or .pdf file anywhere on this page.", cls="form-hint"),
            cls="empty-state",
        )
    else:
        # `articles` is already ordered per the global `sort` (db.list_articles);
        # folder bucketing below (_build_folder_tree) preserves that order
        # within each bucket, so it applies inside every folder too by
        # default -- unless a folder (or an ancestor of it) has its own
        # explicit override in `folder_sort_overrides`, in which case
        # _render_folder_node re-sorts that folder's articles/order in
        # Python and passes its effective sort down as the inherited
        # default for its own children.
        all_folders = sorted({a.folder for a in articles if a.folder})
        root_articles, tree = _build_folder_tree(articles)
        sections = []

        in_progress = [
            a for a in articles
            if a.last_segment_index is not None and a.last_segment_index >= 0
            and not (stats.get(a.id) and stats[a.id].finished)
        ]
        in_progress.sort(key=lambda a: (a.last_played_at or "", a.created_at or ""), reverse=True)
        if in_progress:
            sections.append(Section(
                H2("Continue listening", cls="library-section-title"),
                Div(*[_article_row(a, all_folders, stats, show_folder=True) for a in in_progress[:_CONTINUE_LIMIT]],
                    cls="article-list"),
                cls="library-section", id="continue-section",
            ))
        if tree:
            sections.append(Section(
                Div(
                    H2("Folders", cls="library-section-title"),
                    Button("Expand all", type="button", cls="link-btn", id="expand-all-folders"),
                    Button("Collapse all", type="button", cls="link-btn", id="collapse-all-folders"),
                    cls="library-section-head",
                ),
                *[
                    _render_folder_node(name, node, all_folders, sort, folder_sort_overrides, stats)
                    for name, node in _sorted_folder_entries(tree.items(), sort)
                ],
                cls="library-section",
            ))
        if root_articles:
            sections.append(Section(
                H2("Articles", cls="library-section-title") if has_folders or in_progress else "",
                Div(*[_article_row(a, all_folders, stats) for a in root_articles], cls="article-list"),
                cls="library-section",
            ))
        sections.append(P("No articles match your search.", id="search-empty", cls="empty-state", hidden=True))
        body = Div(*sections, id="library-body")

    notice_banner = Div(notice, cls="notice-banner") if notice else ""
    update_banner = (
        Div(
            Span(f"{APP_NAME} v{update_available} is available "),
            A("see what's new", href=release_url(update_available), target="_blank", rel="noopener"),
            Span(f" (you're on v{APP_VERSION})."),
            cls="update-banner",
        )
        if update_available else ""
    )
    toolbar = (
        Div(
            Input(
                type="search", id="library-search", placeholder="Search library",
                aria_label="Search library", autocomplete="off",
            ),
            _sort_form(sort),
            cls="library-toolbar",
        )
        if articles else ""
    )

    return Html(
        _head(f"Library — {APP_NAME}"),
        Body(
            _nav(lan_url),
            Main(
                H1("Library", cls="visually-hidden"),
                update_banner, notice_banner, toolbar, _lan_line(lan_url), body,
                Div(
                    Div("Drop files to add them", cls="drop-overlay-title"),
                    Div("", cls="drop-overlay-target"),
                    id="drop-overlay", hidden=True,
                ),
                cls="container",
            ),
        ),
    )


_CONTINUE_LIMIT = 5


@dataclass
class ArticleStats:
    """Per-article numbers for the library row, computed in app.py."""
    minutes: float                 # whole article at 1.0x
    progress: float | None = None  # 0-1, None if never played
    minutes_left: float | None = None
    finished: bool = False


def _fmt_minutes(minutes: float) -> str:
    m = round(minutes)
    if m < 1:
        return "<1 min"
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h {m % 60} min" if m % 60 else f"{m // 60} h"


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return iso[:10]
    fmt = "%b %-d" if d.year == datetime.now(timezone.utc).year else "%b %-d, %Y"
    return d.strftime(fmt)


def _lan_line(lan_url: str | None):
    """One slim line with the address other devices on the network can use.
    app.py only passes lan_url when you're browsing on the server machine
    itself -- elsewhere you're already on that address."""
    if not lan_url:
        return ""
    return Div(
        Span("Open on your phone or another computer:"),
        A(lan_url, href=lan_url, cls="lan-url-link"),
        Button("Copy", type="button", cls="link-btn copy-lan-url", data_url=lan_url),
        cls="lan-line",
    )


def _reader_source(a):
    """Under the article title: a link to the original for web articles
    (shown as just its site), else the uploaded filename."""
    domain = _source_domain(a)
    if domain:
        return A(f"{domain} ↗", href=a.original_filename, cls="reader-source",
                 target="_blank", rel="noopener noreferrer", title=a.original_filename)
    if a.original_filename:
        return Span(a.original_filename, cls="reader-source")
    return ""


def _source_domain(a) -> str:
    """original_filename doubles as the source URL for "url" articles."""
    if a.source_type != "url" or not a.original_filename:
        return ""
    host = urlparse(a.original_filename).hostname or ""
    return host.removeprefix("www.")


def _folder_move_form(a, all_folders: list[str]) -> Form:
    options = [Option("— No folder —", value="", selected=not a.folder)]
    options += [Option(f, value=f, selected=(a.folder == f)) for f in all_folders]
    options.append(Option("+ New folder…", value="__new__"))
    return Form(
        Label("Move to", Select(*options, cls="folder-select", title="Move to folder"), cls="popover-field"),
        Input(type="hidden", name="folder", value=a.folder or ""),
        method="post",
        action=f"/article/{a.id}/move",
        cls="folder-move-form",
    )


def _article_row(a, all_folders: list[str] | None = None, stats: dict | None = None, show_folder: bool = False) -> Div:
    st = (stats or {}).get(a.id)
    domain = _source_domain(a)
    # Most useful first, since the line is cut off with "…" on narrow screens.
    meta = []
    if st:
        if st.progress is not None and not st.finished:
            meta.append(f"{round(st.progress * 100)}% · {_fmt_minutes(st.minutes_left)} left")
        elif st.finished:
            meta.append("Finished")
        else:
            meta.append(_fmt_minutes(st.minutes))
    if domain:
        meta.append(domain)
    if show_folder:
        # "Continue listening" mixes articles from everywhere: name the
        # folder (just its last part) instead of the date.
        if a.folder:
            meta.append(a.folder.rsplit("/", 1)[-1])
    else:
        meta.append(_fmt_date(a.created_at))
    progress_bar = ""
    if st and st.progress is not None:
        pct = 100 if st.finished else round(st.progress * 100)
        progress_bar = Div(Div(cls="progress-fill", style=f"width:{pct}%"), cls="progress-track", aria_hidden="true")

    menu_id = f"article-menu-{a.id}"
    original = (
        A("Open original", href=a.original_filename, target="_blank", rel="noopener noreferrer", cls="popover-item")
        if domain else ""
    )
    search_text = " ".join(filter(None, [a.title or "", domain, a.folder or "", a.original_filename or ""])).lower()
    return Div(
        A(
            Span(a.title or "Untitled", cls="article-title"),
            Span(" · ".join(m for m in meta if m), cls="article-meta", title=a.folder or None),
            progress_bar,
            href=f"/article/{a.id}", cls="article-link",
        ),
        Button(
            "⋯", type="button", cls="kebab-btn",
            popovertarget=menu_id, aria_label="Article actions",
        ),
        Div(
            original,
            _folder_move_form(a, all_folders or []),
            Button(
                "Delete", type="button", cls="popover-item popover-item-danger",
                data_delete_id=str(a.id),
            ),
            id=menu_id, popover="auto", cls="popover-menu",
        ),
        cls="article-row",
        data_search=search_text,
    )


def _folder_field() -> Label:
    return Label(
        "Folder (optional)",
        Input(name="folder", type="text", list="folder-datalist", placeholder="e.g. Notes/Work"),
    )


def add_article_page(url: str = "", error: str = "", autofetch: bool = False, folders: list[str] | None = None) -> Html:
    folder_datalist = Datalist(*[Option(value=f) for f in (folders or [])], id="folder-datalist")
    url_form = Form(
        Label(
            "Page URL",
            Input(
                name="url", type="url", value=url,
                placeholder="https://example.com/some-article",
                required=True, autocapitalize="off", autocorrect="off", spellcheck="false",
                autofocus=bool(url) or None,
            ),
        ),
        Label(
            Input(name="use_page_title", type="checkbox", checked=True),
            " Use the page's title",
            cls="checkbox-label",
        ),
        _folder_field(),
        Button("Fetch & add", type="submit", cls="btn btn-primary"),
        P(
            "Fetched with defuddle.md, falling back to Jina AI's reader if that fails.",
            cls="form-hint",
        ),
        method="post",
        action="/articles/url",
        id="url-add-form",
        cls="add-form",
    )
    paste_form = Form(
        Label("Title (optional)", Input(name="title", type="text", placeholder="Derived from content if left blank")),
        Label("Markdown", Textarea(name="markdown", rows=16, placeholder="Paste or write markdown here...", required=True)),
        _folder_field(),
        Button("Add to library", type="submit", cls="btn btn-primary"),
        method="post",
        action="/articles",
        cls="add-form",
    )
    upload_form = Form(
        Label(
            "File (.md, .markdown, .txt, or .pdf)",
            Div(
                Input(name="file", type="file", accept=".md,.markdown,.txt,.pdf", required=True),
                Span("Drop a file here, or tap to browse", cls="file-drop-hint"),
                Span("", cls="file-drop-name", hidden=True),
                cls="file-dropzone",
            ),
        ),
        Label(
            Input(name="use_filename_as_title", type="checkbox", checked=True),
            " Use file name as title",
            cls="checkbox-label",
        ),
        _folder_field(),
        Button("Upload", type="submit", cls="btn btn-primary"),
        method="post",
        action="/articles/upload",
        enctype="multipart/form-data",
        cls="add-form",
    )
    folder_upload_form = Form(
        Label(
            "Folder",
            Div(
                Input(name="folder_files", type="file", webkitdirectory=True, multiple=True, required=True, id="folder-upload-input"),
                Span("Tap to choose a folder", cls="file-drop-hint"),
                Span("", cls="file-drop-name", hidden=True),
                cls="file-dropzone",
            ),
        ),
        Label(
            "Folder name in library (optional)",
            Input(name="folder_prefix", type="text", list="folder-datalist", id="folder-prefix-input",
                  placeholder="Auto-filled from the picked folder's name"),
        ),
        Button("Upload folder", type="submit", cls="btn btn-primary"),
        P(
            "Subfolders are preserved. Unsupported files (anything but "
            ".md/.markdown/.txt/.pdf) are skipped.",
            cls="form-hint",
        ),
        method="post",
        action="/articles/upload-folder",
        enctype="multipart/form-data",
        id="folder-upload-form",
        cls="add-form",
    )
    error_banner = Div(error, cls="add-error") if error else ""
    autofetch_script = (
        Script(NotStr(
            "document.getElementById('url-add-form').submit();"
        ))
        if autofetch and url and not error else ""
    )
    return Html(
        _head(f"Add article — {APP_NAME}"),
        Body(
            _nav(),
            Main(
                H1("Add an article"),
                error_banner,
                folder_datalist,
                Details(Summary("Add from a link"), url_form, open=True),
                Details(Summary("Paste markdown"), paste_form, open=not url),
                Details(Summary("Upload a file"), upload_form),
                Details(Summary("Upload a folder"), folder_upload_form),
                cls="container",
            ),
            autofetch_script,
        ),
    )


def edit_article_page(article) -> Html:
    form = Form(
        Label("Title", Input(name="title", type="text", value=article.title or "")),
        Label("Markdown", Textarea(article.markdown, name="markdown", rows=20, required=True)),
        Button("Save changes", type="submit", cls="btn btn-primary"),
        method="post",
        action=f"/article/{article.id}/edit",
        cls="add-form",
    )
    return Html(
        _head(f"Edit {article.title or 'Untitled'} — {APP_NAME}"),
        Body(
            _nav(),
            Main(
                H1(f"Edit: {article.title or 'Untitled'}"),
                P(
                    "Saving will reset your reading progress for this article and "
                    "regenerate audio on next play (edited content gets a fresh cache).",
                    cls="edit-note",
                ),
                form,
                cls="container",
            ),
        ),
    )


def toc_sidebar(toc: list):
    if not toc:
        return Nav(cls="toc-sidebar")
    items = [
        Button(
            entry.text,
            cls=f"toc-entry toc-level-{entry.level}",
            data_jump=str(entry.segment_index),
        )
        for entry in toc
    ]
    # A <details> rather than a plain <nav>: on desktop it's styled to look
    # identical to the old always-expanded sidebar, but on narrow screens
    # player.js collapses it at load, so a long table of contents doesn't
    # push the article itself below the fold -- tapping "Contents"
    # expands/collapses it like the add-article forms' <details> already do.
    # The entries are wrapped in their own .toc-list flex column rather than
    # relying on <details> to lay out its own children: modern browsers wrap
    # everything after <summary> in an internal anonymous box, so a `display:
    # flex` on the <details> itself only flexes [summary, that one wrapper]
    # -- the buttons inside it then fell back to native inline-block flow
    # and packed side-by-side like wrapped text instead of stacking.
    return Details(Summary("Contents"), Div(*items, cls="toc-list"), open=True, cls="toc-sidebar")


def player_bar(voice: str, speed: float) -> Div:
    speed_buttons = [
        Button(
            f"{s}x",
            cls="speed-btn" + (" active" if s == speed else ""),
            data_speed=str(s),
        )
        for s in SPEEDS
    ]
    voice_options = [
        Option(f"{v['name']} ({v['language']})", value=v["id"], selected=(v["id"] == voice))
        for v in VOICES
    ]
    return Div(
        Div(
            Span(
                "0:00", id="doc-elapsed", cls="playhead-time",
                title="Elapsed across the whole article",
            ),
            Input(
                type="range", id="doc-seek", min="0", max="0", step="0.01", value="0",
                cls="doc-seek", disabled=True,
                aria_label="Jump to a sentence anywhere in the article",
                title="Drag to jump to a sentence anywhere in the article",
            ),
            Span(
                "0:00", id="doc-duration", cls="playhead-time",
                title="Estimated total article duration (refines as more of it is generated)",
            ),
            cls="playhead-row",
        ),
        Div(
            Span(
                "0:00", id="playhead-elapsed", cls="playhead-time",
                title="Elapsed in this sentence",
            ),
            Input(
                type="range", id="playhead-seek", min="0", max="0", step="0.01", value="0",
                cls="playhead-seek", disabled=True, aria_label="Seek within current sentence",
                title="Seek within the current sentence",
            ),
            Span(
                "0:00", id="playhead-duration", cls="playhead-time",
                title="Duration of this sentence",
            ),
            cls="playhead-row",
        ),
        Div(
            Button("⏮", id="btn-skip-back", title="Previous sentence (←)"),
            Button("▶", id="btn-play-pause", title="Play/Pause (Space)"),
            Button("⏹", id="btn-stop", title="Stop"),
            Button("⏭", id="btn-skip-forward", title="Next sentence (→)"),
            Button("📍", id="btn-jump-to-current", title="Scroll to currently playing sentence"),
            cls="transport-row",
        ),
        Div(
            Div(*speed_buttons, cls="speed-row", id="speed-row"),
            Select(*voice_options, id="voice-select"),
            cls="settings-row",
        ),
        id="player-bar",
        cls="player-bar",
    )


def article_page(article, body_html: str, toc: list) -> Html:
    resume_banner = Div(
        Span("Continue from where you left off?"),
        Button("Resume", id="btn-resume", cls="btn btn-sm btn-primary"),
        Button("Dismiss", id="btn-dismiss-resume", cls="btn btn-sm"),
        id="resume-banner",
        cls="resume-banner",
        style="display:none",
    )
    voice = article.last_voice or DEFAULT_VOICE
    speed = article.last_speed or DEFAULT_SPEED
    return Html(
        _head(f"{article.title or 'Untitled'} — {APP_NAME}"),
        Body(
            _nav(),
            Div(
                toc_sidebar(toc),
                Main(
                    Div(
                        Div(
                            H1(article.title or "Untitled"),
                            _reader_source(article),
                        ),
                        Div(
                            Button(
                                "\U0001F3A7 Audio only", id="audio-only-toggle", type="button",
                                cls="btn btn-sm", title="Hide the article text, just show playback",
                            ),
                            A("Edit", href=f"/article/{article.id}/edit", cls="btn btn-sm"),
                            cls="reader-header-actions",
                        ),
                        cls="reader-header",
                    ),
                    resume_banner,
                    Div(
                        Div("Nothing playing yet", id="now-playing-text"),
                        id="now-playing-panel",
                    ),
                    Div(NotStr(body_html), id="doc-body", cls="doc-body"),
                    cls="container reader-main",
                ),
                cls="reader-layout",
            ),
            player_bar(voice, speed),
            Audio(
                id="ios-audio-unlock",
                src=SILENT_WAV_DATA_URI,
                loop=True,
                playsinline=True,
                preload="auto",
                style="display:none",
            ),
            Script(
                NotStr(
                    f"window.ARTICLE_ID = {article.id};\n"
                    f"window.LAST_SEGMENT_INDEX = {article.last_segment_index if article.last_segment_index is not None else -1};\n"
                    f"window.INITIAL_VOICE = {voice!r};\n"
                    f"window.INITIAL_SPEED = {speed!r};\n"
                )
            ),
        ),
    )
