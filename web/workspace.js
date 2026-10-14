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
    // Re-check after the typing pauses; never on every keystroke.
    if (window.scheduleAnalysis) window.scheduleAnalysis();
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
    if (window.resetDiagnostics) window.resetDiagnostics();
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

  // ------------------------------------------------------------- diagnostics
  // Stage 2: local, deterministic diagnostics with inline markers, reviewable
  // corrections and a categorised sidebar. Everything runs against the local
  // server; the editor never sends text anywhere else. Markers are positioned by
  // measuring a hidden mirror of the textarea with the same text metrics, so a
  // marker always sits exactly over the characters it refers to.
  const ANALYSIS_DELAY_MS = 700;
  const MARKER_TRACK_LIMIT = 3;
  const DICTIONARY_PREFIX = "scholarflow:dictionary";
  const DISMISS_PREFIX = "scholarflow:dismissed:";

  const CATEGORY_LETTERS = {
    spelling: "S",
    agreement: "A",
    punctuation: "P",
    capitalization: "C",
    fragment: "F",
    run_on: "R",
    wordiness: "W",
    repetition: "X",
    readability: "Y",
    tone: "T",
  };

  Object.assign(elements, {
    markerLayer: byId("marker-layer"),
    markerMirror: byId("marker-mirror"),
    suggestionCard: byId("suggestion-card"),
    suggestionHeading: byId("suggestion-heading"),
    suggestionBadge: byId("suggestion-badge"),
    suggestionOriginal: byId("suggestion-original"),
    suggestionProposal: byId("suggestion-proposal"),
    suggestionProposalHeading: byId("suggestion-proposal-heading"),
    suggestionMeta: byId("suggestion-meta"),
    suggestionExplanation: byId("suggestion-explanation"),
    suggestionAlternatives: byId("suggestion-alternatives"),
    suggestionBlocked: byId("suggestion-blocked"),
    suggestionDictionary: byId("suggestion-dictionary"),
    suggestionAccept: byId("suggestion-accept"),
    suggestionDismiss: byId("suggestion-dismiss"),
    suggestionClose: byId("suggestion-close"),
    diagnosticsSummary: byId("diagnostics-summary"),
    diagnosticsList: byId("diagnostics-list"),
    diagnosticsEmpty: byId("diagnostics-empty"),
    diagnosticsMetrics: byId("diagnostics-metrics"),
    diagnosticsPrivacy: byId("diagnostics-privacy"),
    dictionaryBox: byId("dictionary-box"),
    dictionaryCount: byId("dictionary-count"),
    dictionaryWords: byId("dictionary-words"),
    filterAll: byId("filter-all"),
    filterError: byId("filter-error"),
    filterStyle: byId("filter-style"),
  });

  state.diagnostics = {
    findings: [],
    categories: [],
    counts: { total: 0, error: 0, style: 0 },
    metrics: null,
    notes: [],
    truncated: false,
    loading: false,
    text: null,
    filter: "all",
    dismissed: [],
    activeId: null,
    openId: null,
    controller: null,
    timer: null,
    requests: 0,
    checks: 0,
    error: null,
    dictionary: [],
  };

  function categoryLetter(category) {
    return CATEGORY_LETTERS[category] || (category || "?").slice(0, 1).toUpperCase();
  }

  function dismissedKey(documentId) {
    return DISMISS_PREFIX + documentId;
  }

  function readDismissed(documentId) {
    if (!documentId) return [];
    try {
      const raw = window.localStorage.getItem(dismissedKey(documentId));
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [];
    } catch {
      return [];
    }
  }

  function writeDismissed() {
    if (!state.document) return;
    try {
      window.localStorage.setItem(
        dismissedKey(state.document.id),
        JSON.stringify(state.diagnostics.dismissed.slice(-500)),
      );
    } catch {
      /* storage may be unavailable; dismissal simply does not persist */
    }
  }

  function visibleFindings() {
    const filter = state.diagnostics.filter;
    return state.diagnostics.findings.filter((finding) => {
      if (state.diagnostics.dismissed.includes(finding.id)) return false;
      if (filter === "error" && finding.kind !== "error") return false;
      if (filter === "style" && finding.kind !== "style") return false;
      return true;
    });
  }

  function findingById(id) {
    return state.diagnostics.findings.find((finding) => finding.id === id) || null;
  }

  // ------------------------------------------------------------ analysis run
  function scheduleAnalysis(delay = ANALYSIS_DELAY_MS) {
    window.clearTimeout(state.diagnostics.timer);
    if (!state.document) return;
    state.diagnostics.timer = window.setTimeout(() => analyseNow(), delay);
  }

  async function analyseNow() {
    const document_ = state.document;
    if (!document_) return null;
    const text = elements.editor.value;
    if (state.diagnostics.controller) {
      // A newer request supersedes an older one; the older answer is dropped.
      state.diagnostics.controller.abort();
    }
    const controller = new AbortController();
    state.diagnostics.controller = controller;
    state.diagnostics.loading = true;
    state.diagnostics.requests += 1;
    renderDiagnosticsPanel();
    try {
      const report = await request("/api/workspace/diagnostics", {
        method: "POST",
        body: JSON.stringify({ text, document_id: document_.id, revision: document_.revision }),
        signal: controller.signal,
      });
      if (state.diagnostics.controller !== controller) return null;
      if (elements.editor.value !== text) {
        // The document changed while the analysis ran: never show stale offsets.
        scheduleAnalysis(0);
        return null;
      }
      state.diagnostics.findings = Array.isArray(report.diagnostics) ? report.diagnostics : [];
      state.diagnostics.categories = Array.isArray(report.categories) ? report.categories : [];
      state.diagnostics.counts = report.counts || { total: 0, error: 0, style: 0 };
      state.diagnostics.metrics = report.metrics || null;
      state.diagnostics.notes = Array.isArray(report.notes) ? report.notes : [];
      state.diagnostics.truncated = Boolean(report.truncated);
      state.diagnostics.text = text;
      state.diagnostics.checks += 1;
      state.diagnostics.error = null;
      renderMarkers();
      renderDiagnosticsPanel();
      return report;
    } catch (error) {
      if (error && (error.name === "AbortError" || error.aborted)) return null;
      state.diagnostics.error = error && error.message ? error.message : "unknown error";
      renderDiagnosticsPanel();
      return null;
    } finally {
      if (state.diagnostics.controller === controller) {
        state.diagnostics.loading = false;
        state.diagnostics.controller = null;
        renderDiagnosticsPanel();
      }
    }
  }

  function resetDiagnostics({ keepDismissed = true } = {}) {
    window.clearTimeout(state.diagnostics.timer);
    if (state.diagnostics.controller) state.diagnostics.controller.abort();
    state.diagnostics.controller = null;
    state.diagnostics.findings = [];
    state.diagnostics.counts = { total: 0, error: 0, style: 0 };
    state.diagnostics.metrics = null;
    state.diagnostics.notes = [];
    state.diagnostics.truncated = false;
    state.diagnostics.text = null;
    state.diagnostics.activeId = null;
    state.diagnostics.openId = null;
    state.diagnostics.error = null;
    state.diagnostics.dismissed = keepDismissed && state.document ? readDismissed(state.document.id) : [];
    window.clearTimeout(state.diagnostics.timer);
    closeSuggestion("");
    renderMarkers();
    renderDiagnosticsPanel();
  }

  // -------------------------------------------------------------- markers
  function buildTracks(findings) {
    const tracks = [];
    const ordered = [...findings].sort((left, right) => left.start - right.start || left.end - right.end);
    for (const finding of ordered) {
      let track = tracks.find((item) => item.length === 0 || item[item.length - 1].end <= finding.start);
      if (!track) {
        track = [];
        tracks.push(track);
      }
      track.push(finding);
    }
    return tracks.slice(0, MARKER_TRACK_LIMIT);
  }

  function escapeHtml(value) {
    return value
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function markerLabel(finding) {
    const kind = finding.kind === "error" ? "Error" : "Style option";
    return `${kind}, ${finding.category_label}: ${finding.message}`;
  }

  function syncMarkerScroll() {
    const { markerLayer, editor } = elements;
    markerLayer.style.transform =
      `translate(${-editor.scrollLeft}px, ${-editor.scrollTop}px)`;
  }

  function renderMarkers() {
    const layer = elements.markerLayer;
    layer.replaceChildren();
    const findings = visibleFindings();
    if (!findings.length) {
      return;
    }
    const text = elements.editor.value;
    const mirror = elements.markerMirror;
    mirror.style.width = `${elements.editor.clientWidth}px`;
    const layerRect = layer.getBoundingClientRect();
    const tracks = buildTracks(findings);
    tracks.forEach((track, trackIndex) => {
      let cursor = 0;
      let html = "";
      for (const finding of track) {
        const start = Math.max(cursor, Math.min(finding.start, text.length));
        const end = Math.max(start, Math.min(finding.end, text.length));
        html += escapeHtml(text.slice(cursor, start));
        const body = text.slice(start, end);
        html += `<span class="marker-span" data-id="${escapeHtml(finding.id)}">${body ? escapeHtml(body) : "&#8203;"}</span>`;
        cursor = end;
      }
      html += escapeHtml(text.slice(cursor));
      mirror.innerHTML = html;
      mirror.style.width = `${elements.editor.clientWidth}px`;
      const mirrorRect = mirror.getBoundingClientRect();
      let fallbackIndex = 0;
      for (const span of mirror.querySelectorAll("span.marker-span")) {
        const finding = findingById(span.dataset.id);
        if (!finding) continue;
        let rects = Array.from(span.getClientRects()).filter(
          (rect) => rect.width > 0 || rect.height > 0,
        );
        if (!rects.length) {
          // A DOM without a layout engine (jsdom in the automated checks) cannot
          // measure text. The markers are still rendered, ordered and focusable
          // so their behaviour can be verified, but exact pixel alignment over
          // the characters needs a real rendering engine. `data-fallback` marks
          // those markers so nothing pretends they are positioned.
          rects = [
            {
              top: 0,
              left: 0,
              width: Math.max(12, finding.original.length * 8),
              height: 18,
              __fallback: true,
            },
          ];
        }
        for (const rect of rects) {
          const fallback = Boolean(rect.__fallback);
          if (fallback) fallbackIndex += 1;
          const marker = document.createElement("button");
          marker.type = "button";
          marker.className = `marker kind-${finding.kind} cat-${finding.category}`;
          if (finding.id === state.diagnostics.activeId) marker.classList.add("is-active");
          marker.dataset.id = finding.id;
          if (fallback) {
            marker.dataset.fallback = "1";
            marker.style.top = `${8 + (fallbackIndex - 1) * 22}px`;
            marker.style.left = `${8 + trackIndex * 6}px`;
          } else {
            marker.style.top = `${rect.top - mirrorRect.top + trackIndex * 1.5}px`;
            marker.style.left = `${rect.left - mirrorRect.left}px`;
          }
          marker.style.width = `${Math.max(4, rect.width)}px`;
          marker.style.height = `${Math.max(8, rect.height)}px`;
          marker.setAttribute("aria-label", markerLabel(finding));
          marker.title = markerLabel(finding);
          marker.tabIndex = finding.id === state.diagnostics.activeId ? 0 : -1;
          if (rect.width >= 10) {
            const badge = document.createElement("span");
            badge.className = "marker-badge";
            badge.setAttribute("aria-hidden", "true");
            badge.textContent = categoryLetter(finding.category);
            marker.appendChild(badge);
          }
          marker.addEventListener("click", () => openSuggestion(finding.id));
          layer.appendChild(marker);
        }
      }
    });
    syncMarkerScroll();
  }

  function scrollEditorTo(start) {
    const editor = elements.editor;
    const before = editor.value.slice(0, start);
    const line = before.split("\n").length - 1;
    const lineHeight = parseFloat(window.getComputedStyle(editor).lineHeight) || 27;
    const target = Math.max(0, line * lineHeight - editor.clientHeight / 3);
    editor.scrollTop = target;
    editor.setSelectionRange(start, start + 1);
    syncMarkerScroll();
  }

  // -------------------------------------------------------------- sidebar
  function setFilter(filter) {
    state.diagnostics.filter = filter;
    elements.filterAll.setAttribute("aria-pressed", filter === "all" ? "true" : "false");
    elements.filterError.setAttribute("aria-pressed", filter === "error" ? "true" : "false");
    elements.filterStyle.setAttribute("aria-pressed", filter === "style" ? "true" : "false");
    renderMarkers();
    renderDiagnosticsPanel();
  }

  function renderDiagnosticsPanel() {
    const diagnostics = state.diagnostics;
    const list = elements.diagnosticsList;
    const summary = elements.diagnosticsSummary;
    list.replaceChildren();
    if (!state.document) {
      summary.textContent = "No document open.";
      elements.diagnosticsEmpty.hidden = false;
      elements.diagnosticsEmpty.textContent = "Open or create a document to see diagnostics.";
      elements.diagnosticsMetrics.textContent = "";
      return;
    }
    const shown = visibleFindings();
    const dismissed = diagnostics.dismissed.length;
    const errorCount = diagnostics.findings.filter((item) => item.kind === "error").length;
    const styleCount = diagnostics.findings.filter((item) => item.kind === "style").length;
    const parts = [
      `<span class="count-error">${errorCount} error${errorCount === 1 ? "" : "s"}</span>`,
      `<span class="count-style">${styleCount} style option${styleCount === 1 ? "" : "s"}</span>`,
    ];
    if (dismissed) parts.push(`${dismissed} dismissed`);
    if (diagnostics.loading) parts.push("checking…");
    let summaryText = parts.join(" · ");
    if (diagnostics.text !== null && shown.length !== diagnostics.findings.length - dismissed) {
      summaryText += ` · showing ${shown.length}`;
    }
    summary.innerHTML = summaryText;
    elements.diagnosticsSummary.setAttribute(
      "aria-label",
      `${errorCount} errors and ${styleCount} style options, showing ${shown.length}`,
    );

    // Group by category, errors first, each group labelled with its kind.
    const groups = new Map();
    for (const finding of shown) {
      if (!groups.has(finding.category)) groups.set(finding.category, []);
      groups.get(finding.category).push(finding);
    }
    const order = diagnostics.categories.map((item) => item.id);
    const sortedCategories = [...groups.keys()].sort((left, right) => {
      const leftError = groups.get(left)[0].kind === "error" ? 0 : 1;
      const rightError = groups.get(right)[0].kind === "error" ? 0 : 1;
      if (leftError !== rightError) return leftError - rightError;
      return order.indexOf(left) - order.indexOf(right);
    });
    for (const category of sortedCategories) {
      const items = groups.get(category);
      const info = diagnostics.categories.find((item) => item.id === category) || {};
      const section = document.createElement("section");
      section.className = "diag-group";
      const heading = document.createElement("h3");
      heading.className = "diag-group-head";
      const kind = items[0].kind;
      heading.innerHTML =
        `${escapeHtml(items[0].category_label)} ` +
        `<span class="diag-kind kind-${kind}">${kind === "error" ? "errors" : "style options"}</span> ` +
        `<span class="diag-text">(${items.length})</span>`;
      section.appendChild(heading);
      if (info.hint) {
        const hint = document.createElement("p");
        hint.className = "diag-hint";
        hint.textContent = info.hint;
        section.appendChild(hint);
      }
      for (const finding of items) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `diag-finding kind-${finding.kind}`;
        button.dataset.id = finding.id;
        button.setAttribute(
          "aria-label",
          `${finding.kind === "error" ? "Error" : "Style option"} in ${finding.category_label}: ${finding.message}. ${finding.explanation}`,
        );
        if (finding.id === diagnostics.activeId) button.classList.add("is-active");
        const letter = document.createElement("span");
        letter.className = "diag-letter";
        letter.setAttribute("aria-hidden", "true");
        letter.textContent = categoryLetter(finding.category);
        button.appendChild(letter);
        const label = document.createElement("span");
        const snippet = finding.original.replace(/\s+/g, " ").slice(0, 60);
        label.innerHTML = `${escapeHtml(finding.message)} <span class="diag-text">“${escapeHtml(snippet)}”</span>`;
        button.appendChild(label);
        button.addEventListener("click", () => openSuggestion(finding.id));
        section.appendChild(button);
      }
      list.appendChild(section);
    }

    if (shown.length) {
      elements.diagnosticsEmpty.hidden = true;
      elements.diagnosticsEmpty.textContent = "";
    } else {
      elements.diagnosticsEmpty.hidden = false;
      if (diagnostics.loading) {
        elements.diagnosticsEmpty.textContent = "Checking this document…";
      } else if (diagnostics.error) {
        elements.diagnosticsEmpty.textContent = `Diagnostics could not run: ${diagnostics.error}. Your text is unchanged.`;
      } else if (diagnostics.findings.length) {
        const which = diagnostics.filter === "error" ? "errors" : "style suggestions";
        elements.diagnosticsEmpty.textContent = `No ${which} here. Switch the filter to see the other findings.`;
      } else {
        elements.diagnosticsEmpty.textContent =
          "No findings. Your text passed every local rule for the categories checked.";
      }
    }
    if (diagnostics.notes.length && !diagnostics.error) {
      elements.diagnosticsEmpty.hidden = false;
      elements.diagnosticsEmpty.textContent = diagnostics.notes.join(" ");
    }
    renderMetrics();

    if (diagnostics.dictionary.length !== elements.dictionaryWords.childElementCount) {
      renderDictionary();
    } else {
      elements.dictionaryCount.textContent = String(diagnostics.dictionary.length);
    }
  }

  function renderMetrics() {
    const metrics = state.diagnostics.metrics;
    if (!metrics) {
      elements.diagnosticsMetrics.textContent = "";
      return;
    }
    const ease = metrics.flesch_reading_ease;
    const band = ease >= 60 ? "plain" : ease >= 30 ? "fairly difficult" : "difficult";
    elements.diagnosticsMetrics.textContent =
      `${metrics.words.toLocaleString()} words · ${metrics.sentences.toLocaleString()} sentences · ` +
      `readability ${ease} (${band}) · longest paragraph ${metrics.longest_paragraph_words} words` +
      (state.diagnostics.truncated ? " · showing the first findings only" : "");
  }

  function renderDictionary() {
    const words = state.diagnostics.dictionary;
    elements.dictionaryCount.textContent = String(words.length);
    elements.dictionaryWords.replaceChildren();
    for (const word of words) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${word} ✕`;
      button.setAttribute("aria-label", `Remove ${word} from the personal dictionary`);
      button.addEventListener("click", async () => {
        await loadDictionary(`/api/workspace/dictionary/${encodeURIComponent(word)}`, { method: "DELETE" });
        scheduleAnalysis(0);
      });
      elements.dictionaryWords.appendChild(button);
    }
  }

  async function loadDictionary(path = "/api/workspace/dictionary", options = {}) {
    try {
      const payload = await request(path, options);
      state.diagnostics.dictionary = Array.isArray(payload.words) ? payload.words : [];
      renderDictionary();
      return payload;
    } catch (error) {
      showStatus(`The personal dictionary could not be updated: ${error.message}`);
      return null;
    }
  }

  // ----------------------------------------------------------- suggestion card
  function openSuggestion(id) {
    const finding = findingById(id);
    if (!finding) return;
    state.diagnostics.openId = id;
    state.diagnostics.activeId = id;
    renderSuggestion();
    renderMarkers();
    renderDiagnosticsPanel();
    elements.suggestionCard.hidden = false;
    elements.suggestionCard.scrollIntoView({ block: "nearest" });
    elements.suggestionAccept.focus();
  }

  function renderSuggestion() {
    const finding = findingById(state.diagnostics.openId);
    if (!finding) return false;
    const kind = finding.kind === "error" ? "Error" : "Style option";
    elements.suggestionHeading.textContent = finding.category_label;
    elements.suggestionBadge.textContent = kind;
    elements.suggestionBadge.className = `badge kind-${finding.kind}`;
    elements.suggestionOriginal.textContent = finding.original;
    const hasReplacement = Boolean(finding.replacement);
    elements.suggestionProposal.textContent = hasReplacement
      ? finding.replacement
      : "(no automatic replacement — review the explanation)";
    elements.suggestionProposalHeading.textContent = hasReplacement ? "Proposed correction" : "Correction";
    elements.suggestionMeta.textContent =
      `${kind} · ${finding.confidence} confidence · rule ${finding.rule} · characters ${finding.start}-${finding.end}`;
    elements.suggestionExplanation.textContent = finding.explanation;
    elements.suggestionAccept.disabled = !hasReplacement;
    elements.suggestionAccept.setAttribute("aria-disabled", hasReplacement ? "false" : "true");
    elements.suggestionBlocked.hidden = true;
    elements.suggestionBlocked.textContent = "";
    elements.suggestionDictionary.hidden = finding.category !== "spelling";
    elements.suggestionDictionary.dataset.word = finding.original;
    elements.suggestionAlternatives.replaceChildren();
    for (const alternative of finding.replacements) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = alternative;
      button.setAttribute("aria-label", `Use “${alternative}” instead`);
      button.addEventListener("click", () => acceptSuggestion(alternative));
      elements.suggestionAlternatives.appendChild(button);
    }
    return true;
  }

  function closeSuggestion(message = "") {
    state.diagnostics.openId = null;
    elements.suggestionCard.hidden = true;
    if (message) showStatus(message);
  }

  function blockSuggestion(message) {
    elements.suggestionBlocked.hidden = false;
    elements.suggestionBlocked.textContent = message;
  }

  function acceptSuggestion(alternative = null) {
    const finding = findingById(state.diagnostics.openId);
    if (!finding) return;
    const replacement = alternative !== null ? alternative : finding.replacement;
    if (replacement === null || replacement === undefined) {
      blockSuggestion("This finding has no automatic correction. Accept is disabled on purpose: applying one would change your meaning.");
      return;
    }
    const text = elements.editor.value;
    const current = text.slice(finding.start, finding.end);
    if (state.diagnostics.text !== text || current !== finding.original) {
      // The text moved since the analysis: refuse rather than corrupt it.
      blockSuggestion(
        "This suggestion no longer matches the text at those characters, so it was not applied. " +
          "Re-checking the document instead.",
      );
      scheduleAnalysis(0);
      return;
    }
    applyEdit(finding.start, finding.end, replacement);
    closeSuggestion(`${finding.category_label} applied; the document is marked as unsaved.`);
    scheduleAnalysis(0);
  }

  function dismissSuggestion() {
    const finding = findingById(state.diagnostics.openId);
    if (!finding) return;
    if (!state.diagnostics.dismissed.includes(finding.id)) {
      state.diagnostics.dismissed.push(finding.id);
      writeDismissed();
    }
    closeSuggestion("Dismissed. The text was not changed.");
    renderMarkers();
    renderDiagnosticsPanel();
  }

  async function addFindingWordToDictionary() {
    const finding = findingById(state.diagnostics.openId);
    if (!finding || finding.category !== "spelling") return;
    const word = elements.suggestionDictionary.dataset.word || finding.original;
    const payload = await loadDictionary("/api/workspace/dictionary", {
      method: "POST",
      body: JSON.stringify({ word }),
    });
    if (payload) {
      closeSuggestion(`“${word}” was added to your personal dictionary.`);
      scheduleAnalysis(0);
    }
  }

  function restoreDismissed() {
    state.diagnostics.dismissed = [];
    writeDismissed();
    renderMarkers();
    renderDiagnosticsPanel();
    showStatus("Dismissed findings are shown again.");
  }

  function focusFinding(delta) {
    const findings = visibleFindings();
    if (!findings.length) {
      showStatus("There are no findings to move between in this view.");
      return;
    }
    const index = findings.findIndex((finding) => finding.id === state.diagnostics.activeId);
    const nextIndex = index < 0 ? (delta > 0 ? 0 : findings.length - 1) : (index + delta + findings.length) % findings.length;
    const finding = findings[nextIndex];
    state.diagnostics.activeId = finding.id;
    scrollEditorTo(finding.start);
    renderMarkers();
    renderDiagnosticsPanel();
    const marker = elements.markerLayer.querySelector(`.marker[data-id="${finding.id}"]`);
    if (marker) marker.focus({ preventScroll: true });
  }

  function moveMarkerFocus(event) {
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      focusFinding(1);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      focusFinding(-1);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      const target = event.target.closest ? event.target.closest(".marker") : null;
      openSuggestion(target ? target.dataset.id : state.diagnostics.activeId);
    } else if (event.key === "Escape") {
      closeSuggestion();
    }
  }

  elements.markerLayer.addEventListener("keydown", moveMarkerFocus);
  elements.filterAll.addEventListener("click", () => setFilter("all"));
  elements.filterError.addEventListener("click", () => setFilter("error"));
  elements.filterStyle.addEventListener("click", () => setFilter("style"));
  elements.editor.addEventListener("scroll", syncMarkerScroll);
  window.addEventListener("resize", () => renderMarkers());
  byId("finding-next").addEventListener("click", () => focusFinding(1));
  byId("finding-previous").addEventListener("click", () => focusFinding(-1));
  byId("finding-recheck").addEventListener("click", () => analyseNow());
  byId("suggestion-accept").addEventListener("click", () => acceptSuggestion());
  byId("suggestion-dismiss").addEventListener("click", dismissSuggestion);
  byId("suggestion-dictionary").addEventListener("click", addFindingWordToDictionary);
  byId("suggestion-close").addEventListener("click", () => closeSuggestion());
  elements.diagnosticsList.addEventListener("click", (event) => {
    const button = event.target.closest && event.target.closest(".diag-finding");
    if (button) openSuggestion(button.dataset.id);
  });
  elements.dictionaryBox.addEventListener("toggle", () => {
    if (elements.dictionaryBox.open) loadDictionary();
  });
  loadDictionary();

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
    if (event.key === "Escape") {
      if (state.pending) {
        dismissReview();
        return;
      }
      if (state.diagnostics && state.diagnostics.openId) {
        closeSuggestion();
        return;
      }
    }
    if (event.altKey && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault();
      focusFinding(event.key === "ArrowDown" ? 1 : -1);
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

  // The diagnostics module is defined after the helpers it uses; publish the two
  // hooks it needs so edits and document changes trigger a re-check.
  window.scheduleAnalysis = scheduleAnalysis;
  window.resetDiagnostics = resetDiagnostics;

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
      diagnostics: {
        count: state.diagnostics.findings.length,
        error: state.diagnostics.counts.error || 0,
        style: state.diagnostics.counts.style || 0,
        shown: visibleFindings().length,
        filter: state.diagnostics.filter,
        dismissed: state.diagnostics.dismissed.length,
        activeId: state.diagnostics.activeId,
        openId: state.diagnostics.openId,
        loading: state.diagnostics.loading,
        requests: state.diagnostics.requests,
        checks: state.diagnostics.checks,
        analysedText: state.diagnostics.text,
        error: state.diagnostics.error,
        categories: state.diagnostics.categories.map((item) => item.id),
        findings: state.diagnostics.findings.map((item) => ({
          id: item.id,
          category: item.category,
          kind: item.kind,
          start: item.start,
          end: item.end,
          original: item.original,
          replacement: item.replacement,
          replacements: item.replacements,
          message: item.message,
          confidence: item.confidence,
        })),
      },
      dictionary: state.diagnostics.dictionary,
    }),
    refine,
    save: saveDocument,
    analyse: analyseNow,
    acceptSuggestion,
    dismissSuggestion,
    openSuggestion,
    setFilter,
    focusFinding,
    restoreDismissed,
    dictionary: { list: loadDictionary, add: addFindingWordToDictionary },
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
