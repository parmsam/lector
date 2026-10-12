// Library page interactions (delete, search, folders, drag-and-drop import,
// copy-LAN-url). Plain fetch()/DOM -- no
// htmx, no build step, consistent with player.js and the rest of this app's
// no-external-JS approach (this app is meant to run fully on-device with no
// CDN dependency).
(function () {
  "use strict";

  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-delete-id]");
    if (!btn) return;

    if (!confirm("Delete this article and its cached audio?")) return;

    const id = btn.getAttribute("data-delete-id");
    try {
      const resp = await fetch(`/article/${id}`, { method: "DELETE" });
      if (!resp.ok) {
        alert("Failed to delete article.");
        return;
      }
      // The same article can be listed twice (Continue listening + its
      // folder), so remove every row for it, not just the clicked one.
      document.querySelectorAll(`.article-row [data-delete-id="${id}"]`).forEach((b) => {
        b.closest(".article-row")?.remove();
      });
    } catch (err) {
      console.error("Delete failed:", err);
      alert("Failed to delete article.");
    }
  });

  // Manual "check for updates" -- lives in the navbar so it's available on
  // every page (unlike the passive library-page banner, see components.py's
  // library_page). A hit turns the link itself into a link to the release;
  // a miss/failure just flashes a status before reverting.
  document.addEventListener("click", async (e) => {
    const link = e.target.closest("#check-update-link");
    if (!link) return;
    e.preventDefault();

    const original = link.textContent;
    link.textContent = "Checking…";
    try {
      const resp = await fetch("/api/check-update");
      const data = await resp.json();
      if (data.update) {
        link.textContent = `v${data.update} available`;
        link.href = data.url;
        link.target = "_blank";
        link.rel = "noopener";
        return;
      }
      link.textContent = "Up to date";
    } catch (err) {
      console.error("Update check failed:", err);
      link.textContent = "Check failed";
    }
    setTimeout(() => { link.textContent = original; }, 2000);
  });

  document.addEventListener("click", async (e) => {
    const btn = e.target.closest(".copy-lan-url");
    if (!btn) return;

    const url = btn.getAttribute("data-url");
    const original = btn.textContent;
    try {
      await navigator.clipboard.writeText(url);
      btn.textContent = "Copied!";
    } catch (err) {
      console.error("Clipboard copy failed:", err);
      btn.textContent = "Copy failed";
    }
    setTimeout(() => { btn.textContent = original; }, 1500);
  });

  // Move-to-folder <select> per article row. The select itself has no
  // name= (see components.py's _folder_move_form) so it can't submit an
  // option value the browser doesn't already know about -- a sibling
  // hidden input carries whatever the actual target folder ends up being,
  // including a freshly-typed new folder name.
  document.addEventListener("change", (e) => {
    const select = e.target.closest(".folder-select");
    if (!select) return;
    const form = select.closest("form");
    const hidden = form.querySelector('input[name="folder"]');

    if (select.value === "__new__") {
      const name = window.prompt('New folder name (use "/" for nested, e.g. Notes/Work):');
      if (!name || !name.trim()) {
        select.value = hidden.value; // revert the visual selection
        return;
      }
      hidden.value = name.trim();
    } else {
      hidden.value = select.value;
    }
    form.submit();
  });

  // Rename a folder (and all its sub-folders, see db.py's rename_folder).
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest(".folder-rename-btn");
    if (!btn) return;

    const oldPath = btn.getAttribute("data-folder-path");
    const newPath = window.prompt(`Rename folder "${oldPath}" to:`, oldPath);
    if (!newPath || !newPath.trim() || newPath.trim() === oldPath) return;

    try {
      const resp = await fetch("/folders/rename", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: `old_path=${encodeURIComponent(oldPath)}&new_path=${encodeURIComponent(newPath.trim())}`,
      });
      if (!resp.ok) throw new Error(`status ${resp.status}`);
      location.reload();
    } catch (err) {
      console.error("Folder rename failed:", err);
      alert("Failed to rename folder.");
    }
  });

  // Delete a folder -- Finder-style: this permanently deletes every article
  // (and cached audio) inside the folder and its sub-folders, not just the
  // grouping. The confirm() names the article count so this reads as
  // clearly destructive before it happens.
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest(".folder-delete-btn");
    if (!btn) return;

    const path = btn.getAttribute("data-folder-path");
    const count = btn.getAttribute("data-folder-count");
    if (!confirm(`Delete folder "${path}" and permanently delete ${count} article${count === "1" ? "" : "s"} inside it (including cached audio)? This cannot be undone.`)) return;

    try {
      const resp = await fetch("/folders/delete", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: `path=${encodeURIComponent(path)}`,
      });
      if (!resp.ok) throw new Error(`status ${resp.status}`);
      window.location = resp.url; // fetch follows the redirect to /?notice=... itself
    } catch (err) {
      console.error("Folder delete failed:", err);
      alert("Failed to delete folder.");
    }
  });

  // ---- folder open/closed state ----
  // Folders render collapsed; which ones this browser last had open is a
  // per-viewer convenience kept in localStorage (wrapped in try/catch --
  // storage can be unavailable in private windows). Not saved while a
  // search is temporarily opening folders to show matches.
  const OPEN_FOLDERS_KEY = "lector.openFolders";
  const folderGroups = () => Array.from(document.querySelectorAll(".folder-group"));
  let searching = false;

  function loadOpenFolders() {
    try { return new Set(JSON.parse(localStorage.getItem(OPEN_FOLDERS_KEY) || "[]")); }
    catch (err) { return new Set(); }
  }
  function saveOpenFolders() {
    if (searching) return;
    const open = folderGroups().filter((d) => d.open).map((d) => d.dataset.folderPath);
    try { localStorage.setItem(OPEN_FOLDERS_KEY, JSON.stringify(open)); } catch (err) { /* ignore */ }
  }
  function restoreOpenFolders() {
    const open = loadOpenFolders();
    folderGroups().forEach((d) => { d.open = open.has(d.dataset.folderPath); });
  }
  restoreOpenFolders();
  // `toggle` doesn't bubble, hence capture.
  document.addEventListener("toggle", (e) => {
    if (e.target instanceof Element && e.target.classList.contains("folder-group")) saveOpenFolders();
  }, true);

  // Expand/collapse every folder at once, including nested subfolders.
  document.getElementById("expand-all-folders")?.addEventListener("click", () => {
    folderGroups().forEach((d) => { d.open = true; });
  });
  document.getElementById("collapse-all-folders")?.addEventListener("click", () => {
    folderGroups().forEach((d) => { d.open = false; });
  });

  // ---- search: filters rows by title/domain/folder as you type ----
  const searchInput = document.getElementById("library-search");
  if (searchInput) {
    const continueSection = document.getElementById("continue-section");
    const emptyMsg = document.getElementById("search-empty");

    const applySearch = () => {
      const terms = searchInput.value.toLowerCase().split(/\s+/).filter(Boolean);
      const wasSearching = searching;
      searching = terms.length > 0;
      if (!searching) {
        document.querySelectorAll(".article-row, .folder-group, .library-section").forEach((el) => { el.hidden = false; });
        if (emptyMsg) emptyMsg.hidden = true;
        if (wasSearching) restoreOpenFolders();
        return;
      }
      // Continue listening would only duplicate matches shown below.
      if (continueSection) continueSection.hidden = true;
      let matches = 0;
      document.querySelectorAll("#library-body .article-row").forEach((row) => {
        if (continueSection && continueSection.contains(row)) return;
        const hay = row.dataset.search || "";
        const hit = terms.every((t) => hay.includes(t));
        row.hidden = !hit;
        if (hit) matches++;
      });
      // Deepest folders first, so a parent sees its children's final state.
      folderGroups().reverse().forEach((d) => {
        const hasHit = d.querySelector(".article-row:not([hidden])") !== null;
        d.hidden = !hasHit;
        d.open = hasHit;
      });
      document.querySelectorAll(".library-section").forEach((sec) => {
        if (sec === continueSection) return;
        sec.hidden = sec.querySelector(".article-row:not([hidden])") === null;
      });
      if (emptyMsg) emptyMsg.hidden = matches > 0;
    };
    searchInput.addEventListener("input", applySearch);
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { searchInput.value = ""; applySearch(); }
    });
    // "/" focuses search, like many sites; ignored while typing elsewhere.
    document.addEventListener("keydown", (e) => {
      const tag = (e.target.tagName || "").toLowerCase();
      if (e.key === "/" && tag !== "input" && tag !== "textarea" && tag !== "select") {
        e.preventDefault();
        searchInput.focus();
      }
    });
  }

  // ---- drag-and-drop import onto the library page ----
  // Drop files anywhere to add them unfiled, or onto a folder row to add
  // them to that folder. Reuses the folder-upload endpoint (one or many
  // files, optional folder_prefix), which redirects back here with a
  // notice when done.
  const overlay = document.getElementById("drop-overlay");
  if (overlay) {
    const overlayTarget = overlay.querySelector(".drop-overlay-target");
    let dragDepth = 0;
    let dropFolder = null;
    let busy = false;

    const hasFiles = (e) => Array.from(e.dataTransfer?.types || []).includes("Files");
    const setDropFolder = (group) => {
      document.querySelectorAll(".folder-group.drop-target").forEach((g) => g.classList.remove("drop-target"));
      dropFolder = group ? group.dataset.folderPath : null;
      if (group) group.classList.add("drop-target");
      overlayTarget.textContent = dropFolder ? `into “${dropFolder}”` : "unfiled — or drop onto a folder";
    };
    const hide = () => {
      dragDepth = 0;
      overlay.hidden = true;
      setDropFolder(null);
    };

    document.addEventListener("dragenter", (e) => {
      if (!hasFiles(e) || busy) return;
      dragDepth++;
      overlay.hidden = false;
    });
    document.addEventListener("dragover", (e) => {
      if (!hasFiles(e) || busy) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      // Innermost folder under the pointer (open or collapsed).
      setDropFolder(e.target.closest?.(".folder-group") || null);
    });
    document.addEventListener("dragleave", (e) => {
      if (!hasFiles(e) || busy) return;
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) hide();
    });
    document.addEventListener("drop", async (e) => {
      if (!hasFiles(e) || busy) return;
      e.preventDefault();
      const files = Array.from(e.dataTransfer.files || []);
      const folder = dropFolder;
      if (!files.length) { hide(); return; }

      busy = true;
      document.querySelectorAll(".folder-group.drop-target").forEach((g) => g.classList.remove("drop-target"));
      overlay.querySelector(".drop-overlay-title").textContent =
        `Adding ${files.length} file${files.length === 1 ? "" : "s"}…`;
      overlayTarget.textContent = files.some((f) => /\.pdf$/i.test(f.name))
        ? "PDFs can take a minute to convert"
        : (folder ? `into “${folder}”` : "");

      const form = new FormData();
      files.forEach((f) => form.append("file", f, f.name));
      if (folder) form.append("folder_prefix", folder);
      try {
        const resp = await fetch("/articles/upload-folder", { method: "POST", body: form });
        window.location = resp.url; // follows the redirect to /?notice=... (or /add?error=...)
      } catch (err) {
        console.error("Drop upload failed:", err);
        alert("Failed to add the dropped files.");
        busy = false;
        hide();
      }
    });
  }

  const sortSelect = document.getElementById("sort-select");
  if (sortSelect) sortSelect.addEventListener("change", () => sortSelect.form.submit());

  document.addEventListener("change", (e) => {
    const select = e.target.closest(".folder-sort-select");
    if (select) select.form.submit();
  });

  // ---- kebab ("⋯") menus: article-row and folder-header actions, both
  // driven by the native Popover API (see components.py's _article_row /
  // _render_folder_node) ----

  // A folder's kebab button lives inside its <summary>, so a plain click
  // would also toggle the <details> open/closed the way any click inside a
  // <summary> does. stopPropagation() (not preventDefault()) is the fix --
  // preventDefault() on this click also cancels the popovertarget button's
  // own default action (showing the popover), since both are driven by the
  // same click event; stopPropagation() only keeps the click from ever
  // bubbling up to <summary>, leaving the popover's own behavior intact.
  // Harmless no-op for article-row kebabs, which aren't inside a <summary>.
  document.addEventListener("click", (e) => {
    if (e.target.closest(".kebab-btn")) e.stopPropagation();
  });

  // Position each popover menu near the button that opened it. There's no
  // cross-browser way to CSS-anchor a [popover] to its trigger yet (CSS
  // anchor positioning isn't in Safari), so this does it in JS instead, on
  // the (non-bubbling, hence the capture-phase listener) `toggle` event
  // every popover fires when its state changes.
  document.addEventListener("toggle", (e) => {
    const menu = e.target;
    if (!(menu instanceof Element) || !menu.hasAttribute("popover")) return;
    if (e.newState !== "open") return;
    const trigger = document.querySelector(`[popovertarget="${menu.id}"]`);
    if (!trigger) return;

    const btnRect = trigger.getBoundingClientRect();
    const menuRect = menu.getBoundingClientRect();
    const margin = 8;
    let left = btnRect.right - menuRect.width;
    left = Math.max(margin, Math.min(left, window.innerWidth - menuRect.width - margin));
    let top = btnRect.bottom + 4;
    if (top + menuRect.height > window.innerHeight - margin) {
      top = btnRect.top - menuRect.height - 4; // flip above if it wouldn't fit below
    }
    menu.style.left = `${left}px`;
    menu.style.top = `${Math.max(margin, top)}px`;
  }, true);
})();
