// Vanilla-JS read-aloud player. Ports the design proven in v1's usePlayer.ts
// (Tauri/React) to a plain browser client talking to this app's HTTP API
// instead of Tauri's invoke() IPC. See LEARNINGS.md for why each piece exists.
(function () {
  "use strict";
  if (typeof window.ARTICLE_ID === "undefined") return; // not an article page

  const ARTICLE_ID = window.ARTICLE_ID;
  const LOOKAHEAD = 2;
  // While the page is hidden (other tab/app, locked screen) nobody's tapping
  // around the document, so prefetch further ahead: a gap waiting on Kokoro
  // between sentences is what risks iOS dropping the background audio session.
  const HIDDEN_LOOKAHEAD = 6;
  const AUTO_SCROLL_IDLE_MS = 2500;
  // Read from the rendered speed buttons rather than hardcoding a second
  // copy of components.py's SPEEDS list here (used by the [ / ] shortcuts).
  const SPEEDS = Array.from(document.querySelectorAll(".speed-btn")).map((b) => parseFloat(b.dataset.speed));

  // On narrow screens the TOC stacks above the article (see style.css's
  // 900px breakpoint), so a long table of contents would push the article
  // itself below the fold -- collapse the <details> at load there. Desktop
  // keeps the server-rendered `open` (a sticky, always-expanded sidebar).
  // Progressive enhancement: with JS disabled it just stays expanded.
  const tocDetails = document.querySelector(".toc-sidebar");
  if (tocDetails && tocDetails.tagName === "DETAILS" && window.matchMedia("(max-width: 900px)").matches) {
    tocDetails.open = false;
  }

  // Keep the article's bottom padding matched to the *actual* rendered
  // height of the fixed player bar (see style.css's --player-bar-space).
  // That height isn't constant -- the settings row wraps to two lines on
  // narrow viewports, a long voice name, or larger browser font/zoom -- so a
  // fixed CSS guess could under-reserve space and let the bar cover the
  // article's last lines. ResizeObserver catches every case that changes
  // the bar's height, not just the viewport widths a breakpoint anticipates.
  const playerBarEl = document.getElementById("player-bar");
  if (playerBarEl && "ResizeObserver" in window) {
    const updatePlayerBarSpace = () => {
      document.documentElement.style.setProperty("--player-bar-space", `${playerBarEl.offsetHeight}px`);
    };
    new ResizeObserver(updatePlayerBarSpace).observe(playerBarEl);
  }

  // ---- DOM: collect every segment element once, indexed by its data-seg ----
  const segEls = [];
  const segTypes = [];
  document.querySelectorAll("[data-seg]").forEach((el) => {
    const idx = parseInt(el.getAttribute("data-seg"), 10);
    segEls[idx] = el;
    segTypes[idx] = el.getAttribute("data-type");
  });
  const totalSegments = segEls.length;

  // ---- the one media element all playback goes through ----
  // A real <audio> element, not the Web Audio API: iOS Safari suspends an
  // AudioContext as soon as the page is hidden, but keeps a playing media
  // element going in the background, and only media elements get lock-screen
  // / Control Center controls via the Media Session API (see below). Its
  // server-rendered src is a tiny silent WAV (components.py's
  // SILENT_WAV_DATA_URI), reused by holdAudioSession().
  const audioEl = document.getElementById("player-audio");
  const SILENT_SRC = audioEl.getAttribute("src");
  const hasMediaSession = "mediaSession" in navigator;

  // ---- state ----
  let loadedSegment = -1; // segment whose audio is in audioEl (-1: none / silence)
  let segmentEndHandler = null; // what audioEl's "ended" does next -- see startAudio()
  const cacheMap = new Map(); // segmentIndex -> {url (blob: WAV), wordTimings, duration}
  const pending = new Map(); // segmentIndex -> in-flight fetch Promise (see fetchSegment)
  let gen = 0; // monotonic generation counter -- see playSegment/startAudio
  let currentSegment = -1;
  let currentWordEl = null;
  let currentWordIdx = -1;
  let playing = false;
  let voice = window.INITIAL_VOICE || "af_heart";
  let speed = window.INITIAL_SPEED || 1.0;
  let userScrolling = false;
  let userScrollTimer = null;
  // Playhead: elapsed time within the current segment is just
  // audioEl.currentTime (each segment is its own src).
  let segmentDuration = 0;
  let playheadDragging = false;

  // ---- document-wide duration estimate, for the playhead's elapsed/total
  // labels (see docElapsedAndTotal below). Audio is generated lazily, one
  // segment at a time -- there's no whole-document duration to know without
  // either generating every segment upfront (slow for a long article) or
  // estimating. Word-count-based estimate per segment, refined to the real
  // duration as each one actually gets generated; recordRealDuration also
  // calibrates the words/sec rate itself from that real data, so later
  // not-yet-generated estimates get more accurate as you listen. ----
  const DEFAULT_WORDS_PER_SECOND = 2.5; // ~150 wpm at 1.0x, typical narration pace
  let observedBaseWordsPerSecond = null; // calibrated from the first real segment we see
  const segmentDurationIsReal = segEls.map(() => false);

  function wordCountOf(index) {
    if (segTypes[index] === "code" || !segEls[index]) return 0;
    return (segEls[index].textContent.match(/\S+/g) || []).length;
  }

  function estimateDuration(words) {
    const baseWps = observedBaseWordsPerSecond || DEFAULT_WORDS_PER_SECOND;
    return words / baseWps / speed;
  }

  const segmentDurations = segEls.map((_, i) => estimateDuration(wordCountOf(i)));

  function recordRealDuration(index, realDuration) {
    segmentDurations[index] = realDuration;
    segmentDurationIsReal[index] = true;
    const words = wordCountOf(index);
    if (words > 0 && realDuration > 0) observedBaseWordsPerSecond = (words / realDuration) * speed;
  }

  function recomputeEstimatesForCurrentSpeed() {
    for (let i = 0; i < segmentDurations.length; i++) {
      if (!segmentDurationIsReal[i]) segmentDurations[i] = estimateDuration(wordCountOf(i));
    }
  }

  function docElapsedAndTotal(withinSegElapsed) {
    let elapsedBefore = 0;
    for (let i = 0; i < currentSegment; i++) elapsedBefore += segmentDurations[i] || 0;
    const total = segmentDurations.reduce((a, b) => a + (b || 0), 0);
    return { elapsed: elapsedBefore + Math.max(0, withinSegElapsed), total };
  }

  // Which segment a document-wide time target falls in -- "jump to a chunk"
  // only needs a segment index (jumpTo() already generates-on-demand and
  // plays whatever segment you jump to, exactly like clicking a TOC entry or
  // a paragraph does), not a precise mid-segment offset. Walks cumulative
  // estimated/real durations rather than segment *count*, so the position
  // roughly tracks actual speaking time even though segments vary in length.
  function segmentIndexAtTime(targetSeconds) {
    let acc = 0;
    for (let i = 0; i < segmentDurations.length; i++) {
      acc += segmentDurations[i] || 0;
      if (targetSeconds <= acc) return i;
    }
    return Math.max(0, segmentDurations.length - 1);
  }

  function lookahead() {
    return document.hidden ? HIDDEN_LOOKAHEAD : LOOKAHEAD;
  }

  // ---- driving audioEl ----
  // iOS only lets a media element play() from a user gesture until it has
  // played once; after that the same element can be play()ed from anywhere
  // (async fetch callbacks, "ended" handlers, lock-screen controls). Every
  // path that starts playback reaches audioEl.play() or holdAudioSession()
  // synchronously from its click/keydown, so the first gesture unlocks it.
  function playAudioEl() {
    audioEl.play().catch((e) => {
      // AbortError just means src changed mid-play (a newer segment won).
      if (e.name === "NotAllowedError") pause();
    });
  }

  function startAudio(index, entry, offset, myGen) {
    audioEl.loop = false;
    if (loadedSegment !== index || audioEl.getAttribute("src") !== entry.url) {
      audioEl.src = entry.url;
      loadedSegment = index;
    }
    if (offset > 0) {
      if (audioEl.readyState >= 1) audioEl.currentTime = offset;
      else audioEl.addEventListener("loadedmetadata", () => { audioEl.currentTime = offset; }, { once: true });
    } else if (audioEl.currentTime !== 0) {
      audioEl.currentTime = 0;
    }
    segmentDuration = entry.duration;
    currentWordIdx = -1;
    segmentEndHandler = () => {
      if (gen === myGen) playSegment(index + 1, myGen);
    };
    playAudioEl();
    updateMediaPositionState(offset);
  }

  // While the next sentence is still being generated, loop silence instead
  // of letting audioEl go idle: a paused/ended element in a hidden page is
  // how iOS decides the page is done playing and suspends it mid-article.
  function holdAudioSession() {
    segmentEndHandler = null;
    loadedSegment = -1;
    audioEl.loop = true;
    if (audioEl.getAttribute("src") !== SILENT_SRC) audioEl.src = SILENT_SRC;
    playAudioEl();
  }

  audioEl.addEventListener("ended", () => {
    const next = segmentEndHandler;
    segmentEndHandler = null;
    if (next) next();
  });
  // A segment's audio failing to load/decode: skip it, same as a failed fetch.
  audioEl.addEventListener("error", () => {
    if (loadedSegment < 0) return;
    console.error(`Audio playback error for segment ${loadedSegment}`, audioEl.error);
    const next = segmentEndHandler;
    segmentEndHandler = null;
    if (next) next();
  });

  // ---- fetch + cache (in-memory, per-page; separate from the server disk cache:
  // this one saves a redundant HTTP round-trip within one page session, the disk
  // cache saves the actual TTS generation across sessions/devices) ----
  function fetchSegment(index) {
    if (index < 0 || index >= totalSegments) return Promise.resolve();
    if (cacheMap.has(index)) return Promise.resolve();
    if (segTypes[index] === "code") return Promise.resolve(); // never spoken
    // If this segment is already being fetched (e.g. lookahead prefetch kicked it
    // off, and playSegment() now needs the same segment right away), return the
    // SAME in-flight promise rather than just checking-and-bailing -- otherwise a
    // caller awaiting this call would resolve immediately while the real fetch is
    // still pending, see an empty cache, and wrongly treat the segment as
    // unplayable (this cascaded through an entire document in milliseconds during
    // manual testing before the fix).
    if (pending.has(index)) return pending.get(index);

    const promise = (async () => {
      try {
        const qs = `?voice=${encodeURIComponent(voice)}&speed=${speed}`;
        const [audioResp, timingsResp] = await Promise.all([
          fetch(`/api/tts/${ARTICLE_ID}/${index}${qs}`),
          fetch(`/api/tts/${ARTICLE_ID}/${index}/timings${qs}`),
        ]);
        if (!audioResp.ok || !timingsResp.ok) throw new Error("tts fetch failed");
        const blob = await audioResp.blob();
        const timings = await timingsResp.json();
        cacheMap.set(index, { url: URL.createObjectURL(blob), wordTimings: timings.word_timings, duration: timings.duration });
        recordRealDuration(index, timings.duration);
      } catch (e) {
        console.error(`TTS error for segment ${index}:`, e);
      } finally {
        pending.delete(index);
      }
    })();
    pending.set(index, promise);
    return promise;
  }

  // Nulling segmentEndHandler first keeps the stopped segment from also
  // (wrongly) advancing to the next one on its own.
  function stopAudio() {
    segmentEndHandler = null;
    audioEl.pause();
  }

  // Voice/speed changed: every cached segment is for the old settings.
  function clearSegmentCache() {
    for (const entry of cacheMap.values()) URL.revokeObjectURL(entry.url);
    cacheMap.clear();
    loadedSegment = -1;
  }

  // ---- word / sentence highlighting ----
  function setWordSpans(el) {
    if (el.dataset.wordsRendered) return;
    const words = JSON.parse(el.getAttribute("data-words") || "[]");
    el.dataset.originalHtml = el.innerHTML;
    el.innerHTML = words.map((w, i) => `<span class="word" data-w="${i}">${escapeHtml(w)}</span>`).join(" ");
    el.dataset.wordsRendered = "1";
  }

  function restoreOriginal(el) {
    if (el && el.dataset.wordsRendered) {
      el.innerHTML = el.dataset.originalHtml;
      delete el.dataset.wordsRendered;
    }
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function formatTime(seconds) {
    if (!isFinite(seconds) || seconds < 0) seconds = 0;
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  // ---- audio-only mode's "now playing" panel: mirrors whatever the main
  // document has for the active segment (word spans/highlighting included),
  // so it stays in sync for free instead of tracking word state twice ----
  const nowPlayingEl = document.getElementById("now-playing-text");
  function syncNowPlaying() {
    if (!nowPlayingEl) return;
    const el = currentSegment >= 0 ? segEls[currentSegment] : null;
    nowPlayingEl.innerHTML = el ? el.innerHTML : "Nothing playing yet";
  }

  // ---- table of contents follows playback: highlight the entry for the
  // section being read (the last heading at or before the current segment),
  // keep it visible inside the sidebar's own scroll area, and name it next
  // to "Contents" for when the list is collapsed (phones). ----
  const tocEntries = Array.from(document.querySelectorAll(".toc-entry[data-jump]"))
    .map((el) => ({ el, seg: parseInt(el.getAttribute("data-jump"), 10) }));
  const tocCurrentEl = document.querySelector(".toc-current");
  let activeTocEl = null;

  function updateTocActive(index) {
    let match = null;
    if (index >= 0) {
      for (const entry of tocEntries) {
        if (entry.seg <= index) match = entry.el; else break;
      }
    }
    if (match === activeTocEl) return;
    activeTocEl?.classList.remove("toc-active");
    activeTocEl?.removeAttribute("aria-current");
    activeTocEl = match;
    if (tocCurrentEl) tocCurrentEl.textContent = match ? match.textContent : "";
    if (!match) return;
    match.classList.add("toc-active");
    match.setAttribute("aria-current", "location");
    // Scroll only the sidebar (not the page) when the entry is out of view.
    const box = tocDetails;
    if (box && box.open && box.scrollHeight > box.clientHeight) {
      const top = match.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop;
      if (top < box.scrollTop || top + match.offsetHeight > box.scrollTop + box.clientHeight) {
        box.scrollTo({ top: top - box.clientHeight / 3, behavior: "smooth" });
      }
    }
  }

  function setActiveSegment(index) {
    if (currentSegment >= 0 && segEls[currentSegment]) {
      segEls[currentSegment].classList.remove("sentence-active");
      restoreOriginal(segEls[currentSegment]);
    }
    currentSegment = index;
    currentWordEl = null;
    currentWordIdx = -1;
    if (index >= 0 && segEls[index]) {
      const el = segEls[index];
      el.classList.add("sentence-active");
      if (segTypes[index] === "paragraph" || segTypes[index] === "heading") setWordSpans(el);
      maybeAutoScroll(el);
    }
    updateDocSeekUI(0);
    syncNowPlaying();
    updateTocActive(index);
    updateMediaMetadata();
    postProgress();
  }

  function setActiveWord(el, wordIdx) {
    if (currentWordEl) currentWordEl.classList.remove("word-active");
    const wordEl = el.querySelector(`.word[data-w="${wordIdx}"]`);
    if (wordEl) {
      wordEl.classList.add("word-active");
      currentWordEl = wordEl;
    }
    syncNowPlaying();
  }

  // Called every animation frame (tickPlayhead) with the current segment's
  // elapsed time. Polling audioEl.currentTime rather than scheduling timers
  // means seeks need no rescheduling, and when the page is hidden (no
  // animation frames) highlighting just pauses and picks up at the right
  // word when you come back.
  function updateWordHighlight(elapsed) {
    const entry = cacheMap.get(currentSegment);
    const el = segEls[currentSegment];
    if (!entry || !el || !entry.wordTimings) return;
    let idx = -1;
    for (let i = 0; i < entry.wordTimings.length; i++) {
      if (entry.wordTimings[i].start <= elapsed) idx = i; else break;
    }
    if (idx >= 0 && idx !== currentWordIdx) {
      currentWordIdx = idx;
      setActiveWord(el, idx);
    }
  }

  // ---- auto-scroll with manual-scroll override ----
  window.addEventListener("scroll", () => {
    userScrolling = true;
    clearTimeout(userScrollTimer);
    userScrollTimer = setTimeout(() => { userScrolling = false; }, AUTO_SCROLL_IDLE_MS);
  }, { passive: true });

  function maybeAutoScroll(el) {
    if (userScrolling) return;
    const rect = el.getBoundingClientRect();
    const inView = rect.top >= 80 && rect.bottom <= window.innerHeight - 120;
    if (!inView) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  // ---- playhead: elapsed/duration for whatever segment is currently
  // playing, plus a seek bar to jump within it ----
  const playheadSeek = document.getElementById("playhead-seek");
  const playheadElapsedEl = document.getElementById("playhead-elapsed");
  const playheadDurationEl = document.getElementById("playhead-duration");

  // This seek bar/labels are scoped to the *current segment only*
  // (0..withinSegDuration) -- dragging it calls seekWithinSegment. The
  // document-wide bar below is the separate #doc-seek row.
  function updatePlayheadUI(withinSegElapsed, withinSegDuration) {
    if (!playheadSeek) return;
    playheadSeek.max = String(withinSegDuration || 0);
    playheadSeek.disabled = !withinSegDuration;
    if (playheadDragging) return; // don't fight the user's own drag position
    playheadElapsedEl.textContent = formatTime(withinSegElapsed);
    playheadSeek.value = String(withinSegElapsed);
  }

  if (playheadSeek) {
    ["pointerdown", "touchstart"].forEach((evt) => {
      playheadSeek.addEventListener(evt, () => { playheadDragging = true; });
    });
    playheadSeek.addEventListener("input", () => {
      playheadElapsedEl.textContent = formatTime(parseFloat(playheadSeek.value));
    });
    playheadSeek.addEventListener("change", () => {
      playheadDragging = false;
      seekWithinSegment(parseFloat(playheadSeek.value));
    });
  }

  // ---- document-wide bar: elapsed/estimated-total across the whole
  // article, and a coarse-grained "jump to any sentence" scrubber. Unlike
  // the per-segment bar above, dragging this doesn't need sample-accurate
  // seeking -- landing on the nearest *segment* (segmentIndexAtTime) and
  // calling jumpTo() is exactly what clicking a TOC entry or a paragraph in
  // the document already does, generating that segment's audio on demand. ----
  const docSeek = document.getElementById("doc-seek");
  const docElapsedEl = document.getElementById("doc-elapsed");
  const docDurationEl = document.getElementById("doc-duration");
  let docSeekDragging = false;

  function updateDocSeekUI(withinSegElapsed) {
    if (!docSeek) return;
    const { elapsed, total } = docElapsedAndTotal(withinSegElapsed);
    docSeek.max = String(total || 0);
    docSeek.disabled = !total;
    docDurationEl.textContent = formatTime(total);
    if (docSeekDragging) return;
    docElapsedEl.textContent = formatTime(elapsed);
    docSeek.value = String(elapsed);
  }

  if (docSeek) {
    ["pointerdown", "touchstart"].forEach((evt) => {
      docSeek.addEventListener(evt, () => { docSeekDragging = true; });
    });
    docSeek.addEventListener("input", () => {
      docElapsedEl.textContent = formatTime(parseFloat(docSeek.value));
    });
    docSeek.addEventListener("change", () => {
      docSeekDragging = false;
      jumpTo(segmentIndexAtTime(parseFloat(docSeek.value)));
    });
  }

  function tickPlayhead() {
    if (playing && loadedSegment >= 0 && loadedSegment === currentSegment) {
      const elapsed = Math.max(0, Math.min(audioEl.currentTime, segmentDuration));
      updatePlayheadUI(elapsed, segmentDuration);
      updateDocSeekUI(elapsed);
      updateWordHighlight(elapsed);
    }
    requestAnimationFrame(tickPlayhead);
  }
  requestAnimationFrame(tickPlayhead);
  updateDocSeekUI(0); // show the estimated total right away, before playback starts

  // ---- playback session (generation-counter guarded, ported from usePlayer.ts) ----
  async function playSegment(index, myGen) {
    if (gen !== myGen) return;
    if (index >= totalSegments) {
      stopAudio();
      setActiveSegment(-1);
      segmentDuration = 0;
      updatePlayheadUI(0, 0);
      // Article finished -- show the doc-wide bar as fully elapsed rather
      // than 0 (docElapsedAndTotal has no "before segment -1" to sum).
      if (docSeek) {
        docSeek.value = docSeek.max;
        docElapsedEl.textContent = formatTime(parseFloat(docSeek.max || "0"));
      }
      setPlayingUI(false);
      return;
    }

    setActiveSegment(index);
    for (let i = 1; i <= lookahead(); i++) fetchSegment(index + i);

    if (segTypes[index] === "code") {
      if (gen === myGen) await playSegment(index + 1, myGen);
      return;
    }

    if (!cacheMap.has(index)) {
      // Audio for this sentence is still being generated: show it, so the
      // pause before playback doesn't look like a hang.
      segEls[index]?.classList.add("seg-loading");
      holdAudioSession();
      await fetchSegment(index);
      segEls[index]?.classList.remove("seg-loading");
    }
    if (gen !== myGen) return;
    const entry = cacheMap.get(index);
    if (!entry) {
      // Segment could not be spoken at all (e.g. crashed even after the
      // retry/bisect fallback server-side) -- skip it rather than stall.
      if (gen === myGen) await playSegment(index + 1, myGen);
      return;
    }

    updatePlayheadUI(0, entry.duration);
    updateDocSeekUI(0);
    startAudio(index, entry, 0, myGen);
  }

  // Reposition playback within the currently-active segment (dragging the
  // playhead, a lock-screen scrub, or resuming after pause), rather than
  // starting a whole new session the way jumpTo()/startSession() do. Always
  // resumes playback (matches how dragging a scrubber reads on most audio
  // players). Bumps gen so a still-loading segment from before can't take
  // over once its fetch lands.
  function seekWithinSegment(offsetSeconds) {
    if (currentSegment < 0) return;
    const entry = cacheMap.get(currentSegment);
    if (!entry) return;
    const myGen = ++gen;
    const clamped = Math.max(0, Math.min(offsetSeconds, Math.max(0, entry.duration - 0.02)));
    setPlayingUI(true);
    startAudio(currentSegment, entry, clamped, myGen);
    updatePlayheadUI(clamped, entry.duration);
    updateDocSeekUI(clamped);
  }

  function startSession(fromSegment) {
    const myGen = ++gen;
    stopAudio();
    for (let i = 0; i <= lookahead(); i++) fetchSegment(fromSegment + i);
    playSegment(fromSegment, myGen);
  }

  // Paused partway through the sentence that's still loaded? Pick up where
  // it left off instead of restarting the sentence.
  function canResumeInPlace(index) {
    return index === currentSegment && loadedSegment === index && cacheMap.has(index)
      && !audioEl.ended && audioEl.currentTime > 0;
  }

  function play(fromSegment) {
    const startAt = fromSegment !== undefined ? fromSegment : Math.max(0, currentSegment);
    if (canResumeInPlace(startAt)) {
      seekWithinSegment(audioEl.currentTime);
      return;
    }
    setPlayingUI(true);
    startSession(startAt);
  }

  function pause() {
    gen++; // invalidate in-flight session
    stopAudio();
    setPlayingUI(false);
  }

  function stop() {
    gen++;
    stopAudio();
    setActiveSegment(-1);
    setPlayingUI(false);
  }

  function skipBack() {
    const prev = Math.max(0, currentSegment - 1);
    setPlayingUI(true);
    startSession(prev);
  }

  function skipForward() {
    const next = Math.min(totalSegments - 1, currentSegment + 1);
    setPlayingUI(true);
    startSession(next);
  }

  function jumpTo(index) {
    setPlayingUI(true);
    startSession(index);
  }

  // Every previously-recorded *real* segment duration was measured at the
  // old voice/speed and no longer applies (a different voice/speed produces
  // different actual durations) -- back every segment out to a fresh
  // estimate along with the audio cache itself, rather than leaving stale
  // real numbers in the document-wide total.
  function resetDurationEstimates() {
    for (let i = 0; i < segmentDurations.length; i++) segmentDurationIsReal[i] = false;
    observedBaseWordsPerSecond = null;
    recomputeEstimatesForCurrentSpeed();
  }

  function setSpeed(newSpeed) {
    speed = newSpeed;
    clearSegmentCache();
    // Forget in-flight fetches too (not cancel them -- fetch() has no abort wired
    // here -- but a stale one finishing later just writes an orphaned cacheMap
    // entry for an index nobody reads under the new voice/speed context; a fresh
    // fetchSegment() call right after this always starts a new request instead of
    // awaiting the stale one).
    pending.clear();
    resetDurationEstimates();
    document.querySelectorAll(".speed-btn").forEach((b) => {
      b.classList.toggle("active", parseFloat(b.dataset.speed) === speed);
    });
    if (currentSegment >= 0) startSession(currentSegment);
  }

  function setVoice(newVoice) {
    voice = newVoice;
    clearSegmentCache();
    // Forget in-flight fetches too (not cancel them -- fetch() has no abort wired
    // here -- but a stale one finishing later just writes an orphaned cacheMap
    // entry for an index nobody reads under the new voice/speed context; a fresh
    // fetchSegment() call right after this always starts a new request instead of
    // awaiting the stale one).
    pending.clear();
    resetDurationEstimates();
    if (playing && currentSegment >= 0) startSession(currentSegment);
  }

  // ---- UI wiring ----
  function setPlayingUI(isPlaying) {
    playing = isPlaying;
    const btn = document.getElementById("btn-play-pause");
    if (btn) btn.textContent = isPlaying ? "⏸" : "▶";
    if (hasMediaSession) navigator.mediaSession.playbackState = isPlaying ? "playing" : "paused";
  }

  // ---- Media Session: lock screen / Control Center / headphone controls.
  // Previous/next track step by sentence, like the ⏮/⏭ buttons; the
  // scrubber is the current sentence, like #playhead-seek. ----
  const articleTitle = document.querySelector(".reader-header h1")?.textContent || document.title;
  let mediaSectionTitle = null;

  function updateMediaMetadata() {
    if (!hasMediaSession || typeof MediaMetadata === "undefined") return;
    const section = tocCurrentEl?.textContent || "";
    if (section === mediaSectionTitle) return;
    mediaSectionTitle = section;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: articleTitle,
      artist: section || "Lector",
      album: "Lector",
      artwork: [{ src: "/static/icon-512.png", sizes: "512x512", type: "image/png" }],
    });
  }

  function updateMediaPositionState(position) {
    if (!hasMediaSession || !navigator.mediaSession.setPositionState) return;
    try {
      if (!segmentDuration) {
        navigator.mediaSession.setPositionState();
        return;
      }
      navigator.mediaSession.setPositionState({
        duration: segmentDuration,
        playbackRate: 1,
        position: Math.max(0, Math.min(position, segmentDuration)),
      });
    } catch (_) { /* older browsers throw on any invalid combination */ }
  }

  if (hasMediaSession) {
    const handlers = {
      play: () => play(currentSegment >= 0 ? currentSegment : 0),
      pause: () => pause(),
      stop: () => stop(),
      previoustrack: () => skipBack(),
      nexttrack: () => skipForward(),
      seekto: (details) => { if (details.seekTime != null) seekWithinSegment(details.seekTime); },
    };
    for (const [action, handler] of Object.entries(handlers)) {
      try { navigator.mediaSession.setActionHandler(action, handler); } catch (_) { /* unsupported action */ }
    }
  }

  // Coming back to the page: catch the document up with wherever playback
  // got to while it was hidden. While hidden, prefetch further ahead.
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      if (playing && currentSegment >= 0) {
        for (let i = 1; i <= lookahead(); i++) fetchSegment(currentSegment + i);
      }
    } else if (currentSegment >= 0 && segEls[currentSegment]) {
      maybeAutoScroll(segEls[currentSegment]);
    }
  });

  let progressTimer = null;
  function postProgress() {
    clearTimeout(progressTimer);
    progressTimer = setTimeout(() => {
      fetch(`/api/articles/${ARTICLE_ID}/progress`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ segment_index: currentSegment, voice, speed }),
      }).catch(() => {});
    }, 300);
  }

  // ---- one-time "tap any sentence" tip (per-browser, localStorage) ----
  const TAP_TIP_KEY = "lector.tapTipSeen";
  const tapTip = document.getElementById("tap-tip");
  function dismissTapTip() {
    if (tapTip) tapTip.hidden = true;
    try { localStorage.setItem(TAP_TIP_KEY, "1"); } catch (err) { /* ignore */ }
  }
  if (tapTip) {
    let seen = false;
    try { seen = localStorage.getItem(TAP_TIP_KEY) === "1"; } catch (err) { /* ignore */ }
    tapTip.hidden = seen || totalSegments === 0;
    document.getElementById("btn-dismiss-tap-tip")?.addEventListener("click", dismissTapTip);
  }

  document.addEventListener("click", (e) => {
    if (e.target.closest("#doc-body [data-seg]")) dismissTapTip();
    const jumpEl = e.target.closest("[data-jump]");
    if (jumpEl) {
      jumpTo(parseInt(jumpEl.getAttribute("data-jump"), 10));
      return;
    }
    const segEl = e.target.closest("[data-seg]");
    if (segEl && segTypes[parseInt(segEl.getAttribute("data-seg"), 10)] !== "code") {
      jumpTo(parseInt(segEl.getAttribute("data-seg"), 10));
    }
  });

  const playPauseBtn = document.getElementById("btn-play-pause");
  if (playPauseBtn) {
    playPauseBtn.addEventListener("click", () => {
      if (playing) pause();
      else play(currentSegment >= 0 ? currentSegment : 0);
    });
  }
  const stopBtn = document.getElementById("btn-stop");
  if (stopBtn) stopBtn.addEventListener("click", stop);
  const skipBackBtn = document.getElementById("btn-skip-back");
  if (skipBackBtn) skipBackBtn.addEventListener("click", skipBack);
  const skipForwardBtn = document.getElementById("btn-skip-forward");
  if (skipForwardBtn) skipForwardBtn.addEventListener("click", skipForward);
  const jumpToCurrentBtn = document.getElementById("btn-jump-to-current");
  if (jumpToCurrentBtn) {
    jumpToCurrentBtn.addEventListener("click", () => {
      if (currentSegment < 0 || !segEls[currentSegment]) return;
      // A manual scroll suppresses auto-scroll for AUTO_SCROLL_IDLE_MS (see
      // the scroll listener below) -- explicitly asking to jump back to the
      // current sentence is a clear signal to resume following along, so
      // clear that suppression instead of leaving it on a stale cooldown.
      userScrolling = false;
      clearTimeout(userScrollTimer);
      segEls[currentSegment].scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  document.querySelectorAll(".speed-btn").forEach((btn) => {
    btn.addEventListener("click", () => setSpeed(parseFloat(btn.dataset.speed)));
  });
  const voiceSelect = document.getElementById("voice-select");
  if (voiceSelect) voiceSelect.addEventListener("change", () => setVoice(voiceSelect.value));

  document.addEventListener("keydown", (e) => {
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea") return;
    if (e.code === "Space") {
      e.preventDefault();
      if (playing) pause(); else play(currentSegment >= 0 ? currentSegment : 0);
    } else if (e.code === "ArrowLeft") {
      skipBack();
    } else if (e.code === "ArrowRight") {
      skipForward();
    } else if (e.key === "[") {
      const i = Math.max(0, SPEEDS.indexOf(speed) - 1);
      setSpeed(SPEEDS[i]);
    } else if (e.key === "]") {
      const i = Math.min(SPEEDS.length - 1, SPEEDS.indexOf(speed) + 1);
      setSpeed(SPEEDS[i]);
    }
  });

  // ---- audio-only mode: hides the article text/TOC, shows the
  // "now playing" panel (syncNowPlaying(), above) instead. Persisted
  // per-browser via localStorage, matching theme.js's pattern -- not
  // per-article, since it's a listening-preference, not article state. ----
  const AUDIO_ONLY_KEY = "audioOnlyMode";
  const audioOnlyToggle = document.getElementById("audio-only-toggle");
  function applyAudioOnlyMode(enabled) {
    document.body.classList.toggle("audio-only-mode", enabled);
    if (audioOnlyToggle) audioOnlyToggle.textContent = enabled ? "📄 Show text" : "🎧 Audio only";
  }
  applyAudioOnlyMode(localStorage.getItem(AUDIO_ONLY_KEY) === "1");
  if (audioOnlyToggle) {
    audioOnlyToggle.addEventListener("click", () => {
      const enabled = !document.body.classList.contains("audio-only-mode");
      localStorage.setItem(AUDIO_ONLY_KEY, enabled ? "1" : "0");
      applyAudioOnlyMode(enabled);
    });
  }

  // ---- resume banner ----
  const lastIndex = window.LAST_SEGMENT_INDEX;
  if (typeof lastIndex === "number" && lastIndex >= 0 && lastIndex < totalSegments) {
    const banner = document.getElementById("resume-banner");
    if (banner) {
      banner.style.display = "flex";
      document.getElementById("btn-resume").addEventListener("click", () => {
        banner.style.display = "none";
        jumpTo(lastIndex);
      });
      document.getElementById("btn-dismiss-resume").addEventListener("click", () => {
        banner.style.display = "none";
      });
    }
  }
})();
