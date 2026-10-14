/* ScholarFlow writing workspace.
 *
 * Stage 1: real document editing, local persistence, crash recovery,
 * revision history, Markdown structure tools, and a reviewable "refine"
 * step that never changes text without an explicit Accept.
 */
(() => {
  "use strict";

  const DRAFT_PREFIX = "scholarflow:draft:";
  const AUTOSAVE_DELAY_MS = 2500;
  const PROFILE_LABELS = {
    standard: "Academic standard",
    polish: "Concise academic writing",
    conservative: "Formal academic writing (minimal edits)",
  };

  const byId = (id) => document.getElementById(id);
  const elements = {
    title: byId("doc-title"),
    editor: byId("editor"),
    saveState: byId("save-state"),
    documentList: byId("document-list"),
    documentSearch: byId("document-search"),
    storageNote: byId("storage-note"),
    history: byId("history"),
    outline: byId("outline"),
    wordCount: byId("word-count"),
    charCount: byId("char-count"),
    selectionCount: byId("selection-count"),
    cursorPosition: byId("cursor-position"),
    readingTime: byId("reading-time"),
    lastSaved: byId("last-saved"),
    profile: byId("profile"),
    reviewCard: byId("review-card"),
    reviewHeading: byId("review-heading"),
    reviewBadge: byId("review-badge"),
    reviewOriginal: byId("review-original"),
    reviewProposal: byId("review-proposal"),
    reviewMeta: byId("review-meta"),
    reviewNote: byId("review-note"),
    errorBanner: byId("error-banner"),
    errorMessage: byId("error-message"),
    statusBanner: byId("status-banner"),
    statusMessage: byId("status-message"),
    recoveryBanner: byId("recovery-banner"),
    conflictBanner: byId("conflict-banner"),
    refineButton: byId("refine-selection"),
  };

  const state = {
    document: null,
    dirty: false,
    saving: false,
    pending: null,
    queuedSave: null,
    autosaveTimer: null,
    statusTimer: null,
    retry: null,
    list: [],
  };

  // ---------------------------------------------------------------- helpers
  async function request(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (!response.ok) {
      const error = new Error(readError(payload, response.status));
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function readError(payload, status) {
    const detail = payload && payload.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && typeof detail.message === "string") return detail.message;
    if (Array.isArray(detail)) {
      return detail.map((item) => (item && item.msg) || "Invalid input").join("; ");
    }
    return `The ScholarFlow server returned ${status}.`;
  }

  function countWords(text) {
    const matches = text.match(/[\w\u0300-\u036f\u0900-\u097F]+(?:['’-][\w\u0300-\u036f\u0900-\u097F]+)*/gu);
    return matches ? matches.length : 0;
  }

  function setSaveState(text, kind = "") {
    elements.saveState.textContent = text;
    elements.saveState.classList.toggle("is-dirty", kind === "dirty");
    elements.saveState.classList.toggle("is-error", kind === "error");
  }

  function showStatus(message) {
    elements.statusMessage.textContent = message;
    elements.statusBanner.hidden = !message;
    window.clearTimeout(state.statusTimer);
    if (message) {
      state.statusTimer = window.setTimeout(() => {
        elements.statusBanner.hidden = true;
      }, 6000);
    }
  }

  function showError(message, retry) {
    elements.errorMessage.textContent = message;
    elements.errorBanner.hidden = false;
    state.retry = retry || null;
    byId("retry-button").hidden = !retry;
    setSaveState("Error", "error");
  }

  function clearError() {
    elements.errorBanner.hidden = true;
    state.retry = null;
  }

  function draftKey(id) {
    return DRAFT_PREFIX + id;
  }

  function readDraft(id) {
    try {
      const raw = window.localStorage.getItem(draftKey(id));
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  function writeDraft() {
    if (!state.document) return;
    try {
      window.localStorage.setItem(
        draftKey(state.document.id),
        JSON.stringify({
          text: elements.editor.value,
          title: elements.title.value,
          baseRevision: state.document.revision,
          savedAt: new Date().toISOString(),
        }),
      );
    } catch {
      /* storage may be unavailable; autosave still protects the text */
    }
  }

  function clearDraft(id) {
    try {
      window.localStorage.removeItem(draftKey(id));
    } catch {
      /* ignore */
    }
  }

  // ------------------------------------------------------------- editing
  function markDirty() {
    state.dirty = true;
    setSaveState("Unsaved changes", "dirty");
    writeDraft();
    scheduleAutosave();
    if (state.pending) {
      state.pending.stale = true;
      renderPendingNote();
    }
    refreshDerived();
  }

  function scheduleAutosave() {
    window.clearTimeout(state.autosaveTimer);
    state.autosaveTimer = window.setTimeout(() => {
      if (state.dirty && !state.saving && state.document) {
        saveDocument("autosave");
      }
    }, AUTOSAVE_DELAY_MS);
  }

  function applyEdit(start, end, replacement, select = false) {
    const value = elements.editor.value;
    elements.editor.value = value.slice(0, start) + replacement + value.slice(end);
    const caret = start + replacement.length;
    elements.editor.focus();
    elements.editor.setSelectionRange(select ? start : caret, caret);
    markDirty();
  }

  function selectedLines() {
    const value = elements.editor.value;
    const start = value.lastIndexOf("\n", Math.max(0, elements.editor.selectionStart - 1)) + 1;
    let end = value.indexOf("\n", elements.editor.selectionEnd);
    if (end === -1) end = value.length;
    return { start, end, text: value.slice(start, end) };
  }

  function prefixLines(prefix, togglePrefixes = []) {
    const { start, end, text } = selectedLines();
    const lines = text.split("\n");
    const alreadyApplied = togglePrefixes.some((candidate) =>
      lines.every((line) => line.trim() === "" || line.startsWith(candidate)),
    );
    const updated = lines
      .map((line) => {
        let cleaned = line;
        togglePrefixes.forEach((candidate) => {
          if (cleaned.startsWith(candidate)) cleaned = cleaned.slice(candidate.length);
        });
        if (alreadyApplied) return cleaned.trimStart();
        return line.trim() === "" ? line : prefix + cleaned.trimStart();
      })
      .join("\n");
    applyEdit(start, end, updated);
  }

  function wrapSelection(marker) {
    const value = elements.editor.value;
    const start = elements.editor.selectionStart;
    const end = elements.editor.selectionEnd;
    const selected = value.slice(start, end);
    const doubled = marker + marker;
    if (selected.startsWith(doubled) && selected.endsWith(doubled) && selected.length > doubled.length * 2 - 1) {
      applyEdit(start, end, selected.slice(doubled.length, -doubled.length), true);
      return;
    }
    if (selected.startsWith(marker) && selected.endsWith(marker) && selected.length > marker.length * 2 - 1) {
      applyEdit(start, end, selected.slice(marker.length, -marker.length), true);
      return;
    }
    if (!selected) {
      applyEdit(start, end, doubled);
      elements.editor.setSelectionRange(start + marker.length, start + marker.length);
      return;
    }
    applyEdit(start, end, doubled + selected + doubled, true);
  }

  function runFormat(action) {
    if (!state.document) {
      showStatus("Open or create a document first.");
      return;
    }
    if (action === "h1") prefixLines("# ", ["# ", "## ", "### "]);
    else if (action === "h2") prefixLines("## ", ["# ", "## ", "### "]);
    else if (action === "h3") prefixLines("### ", ["# ", "## ", "### "]);
    else if (action === "bullet") prefixLines("- ", ["- ", "* "]);
    else if (action === "number") prefixLines("1. ", ["1. "]);
    else if (action === "quote") prefixLines("> ", ["> "]);
    else if (action === "bold") wrapSelection("**");
    else if (action === "italic") wrapSelection("*");
    saveSelectionState();
  }

  function saveSelectionState() {
    refreshDerived();
  }

  // ------------------------------------------------------------- rendering
  function refreshDerived() {
    const text = elements.editor.value;
    const wordCount = countWords(text);
    elements.wordCount.textContent = `${wordCount.toLocaleString()} words`;
    elements.charCount.textContent = `${text.length.toLocaleString()} characters`;
    elements.readingTime.textContent = `${Math.max(1, Math.round(wordCount / 200))} min read`;
    const selected = elements.editor.selectionEnd - elements.editor.selectionStart;
    elements.selectionCount.textContent =
      selected > 0 ? `${selected.toLocaleString()} characters selected` : "No selection";
    const before = text.slice(0, elements.editor.selectionStart);
    const lines = before.split("\n");
    elements.cursorPosition.textContent = `Line ${lines.length}, column ${lines[lines.length - 1].length + 1}`;
    renderOutline(text);
  }

  function renderOutline(text) {
    elements.outline.replaceChildren();
    const lines = text.split("\n");
    let found = 0;
    lines.forEach((line, index) => {
      const match = /^(#{1,3})\s+(.*)$/.exec(line);
      if (!match || !match[2].trim()) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `level-${match[1].length}`;
      button.textContent = match[2].trim();
      button.addEventListener("click", () => {
        const offset = lines.slice(0, index).reduce((total, item) => total + item.length + 1, 0);
        elements.editor.focus();
        elements.editor.setSelectionRange(offset, offset + line.length);
        refreshDerived();
      });
      elements.outline.append(button);
      found += 1;
    });
    if (!found) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "Add a heading with H1–H3 to build an outline.";
      elements.outline.append(empty);
    }
  }

  function renderDocumentList() {
    const container = elements.documentList;
    container.replaceChildren();
    if (!state.list.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "No documents yet. Use “New document” to start.";
      container.append(empty);
      return;
    }
    state.list.forEach((item) => {
      const wrapper = document.createElement("div");
      wrapper.className = "list-item" + (state.document && state.document.id === item.id ? " is-current" : "");
      const open = document.createElement("button");
      open.type = "button";
      open.className = "list-item";
      open.style.border = "0";
      open.style.padding = "0";
      open.style.background = "none";
      const title = document.createElement("strong");
      title.textContent = item.title;
      const meta = document.createElement("small");
      meta.textContent = `${item.word_count.toLocaleString()} words · updated ${item.updated_at.replace("T", " ").slice(0, 16)}`;
      open.append(title, meta);
      open.addEventListener("click", () => openDocument(item.id));
      const actions = document.createElement("div");
      actions.className = "row-actions";
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "link-button danger";
      remove.textContent = "Delete";
      remove.addEventListener("click", (event) => {
        event.stopPropagation();
        deleteDocument(item.id);
      });
      actions.append(remove);
      wrapper.append(open, actions);
      container.append(wrapper);
    });
  }

  function renderHistory(revisions) {
    elements.history.replaceChildren();
    if (!revisions.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "No earlier versions yet.";
      elements.history.append(empty);
      return;
    }
    revisions.forEach((entry) => {
      const wrapper = document.createElement("div");
      wrapper.className = "list-item";
      const label = document.createElement("strong");
      label.textContent = `Revision ${entry.revision}`;
      const meta = document.createElement("small");
      meta.textContent = `${entry.reason} · ${entry.word_count.toLocaleString()} words · ${entry.created_at.replace("T", " ").slice(0, 16)}`;
      const restore = document.createElement("button");
      restore.type = "button";
      restore.className = "link-button";
      restore.textContent = "Restore this revision";
      restore.addEventListener("click", () => restoreRevision(entry.revision));
      wrapper.append(label, meta, restore);
      elements.history.append(wrapper);
    });
  }

  // ------------------------------------------------------------ documents
  async function loadDocumentList() {
    try {
      const payload = await request(`/api/documents?q=${encodeURIComponent(elements.documentSearch.value.trim())}`);
      state.list = payload.documents || [];
      renderDocumentList();
      elements.storageNote.textContent =
        "Documents are stored locally in your ScholarFlow data folder (writing-documents.sqlite3).";
    } catch (error) {
      showError(`The document list could not be loaded: ${error.message}`, loadDocumentList);
    }
  }

  // Adopt a document returned by the server. `writeText` is only true when the
  // server copy is the one that should win (open, restore, conflict reload):
  // after a save the editor may already hold newer keystrokes, and overwriting
  // them lost whatever was typed while the request was in flight.
  function adopt(document_, { writeText = true } = {}) {
    state.document = document_;
    state.dirty = false;
    if (writeText) {
      elements.title.value = document_.title;
      elements.editor.value = document_.text || "";
    }
    elements.lastSaved.textContent = `Last saved ${document_.updated_at.replace("T", " ").slice(0, 16)} · revision ${document_.revision}`;
    setSaveState("Saved");
    clearError();
    refreshDerived();
    renderDocumentList();
    loadHistory();
  }

  async function openDocument(id) {
    try {
      const document_ = await request(`/api/documents/${id}`);
      if (state.dirty && state.document && state.document.id !== id) {
        showStatus("The previous document had unsaved changes; they are kept in this browser session.");
      }
      adopt(document_);
      const draft = readDraft(id);
      if (draft && typeof draft.text === "string" && draft.text !== document_.text) {
        elements.recoveryBanner.hidden = false;
      } else {
        elements.recoveryBanner.hidden = true;
      }
      clearReview("");
      return document_;
    } catch (error) {
      showError(`That document could not be opened: ${error.message}`, () => openDocument(id));
      return null;
    }
  }

  async function createDocument() {
    try {
      const created = await request("/api/documents", {
        method: "POST",
        body: JSON.stringify({ title: "Untitled document", text: "" }),
      });
      await loadDocumentList();
      await openDocument(created.id);
      elements.title.focus();
      elements.title.select();
      showStatus("New document created.");
    } catch (error) {
      showError(`A new document could not be created: ${error.message}`, createDocument);
    }
  }

  async function saveDocument(reason = "manual") {
    if (!state.document) return;
    if (state.saving) {
      // Never drop a queued autosave: remember it and run it when the current
      // write finishes, otherwise an edit made mid-save stays unsaved.
      if (reason === "autosave") state.queuedSave = "autosave";
      return;
    }
    if (!state.dirty && reason !== "manual") return;
    state.saving = true;
    setSaveState(reason === "autosave" ? "Autosaving…" : "Saving…");
    try {
      const saved = await request(`/api/documents/${state.document.id}`, {
        method: "PUT",
        body: JSON.stringify({
          title: elements.title.value,
          text: elements.editor.value,
          expected_revision: state.document.revision,
          reason,
        }),
      });
      // The response carries the stored revision and timestamp, but the editor
      // keeps whatever the researcher has typed meanwhile.
      const stillDirty =
        elements.editor.value !== saved.text || elements.title.value !== saved.title;
      adopt(saved, { writeText: false });
      clearDraft(saved.id);
      elements.conflictBanner.hidden = true;
      if (stillDirty) {
        // Edits made while the request was in flight are still unsaved.
        markDirty();
      } else if (reason === "manual") {
        showStatus("Saved locally.");
      }
    } catch (error) {
      if (error.status === 409) {
        elements.conflictBanner.hidden = false;
        setSaveState("Changed elsewhere", "dirty");
      } else {
        showError(`Saving failed: ${error.message}`, () => saveDocument(reason));
      }
    } finally {
      state.saving = false;
      const queued = state.queuedSave;
      state.queuedSave = null;
      if (queued) saveDocument(queued);
    }
  }

  async function loadHistory() {
    if (!state.document) return;
    try {
      const payload = await request(`/api/documents/${state.document.id}/revisions`);
      renderHistory(payload.revisions || []);
    } catch {
      elements.history.replaceChildren();
    }
  }

  async function restoreRevision(revision) {
    if (!state.document) return;
    try {
      const document_ = await request(
        `/api/documents/${state.document.id}/revisions/${revision}/restore`,
        { method: "POST" },
      );
      adopt(document_);
      showStatus(`Revision ${revision} restored. The previous text is kept in history.`);
    } catch (error) {
      showError(`That revision could not be restored: ${error.message}`);
    }
  }

  async function deleteDocument(id) {
    if (!window.confirm("Move this document to the archive? The text is kept and can be restored from the API.")) return;
    try {
      await request(`/api/documents/${id}`, { method: "DELETE" });
      if (state.document && state.document.id === id) {
        state.document = null;
        elements.editor.value = "";
        elements.title.value = "";
        setSaveState("Ready");
      }
      await loadDocumentList();
      showStatus("Document archived.");
    } catch (error) {
      showError(`The document could not be archived: ${error.message}`);
    }
  }

  // --------------------------------------------------------------- refine
  function targetRange() {
    const value = elements.editor.value;
    const start = elements.editor.selectionStart;
    const end = elements.editor.selectionEnd;
    if (end > start) return { start, end, source: "selection" };
    let paragraphStart = value.lastIndexOf("\n\n", Math.max(0, start - 1));
    paragraphStart = paragraphStart === -1 ? 0 : paragraphStart + 2;
    let paragraphEnd = value.indexOf("\n\n", start);
    paragraphEnd = paragraphEnd === -1 ? value.length : paragraphEnd;
    return { start: paragraphStart, end: paragraphEnd, source: "paragraph" };
  }

  async function refine() {
    if (!state.document) {
      showStatus("Open or create a document first.");
      return;
    }
    const range = targetRange();
    const original = elements.editor.value.slice(range.start, range.end);
    if (!original.trim()) {
      showStatus("Put the cursor in a paragraph or select text to refine.");
      return;
    }
    const profile = elements.profile.value;
    elements.refineButton.disabled = true;
    elements.refineButton.textContent = "Refining…";
    try {
      const result = await request("/editor/rewrite", {
        method: "POST",
        body: JSON.stringify({ text: original, profile, use_llm: false }),
      });
      state.pending = { ...range, original, result, profile, stale: false };
      renderReview();
      showStatus(
        result.refined_text.trim() === original.trim()
          ? "No changes were suggested for this passage — your text is already clear of the patterns the local editor corrects."
          : "A suggestion is ready. Accept or dismiss it — nothing changes until you accept.",
      );
    } catch (error) {
      showError(`Refining failed: ${error.message}`, refine);
    } finally {
      elements.refineButton.disabled = false;
      elements.refineButton.textContent = "Refine selection";
    }
  }

  function renderReview() {
    const pending = state.pending;
    if (!pending) {
      elements.reviewCard.hidden = true;
      return;
    }
    const changed = pending.original.trim() !== pending.result.refined_text.trim();
    elements.reviewHeading.textContent = changed ? "Suggested revision" : "No changes suggested";
    elements.reviewBadge.textContent = changed ? "Review" : "No change";
    elements.reviewBadge.className = "badge" + (changed ? "" : " is-good");
    elements.reviewOriginal.textContent = pending.original;
    elements.reviewProposal.textContent = changed
      ? pending.result.refined_text
      : pending.original + "\n\n(the local editor proposes no change)";
    const stats = pending.result.stats || {};
    elements.reviewMeta.textContent =
      `${PROFILE_LABELS[pending.profile] || pending.profile} · scope: ${pending.source} · ` +
      `${stats.original_words ?? "?"} → ${stats.refined_words ?? "?"} words · ` +
      `${stats.similarity_percent ?? "?"}% of the wording kept · provider: ${pending.result.provider}`;
    byId("review-accept").disabled = !changed;
    renderPendingNote();
    elements.reviewCard.hidden = false;
  }

  function renderPendingNote() {
    const pending = state.pending;
    if (!pending) return;
    const notes = [];
    if (pending.stale) {
      notes.push("The document changed since this suggestion was produced. Refine again before accepting it.");
    }
    const safeguards = pending.result.safeguards || {};
    const preserved = Object.entries(safeguards)
      .filter(([, value]) => value === true)
      .map(([name]) => name.replaceAll("_", " "));
    if (preserved.length) notes.push(`Checks passed: ${preserved.join(", ")}.`);
    if ((pending.result.notices || []).length) notes.push(pending.result.notices.join(" "));
    if (!pending.original.trim()) notes.push("The selected range is empty.");
    elements.reviewNote.textContent = notes.join(" ") || "The check is a language-level suggestion, not a judgement about your scholarship.";
  }

  function closeReview(message) {
    state.pending = null;
    elements.reviewCard.hidden = true;
    if (message) showStatus(message);
  }

  function acceptReview() {
    const pending = state.pending;
    if (!pending) return;
    const current = elements.editor.value.slice(pending.start, pending.end);
    if (pending.stale || current !== pending.original) {
      elements.reviewNote.textContent =
        "This suggestion no longer matches the document at those positions, so it was not applied. Refine again to get a current suggestion.";
      showError("A stale suggestion was blocked: the text changed before you accepted it.", null);
      return;
    }
    const replacement = pending.result.refined_text;
    applyEdit(pending.start, pending.end, replacement, true);
    closeReview("Suggestion applied. Use Ctrl+Z to undo it.");
  }

  function dismissReview() {
    if (!state.pending) return;
    closeReview("Suggestion dismissed. The document was not changed.");
  }

  async function copyProposal() {
    if (!state.pending) return;
    try {
      await window.navigator.clipboard.writeText(state.pending.result.refined_text);
      showStatus("Proposal copied to the clipboard.");
    } catch {
      showStatus("Copying is unavailable here; select the proposal text and copy it manually.");
    }
  }

  // --------------------------------------------------------------- events
  elements.editor.addEventListener("input", markDirty);
  elements.editor.addEventListener("keyup", refreshDerived);
  elements.editor.addEventListener("click", refreshDerived);
  elements.editor.addEventListener("select", refreshDerived);
  elements.title.addEventListener("input", markDirty);
  elements.documentSearch.addEventListener("input", loadDocumentList);

  byId("new-document").addEventListener("click", createDocument);
  byId("save-document").addEventListener("click", () => saveDocument("manual"));
  elements.refineButton.addEventListener("click", refine);
  byId("review-accept").addEventListener("click", acceptReview);
  byId("review-dismiss").addEventListener("click", dismissReview);
  byId("review-copy").addEventListener("click", copyProposal);
  byId("retry-button").addEventListener("click", () => {
    const retry = state.retry;
    clearError();
    if (retry) retry();
  });
  byId("dismiss-error").addEventListener("click", clearError);
  byId("recover-button").addEventListener("click", () => {
    const draft = state.document && readDraft(state.document.id);
    if (!draft) return;
    elements.editor.value = draft.text;
    elements.title.value = draft.title || elements.title.value;
    elements.recoveryBanner.hidden = true;
    markDirty();
    showStatus("Recovered unsaved changes from the previous session. Save to keep them.");
  });
  byId("discard-recovery").addEventListener("click", () => {
    if (state.document) clearDraft(state.document.id);
    elements.recoveryBanner.hidden = true;
    showStatus("Unsaved changes from the previous session were discarded.");
  });
  byId("conflict-reload").addEventListener("click", async () => {
    if (!state.document) return;
    const id = state.document.id;
    elements.conflictBanner.hidden = true;
    await openDocument(id);
    showStatus("Loaded the stored version.");
  });
  byId("conflict-overwrite").addEventListener("click", async () => {
    if (!state.document) return;
    const id = state.document.id;
    try {
      const latest = await request(`/api/documents/${id}`);
      state.document = latest;
      await saveDocument("manual");
      elements.conflictBanner.hidden = true;
    } catch (error) {
      showError(`The document could not be saved: ${error.message}`);
    }
  });

  const FORMAT_BUTTONS = {
    "fmt-h1": "h1",
    "fmt-h2": "h2",
    "fmt-h3": "h3",
    "fmt-bold": "bold",
    "fmt-italic": "italic",
    "fmt-bullet": "bullet",
    "fmt-number": "number",
    "fmt-quote": "quote",
  };
  Object.entries(FORMAT_BUTTONS).forEach(([id, action]) => {
    byId(id).addEventListener("click", () => runFormat(action));
  });

  function historyEdit(command) {
    try {
      elements.editor.focus();
      document.execCommand(command);
      markDirty();
    } catch {
      showStatus("Use Ctrl+Z and Ctrl+Y for undo and redo.");
    }
  }
  byId("undo").addEventListener("click", () => historyEdit("undo"));
  byId("redo").addEventListener("click", () => historyEdit("redo"));

  document.addEventListener("keydown", (event) => {
    const modifier = event.ctrlKey || event.metaKey;
    const inEditor = event.target === elements.editor;
    if (modifier && event.key.toLowerCase() === "s") {
      event.preventDefault();
      saveDocument("manual");
      return;
    }
    if (modifier && event.key === "Enter") {
      event.preventDefault();
      refine();
      return;
    }
    if (event.key === "Escape" && state.pending) {
      dismissReview();
      return;
    }
    if (!inEditor || !modifier) return;
    const key = event.key;
    if (key === "1" || key === "2" || key === "3") {
      event.preventDefault();
      runFormat(`h${key}`);
    } else if (key.toLowerCase() === "b") {
      event.preventDefault();
      runFormat("bold");
    } else if (key.toLowerCase() === "i") {
      event.preventDefault();
      runFormat("italic");
    } else if (event.shiftKey && (key === "8" || key === "*")) {
      event.preventDefault();
      runFormat("bullet");
    } else if (event.shiftKey && (key === "7" || key === "&")) {
      event.preventDefault();
      runFormat("number");
    }
  });

  window.addEventListener("beforeunload", (event) => {
    if (!state.dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });

  // Small read-only hook used by the repository's GUI checks and by debugging.
  window.scholarflowWorkspace = {
    getState: () => ({
      documentId: state.document ? state.document.id : null,
      revision: state.document ? state.document.revision : null,
      dirty: state.dirty,
      pending: state.pending
        ? {
            start: state.pending.start,
            end: state.pending.end,
            stale: state.pending.stale,
            changed: state.pending.original.trim() !== state.pending.result.refined_text.trim(),
          }
        : null,
      documents: state.list.length,
    }),
    refine,
    save: saveDocument,
  };

  // ----------------------------------------------------------------- boot
  (async function start() {
    await loadDocumentList();
    if (state.list.length) {
      await openDocument(state.list[0].id);
    } else {
      refreshDerived();
    }
  })();
})();
