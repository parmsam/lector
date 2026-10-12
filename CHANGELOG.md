# Changelog

All notable changes to Lector are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

Add each change under **Unreleased** as it lands. When cutting a release,
rename that section to the new version and date, bump `pyproject.toml`, and
use the section as the GitHub release notes.

## [Unreleased]

### Changed
- Library redesigned to be calmer and more compact: one line per article
  (title plus a short detail line) instead of a bordered card, and folders
  as a simple collapsible list instead of boxes inside boxes.
- Each article shows its listening time, its source site for web articles,
  and a short date. The full URL moved to the article's ⋯ menu as
  "Open original".
- Folders start collapsed, and the library remembers which ones you opened.
  A folder that only holds one subfolder is shown as a single combined row.
- The version is a pill next to the Lector name (linking to that release's
  notes), with a GitHub button beside it; "Check for updates", the changelog
  and the repo link are in a ⋯ menu in the top bar.
  On the server machine itself, the network address for opening Lector on
  your phone is now one slim line under the search box (and in that menu).

### Added
- **Continue listening** section at the top of the library with the
  articles you're partway through, most recently played first.
- Progress bar and "% · time left" on every article you've started.
- Search box that filters the whole library, including inside folders, as
  you type. Press `/` to jump to it and `Esc` to clear it.
- Drag and drop files onto the library to add them, or drop them onto a
  folder to add them there.
- The table of contents follows playback: the section being read is
  highlighted (and kept in view in a long list). On phones, where the
  contents start collapsed, the current section is named next to
  "Contents".
- Sentences get a light tint on hover to show you can click them to start
  reading there, and first-time readers see a one-line tip saying so.
- A sentence pulses while its audio is still being generated, so the wait
  doesn't look like a hang.

### Fixed
- "Recently added" sorting showed the oldest articles first.

## [1.1.0] - 2026-10-12

### Added
- Markdown tables render as real tables, and each row is read aloud.
- Headings get word-by-word highlighting, like paragraphs.
- Check-for-updates banner on the library page, plus a manual
  "Check for updates" link in the top bar.
- Expand all / Collapse all buttons for folders.

### Changed
- App version shown in the top bar instead of the library footer.

### Fixed
- Bold text and headings are read sentence by sentence. A heading with its
  body directly underneath used to be read as one long chunk.
- Bold or highlighted text that spans several sentences keeps its
  formatting on each sentence.
- Stray `**` no longer shows around bold punctuation from some ebook
  conversions.
- Cached audio is checked against its sentence text, so a change in how
  articles are split can't play the wrong sentence's audio.

## [1.0.0] - 2026-07-30

First tagged release of the rewrite as a network-accessible web app.

### Added
- Personal article library (paste markdown, upload .md/.txt/PDF, or add by
  URL) backed by SQLite, with nested folders and per-folder sorting.
- Kokoro TTS playback with real-time sentence and word highlighting, a
  seekable whole-article playhead, and speeds from 0.5x to 2.5x.
- Table of contents with click-to-jump, and click any sentence to jump there.
- Reading progress (position, voice, speed) saved per article and shared
  across every device on your network.
- Mobile support: Add to Home Screen, Android/iOS share target for adding
  links, light/dark theme.

[Unreleased]: https://github.com/parmsam/markdown-reader2/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/parmsam/markdown-reader2/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/parmsam/markdown-reader2/releases/tag/v1.0.0
