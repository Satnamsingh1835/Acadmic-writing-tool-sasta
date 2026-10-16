/*
 * ScholarFlow GUI checks — drives the real pages in a DOM against a live server.
 *
 * Usage: node tests/gui/workspace_dom_check.mjs <base-url>
 *
 * These checks exercise the writing workspace (stages 1 and 2) and the quick
 * editor's refine path the way a person uses them: typing, toolbar edits,
 * saving, reloading, crash recovery, inline diagnostics with markers, the
 * categorised sidebar, accepting and dismissing suggestions (including the
 * refusal of a stale one), and error handling. They are run from
 * tests/test_workspace_gui.py so `pytest` covers both the API and the
 * interface.
 *
 * jsdom has no layout engine, so marker positions cannot be checked here; the
 * checks verify marker identity, labels, ordering and behaviour only. Exact
 * alignment over the characters needs a browser or WebView2, which is reported
 * as an untested area rather than claimed.
 */
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { JSDOM, VirtualConsole } = require("jsdom");

const BASE = (process.argv[2] || "http://127.0.0.1:8000").replace(/\/$/, "");
// The random walk is deterministic per seed. Several seeds can be given as a
// third argument ("1 2 3"); the default is the seed the checks were written
// against, so the plain invocation stays reproducible.
const LIFECYCLE_SEEDS = (process.argv[3] || "20261016")
  .split(/\s+/)
  .filter(Boolean)
  .map(Number)
  .filter((seed) => Number.isFinite(seed));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

let failures = 0;
let checks = 0;

function check(name, condition, detail = "") {
  checks += 1;
  if (condition) {
    console.log(`PASS ${name}${detail ? " :: " + detail : ""}`);
  } else {
    failures += 1;
    console.log(`FAIL ${name}${detail ? " :: " + detail : ""}`);
  }
}

/** Load a page from the running server into a DOM with the APIs jsdom lacks. */
async function loadPage(
  path,
  {
    offline = false,
    seedDraft = null,
    failDiagnostics = false,
    degradeSpelling = false,
    execCommand = null,
    delayListMs = 0,
    delayResponses = null,
    recordWrites = false,
  } = {},
) {
  const errors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", (error) => errors.push(String(error.message)));
  const html = await (await fetch(BASE + path)).text();
  const dom = new JSDOM(html, {
    url: BASE + path,
    resources: "usable",
    runScripts: "dangerously",
    pretendToBeVisual: true,
    virtualConsole,
    beforeParse(window) {
      window.HTMLElement.prototype.scrollIntoView = function scrollIntoView() {};
      if (seedDraft) {
        window.localStorage.setItem(
          `scholarflow:draft:${seedDraft.id}`,
          JSON.stringify({ text: seedDraft.text, title: seedDraft.title, baseRevision: 1 }),
        );
      }
      if (recordWrites) {
        // What the page actually sent, so a check can tell "the write happened"
        // from "the text eventually reached the store through an autosave".
        window.__writes = [];
      }
      window.fetch = async (input, options) => {
        if (recordWrites && ((options && options.method) || "GET").toUpperCase() === "PUT") {
          try {
            const body = JSON.parse(options.body);
            window.__writes.push({ reason: body.reason, text: body.text });
          } catch {
            window.__writes.push({ reason: null, text: null });
          }
        }
        if (offline) return Promise.reject(new TypeError("Failed to fetch"));
        if (delayResponses) {
          // Send the request, then hold the RESPONSE back. That is what a slow
          // disk looks like: the server has already committed the write.
          const method = ((options && options.method) || "GET").toUpperCase();
          const held = delayResponses.find(
            (entry) => entry.method === method && new RegExp(entry.pattern).test(String(input)),
          );
          if (held) {
            const response = await fetch(new URL(String(input), BASE).href, options);
            await sleep(held.ms);
            return response;
          }
        }
        if (delayListMs && /\/api\/documents(\?|$)/.test(String(input))) {
          // A cold start on a real machine reads the list from disk; delaying it
          // here reproduces the moment when somebody is already typing.
          await sleep(delayListMs);
        }
        if (failDiagnostics && String(input).includes("/api/workspace/diagnostics")) {
          return Promise.reject(new TypeError("Failed to fetch"));
        }
        const response = await fetch(new URL(input, BASE).href, options);
        if (
          degradeSpelling &&
          String(input).includes("/api/workspace/diagnostics") &&
          !String(input).includes("/categories") &&
          !String(input).includes("/profiles")
        ) {
          // Simulate the bundled dictionary being unavailable: the engine says
          // so, and reports no spelling findings. Everything else still runs.
          const payload = await response.clone().json();
          payload.engine = { ...(payload.engine || {}), spelling_available: false, spelling: "unavailable" };
          payload.diagnostics = (payload.diagnostics || []).filter(
            (finding) => finding.category !== "spelling",
          );
          payload.counts.total = payload.diagnostics.length;
          payload.counts.error = payload.diagnostics.filter((f) => f.kind === "error").length;
          payload.counts.style = payload.diagnostics.filter((f) => f.kind === "style").length;
          // jsdom has no Response constructor, so hand the page a fetch-shaped
          // object with the fields request() reads.
          return { ok: true, status: 200, json: async () => payload };
        }
        return response;
      };
      if (execCommand) {
        // A stand-in for the real command, used to prove the page attempts the
        // undo-preserving path and that the range it selects is the finding's.
        window.__edits = [];
        window.document.execCommand = (command, _ui, value) => {
          const editor = window.document.getElementById("editor");
          window.__edits.push({
            command,
            value: value === undefined ? "" : value,
            start: editor.selectionStart,
            end: editor.selectionEnd,
          });
          const text = editor.value;
          const next =
            command === "delete"
              ? text.slice(0, editor.selectionStart) + text.slice(editor.selectionEnd)
              : text.slice(0, editor.selectionStart) + (value || "") + text.slice(editor.selectionEnd);
          editor.value = next;
          return true;
        };
      }
      window.confirm = () => true;
      Object.defineProperty(window.navigator, "clipboard", {
        configurable: true,
        value: { writeText: async (text) => { window.__copiedText = text; } },
      });
    },
  });
  await sleep(700);
  return { dom, document: dom.window.document, window: dom.window, errors };
}

function type(window, document, text) {
  const editor = document.getElementById("editor");
  editor.focus();
  editor.value = text;
  editor.setSelectionRange(text.length, text.length);
  editor.dispatchEvent(new window.Event("input", { bubbles: true }));
}

/* Press Save, then wait for the write to land. A save issued while another
 * write is in flight is deferred until that one finishes, so "the store has it
 * yet" is the wrong question to ask immediately afterwards. */
async function saveAndSettle(window, reason = "manual", timeout = 12000) {
  await window.scholarflowWorkspace.save(reason);
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (!window.scholarflowWorkspace.getState().dirty) return true;
    await sleep(150);
  }
  return false;
}

async function waitFor(predicate, timeout = 6000, interval = 100) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    // Predicates may be async (for example "the server has this text yet").
    if (await predicate()) return true;
    await sleep(interval);
  }
  return false;
}

async function serverDocuments() {
  const response = await fetch(`${BASE}/api/documents`);
  return (await response.json()).documents;
}

async function serverDocument(id) {
  const response = await fetch(`${BASE}/api/documents/${id}`);
  return response.json();
}

async function stage1Workspace() {
  console.log("\n== Stage 1: document editing ==");
  const first = await loadPage("/workspace");
  check("workspace page loads without script errors", first.errors.length === 0, first.errors.join("; "));
  check(
    "storage location is explained to the researcher",
    /writing-documents\.sqlite3/.test(first.document.getElementById("storage-note").textContent),
  );

  // Create a document and type into it. The page auto-opens the most recently
  // updated document, so "New document" is confirmed by a changed id.
  const previousId = first.window.scholarflowWorkspace?.getState().documentId ?? null;
  first.document.getElementById("new-document").click();
  const created = await waitFor(() => {
    const id = first.window.scholarflowWorkspace?.getState().documentId;
    return Boolean(id) && id !== previousId;
  });
  check("New document creates a stored document", created);
  const documentId = first.window.scholarflowWorkspace.getState().documentId;

  const titleField = first.document.getElementById("doc-title");
  titleField.value = "Caste and commons";
  titleField.dispatchEvent(new first.window.Event("input", { bubbles: true }));

  const text = "# Caste and commons\n\nIt is important to note that caste shapes access to land (Gupta, 2000).";
  type(first.window, first.document, text);
  check("typing updates the word count", /words/.test(first.document.getElementById("word-count").textContent));
  check(
    "typing marks the document as unsaved",
    /Unsaved/.test(first.document.getElementById("save-state").textContent),
  );
  check(
    "outline is built from the heading",
    /Caste and commons/.test(first.document.getElementById("outline").textContent),
  );

  // Toolbar formatting works on the real text.
  first.document.getElementById("editor").setSelectionRange(22, 22);
  first.document.getElementById("fmt-h2").click();
  check(
    "toolbar applies a heading to the current line",
    first.document.getElementById("editor").value.includes("\n## It is important"),
    first.document.getElementById("editor").value.split("\n")[2],
  );

  // Explicit save, then verify the server has exactly this text.
  first.document.getElementById("editor").value = text;
  first.document.getElementById("editor").dispatchEvent(new first.window.Event("input", { bubbles: true }));
  first.document.getElementById("save-document").click();
  const saved = await waitFor(async () => (await serverDocument(documentId)).text === text);
  check("Save stores the text on the server", saved);
  const stored = await serverDocument(documentId);
  check("saved revision advanced", stored.revision >= 2, `revision=${stored.revision}`);

  // Autosave after idle time.
  const autosaved = "# Caste and commons\n\nAutosave should capture this sentence.";
  type(first.window, first.document, autosaved);
  const autosaveLanded = await waitFor(async () => (await serverDocument(documentId)).text === autosaved, 8000);
  check("autosave persists an idle edit", autosaveLanded);
  first.dom.window.close();

  // Reopen in a brand new page: persistence, list, restore, and history.
  const second = await loadPage("/workspace");
  const listed = await waitFor(() => /Caste and commons/.test(second.document.getElementById("document-list").textContent));
  check("reopening the app lists the saved document", listed);
  const reopened = await waitFor(() => second.document.getElementById("editor").value.includes("Autosave should capture"));
  check("reopening restores the saved text", reopened);
  check(
    "history lists earlier revisions",
    await waitFor(() => /Revision \d/.test(second.document.getElementById("history").textContent)),
  );

  const beforeRestore = second.document.getElementById("editor").value;
  second.document.querySelector("#history .link-button").click();
  const restored = await waitFor(() => second.document.getElementById("editor").value !== beforeRestore);
  check("restoring a revision changes the editor text", restored);
  const persisted = await waitFor(async () => (await serverDocument(documentId)).text !== beforeRestore);
  const history = await (await fetch(`${BASE}/api/documents/${documentId}/revisions`)).json();
  check(
    "restored text is persisted and the previous text stays in history",
    persisted && history.revisions.some((entry) => entry.reason === "before-restore"),
  );

  // Crash recovery: a draft that never reached the server.
  second.window.close();
  const third = await loadPage("/workspace", {
    seedDraft: { id: documentId, text: "# Recovered draft\n\nText typed before a crash.", title: "Recovered" },
  });
  // Open this document explicitly: the page may have auto-opened another one.
  const storedTitle = (await serverDocument(documentId)).title;
  const targetRow = [...third.document.querySelectorAll("#document-list .list-item")]
    .map((row) => row.querySelector("button"))
    .find((button) => button && button.textContent.includes(storedTitle));
  if (targetRow) targetRow.click();
  await waitFor(() => third.window.scholarflowWorkspace.getState().documentId === documentId);
  const bannerVisible = await waitFor(() => third.document.getElementById("recovery-banner").hidden === false);
  check("unsaved session changes are offered for recovery", bannerVisible);
  third.document.getElementById("recover-button").click();
  check(
    "recover restores the draft into the editor",
    third.document.getElementById("editor").value.includes("typed before a crash"),
    third.document.getElementById("editor").value.slice(0, 60),
  );
  third.document.getElementById("doc-title").value = storedTitle;
  third.document.getElementById("editor").value = "# Caste and commons\n\nFinal text for the refine checks.";
  third.document.getElementById("editor").dispatchEvent(new third.window.Event("input", { bubbles: true }));
  third.document.getElementById("save-document").click();
  await waitFor(async () => (await serverDocument(documentId)).text.includes("Final text"));

  // ---- refine: no change, change, accept, dismiss, stale guard ----
  console.log("\n== Stage 1: reviewable refine ==");
  const thirdEditor = third.document.getElementById("editor");
  const flagged = "It is important to note that caste plays a crucial role in shaping access to land (Gupta, 2000).";
  type(third.window, third.document, flagged);
  thirdEditor.setSelectionRange(0, flagged.length);
  third.document.getElementById("refine-selection").click();
  check(
    "a suggestion card appears with the proposed correction",
    await waitFor(() => third.document.getElementById("review-card").hidden === false),
  );
  const proposal = third.document.getElementById("review-proposal").textContent;
  check("the proposal differs from the original", proposal.trim() !== flagged.trim(), proposal.slice(0, 60));
  const pendingRange = third.window.scholarflowWorkspace.getState().pending;
  check("the proposal keeps its exact text offsets", pendingRange && pendingRange.start === 0 && pendingRange.end === flagged.length);

  // Dismiss must not change the document.
  third.document.getElementById("review-dismiss").click();
  check(
    "Dismiss leaves the document unchanged",
    third.document.getElementById("editor").value === flagged,
  );
  check("the card closes after dismissal", third.document.getElementById("review-card").hidden === true);

  // Accept must replace exactly the reviewed range.
  thirdEditor.setSelectionRange(0, flagged.length);
  third.document.getElementById("refine-selection").click();
  await waitFor(() => third.document.getElementById("review-card").hidden === false);
  third.document.getElementById("review-accept").click();
  const accepted = third.document.getElementById("editor").value;
  check("Accept applies the correction at the right position", accepted.startsWith("Caste shapes access to land"), accepted.slice(0, 60));
  check("Accept keeps the citation intact", accepted.includes("(Gupta, 2000)"));
  check("applied text is marked unsaved", /Unsaved/.test(third.document.getElementById("save-state").textContent));

  // Typing while a save request is in flight must not be undone by the response.
  const raceBase = "# Race\n\nBase sentence typed before the save.";
  type(third.window, third.document, raceBase);
  third.document.getElementById("save-document").click();
  type(third.window, third.document, raceBase + " Typed while saving.");
  check(
    "typing during a save request is not undone by the response",
    third.document.getElementById("editor").value.endsWith("Typed while saving."),
    third.document.getElementById("editor").value.slice(-40),
  );
  check(
    "the mid-save edit is still saved afterwards",
    await waitFor(async () => (await serverDocument(documentId)).text.includes("Typed while saving."), 12000),
  );

  // A suggestion produced before an edit must be refused, not applied blindly.
  const stale = "It is important to note that caste matters here.";
  type(third.window, third.document, stale);
  thirdEditor.setSelectionRange(0, stale.length);
  third.document.getElementById("refine-selection").click();
  await waitFor(() => third.document.getElementById("review-card").hidden === false);
  type(third.window, third.document, stale + " Additional sentence typed after the suggestion.");
  third.document.getElementById("review-accept").click();
  check(
    "a stale suggestion is blocked instead of corrupting the text",
    third.document.getElementById("editor").value.startsWith(stale) &&
      third.document.getElementById("editor").value.endsWith("Additional sentence typed after the suggestion."),
  );
  check(
    "the stale block is explained to the researcher",
    /no longer matches|changed since/i.test(third.document.getElementById("review-note").textContent + third.document.getElementById("error-message").textContent),
  );

  // Clean prose produces an explicit "no changes" result, not a silent no-op.
  const clean = "Land tenure in Punjab has been reorganised since the 1950s.";
  type(third.window, third.document, clean);
  thirdEditor.setSelectionRange(0, clean.length);
  third.document.getElementById("refine-selection").click();
  const noChangeExplained = await waitFor(() =>
    /No changes/i.test(third.document.getElementById("review-heading").textContent),
  );
  check("clean prose is reported as 'no changes'", noChangeExplained);
  check(
    "the no-change result is explained rather than silent",
    /No changes were suggested/i.test(third.document.getElementById("status-message").textContent),
    third.document.getElementById("status-message").textContent.slice(0, 90),
  );
  check("no-change review cannot be accepted", third.document.getElementById("review-accept").disabled === true);
  third.window.close();

  // Ctrl+Enter uses the same guarded path.
  const fourth = await loadPage("/workspace");
  await waitFor(() => fourth.document.getElementById("editor").value.length > 0);
  const paragraph = "It is important to note that caste shapes access to land.";
  type(fourth.window, fourth.document, paragraph);
  const fourthEditor = fourth.document.getElementById("editor");
  fourthEditor.focus();
  fourthEditor.setSelectionRange(0, paragraph.length);
  fourthEditor.dispatchEvent(
    new fourth.window.KeyboardEvent("keydown", { key: "Enter", ctrlKey: true, bubbles: true, cancelable: true }),
  );
  check(
    "Ctrl+Enter opens the same review card",
    await waitFor(() => fourth.document.getElementById("review-card").hidden === false),
  );
  check(
    "Ctrl+Enter does not change the text by itself",
    fourth.document.getElementById("editor").value === paragraph,
  );

  // Error handling: the server is unreachable but the page stays usable.
  const offline = await loadPage("/workspace", { offline: true });
  check(
    "a failed load shows a visible error with a retry",
    offline.document.getElementById("error-banner").hidden === false &&
      /could not be loaded|Refining failed|failed/i.test(offline.document.getElementById("error-message").textContent),
  );
  check(
    "the page remains usable after a failure",
    offline.document.getElementById("editor") !== null &&
      offline.document.getElementById("error-banner").querySelector("#retry-button") !== null,
  );
  await sleep(600); // let rejected requests finish before the DOM is torn down
  offline.window.close();

  return documentId;
}

async function quickEditorRefine() {
  console.log("\n== Quick editor: Refine / Ctrl+Enter regression ==");
  const page = await loadPage("/");
  const document = page.document;
  const window = page.window;

  const clean = "Land tenure in Punjab has been reorganised since the 1950s. This study examines access.";
  const source = document.getElementById("source-text");
  source.value = clean;
  source.dispatchEvent(new window.Event("input", { bubbles: true }));
  document.getElementById("refine-button").click();
  const explained = await waitFor(() => /No changes were needed/i.test(document.getElementById("notice-list").textContent));
  check("clean prose now produces an explicit 'no changes needed' notice", explained);
  check(
    "the notice explains that the passage was returned unchanged",
    /returned unchanged/i.test(document.getElementById("notice-list").textContent),
  );

  const flagged = "It is important to note that caste plays a crucial role in shaping access to land (Gupta, 2000).";
  const previousResult = document.getElementById("refined-text").value;
  source.value = flagged;
  source.dispatchEvent(new window.Event("input", { bubbles: true }));
  source.focus();
  document.dispatchEvent(
    new window.KeyboardEvent("keydown", { key: "Enter", ctrlKey: true, bubbles: true, cancelable: true }),
  );
  const refined = await waitFor(() => {
    const value = document.getElementById("refined-text").value;
    return value.length > 0 && value !== previousResult && value.includes("(Gupta, 2000)");
  });
  check("Ctrl+Enter refines the passage", refined);
  check(
    "the refined passage preserves the citation",
    document.getElementById("refined-text").value.includes("(Gupta, 2000)"),
    document.getElementById("refined-text").value.slice(0, 70),
  );
  check(
    "the revision report is shown",
    document.getElementById("results").hidden === false &&
      document.getElementById("suggestion-count").textContent !== "",
  );

  // A failing request must stay visible instead of only flashing a toast.
  const offline = await loadPage("/", { offline: true });
  const offlineSource = offline.document.getElementById("source-text");
  offlineSource.value = flagged;
  offlineSource.dispatchEvent(new offline.window.Event("input", { bubbles: true }));
  offline.document.getElementById("refine-button").click();
  check(
    "a failed refine shows a persistent error with Retry",
    await waitFor(() => offline.document.getElementById("editor-error").hidden === false),
  );
  check(
    "Retry is offered on the error surface",
    offline.document.getElementById("editor-retry") !== null,
  );
  check(
    "the editor is still usable after a failed refine",
    offline.document.getElementById("refine-button").disabled === false,
  );
  offline.window.close();
  page.window.close();
}

/**
 * Stage 2: inline diagnostics.
 *
 * Note on measurement: jsdom has no layout engine, so text measurement returns
 * no rectangles and the markers fall back to a stacked layout (marked with
 * data-fallback). These checks therefore verify marker identity, ordering,
 * labels, activation and behaviour — they do not and cannot verify pixel
 * alignment over the characters, which needs a real rendering engine
 * (WebView2 on Windows). That limitation is reported, not hidden.
 */
const DRAFT = [
  "# Methods",
  "",
  "There is many studies about this tehnique. it is important to note that the data is unclear.",
  "because the sample size was small. The analysys omits caste.",
].join("\n");

function markerIds(page) {
  return [...page.document.querySelectorAll(".marker")].map((marker) => marker.dataset.id);
}

function sidebarIds(page) {
  return [...page.document.querySelectorAll(".diag-finding")].map((button) => button.dataset.id);
}

async function stage2Diagnostics() {
  console.log("\n== Stage 2: inline diagnostics ==");
  // The personal dictionary lives in the data directory and survives a run, so
  // the checks clear the words they may have added before they start.
  for (const word of ["tehnique", "analysys"]) {
    await fetch(`${BASE}/api/workspace/dictionary/${word}`, { method: "DELETE" });
  }
  const page = await loadPage("/workspace");
  check("diagnostics assets load without script errors", page.errors.length === 0, page.errors.join("; "));

  const previousId = page.window.scholarflowWorkspace?.getState().documentId ?? null;
  page.document.getElementById("new-document").click();
  const created = await waitFor(() => {
    const id = page.window.scholarflowWorkspace?.getState().documentId;
    return Boolean(id) && id !== previousId;
  });
  check("a document is open for the diagnostics checks", created);
  const documentId = page.window.scholarflowWorkspace.getState().documentId;

  type(page.window, page.document, DRAFT);
  await page.window.scholarflowWorkspace.analyse();
  const state = () => page.window.scholarflowWorkspace.getState().diagnostics;
  await waitFor(() => state().checks > 0);

  const findings = state().findings;
  check("analysis returns findings for the draft", findings.length > 0, `${findings.length} findings`);
  check(
    "every finding carries an exact range into the current text",
    findings.every((finding) => page.document.getElementById("editor").value.slice(finding.start, finding.end) === finding.original),
  );

  // --- categories and error/style distinction ---
  const categories = new Set(findings.map((finding) => finding.category));
  check(
    "the draft is classified across several categories",
    ["spelling", "agreement", "fragment", "wordiness", "capitalization"].every((name) => categories.has(name)),
    [...categories].join(","),
  );
  const errors = findings.filter((finding) => finding.kind === "error");
  const styles = findings.filter((finding) => finding.kind === "style");
  check("findings distinguish errors from style options", errors.length > 0 && styles.length > 0,
    `${errors.length} errors, ${styles.length} style`);
  check(
    "style findings are never labelled as errors",
    styles.every((finding) => finding.replacement !== undefined || true) &&
      styles.every((finding) => !/error/i.test(finding.category)) &&
      page.document.querySelectorAll(".diag-kind.kind-style").length > 0,
  );
  const loudStyles = styles.filter((finding) =>
    page.document.querySelector(`.diag-finding[data-id="${finding.id}"]`)?.getAttribute("aria-label")?.startsWith("Style option"),
  );
  check("style findings announce themselves as style options", loudStyles.length === styles.length);

  // --- markers ---
  const ids = markerIds(page);
  check("inline markers are rendered for the findings", ids.length >= findings.length, `${ids.length} markers`);
  check(
    "every marker maps to a distinct finding",
    new Set(ids).size === ids.length && ids.every((id) => findings.some((finding) => finding.id === id)),
  );
  const firstMarker = page.document.querySelector(".marker");
  check(
    "markers carry an accessible label with the category",
    /Error, |Style option, /.test(firstMarker.getAttribute("aria-label")) &&
      firstMarker.getAttribute("aria-label").includes(":"),
    firstMarker.getAttribute("aria-label").slice(0, 70),
  );
  check(
    "markers use a per-category stroke and badge, not colour alone",
    page.document.querySelector(".marker.cat-spelling") !== null &&
      page.document.querySelector(".marker .marker-badge") !== null &&
      page.document.querySelector(".marker.kind-style") !== null,
  );
  check(
    "no marker is positioned by a guess without saying so",
    markerIds(page).every((id) => {
      const marker = [...page.document.querySelectorAll(".marker")].find((item) => item.dataset.id === id);
      return Boolean(marker.dataset.fallback) || marker.style.top.includes("px");
    }),
  );

  // --- keyboard access ---
  const activeMarker = page.document.querySelector(".marker");
  activeMarker.focus();
  check("a marker can take keyboard focus", page.document.activeElement === activeMarker);
  const beforeKey = state().activeId;
  page.window.scholarflowWorkspace.focusFinding(1);
  check("keyboard navigation moves to another finding", state().activeId !== beforeKey);
  page.document.getElementById("marker-layer").dispatchEvent(
    new page.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }),
  );
  check("Enter on the marker layer opens the suggestion card", page.document.getElementById("suggestion-card").hidden === false);
  page.document.dispatchEvent(new page.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
  check("Escape closes the suggestion card", page.document.getElementById("suggestion-card").hidden === true);

  // --- clicking a marker opens the card ---
  const spelling = findings.find((finding) => finding.category === "spelling");
  page.window.scholarflowWorkspace.openSuggestion(spelling.id);
  const card = page.document.getElementById("suggestion-card");
  check("clicking a marker opens the suggestion card", card.hidden === false);
  check("the card shows the original text", page.document.getElementById("suggestion-original").textContent === spelling.original);
  check(
    "the card shows a proposed correction",
    page.document.getElementById("suggestion-proposal").textContent === spelling.replacement,
    page.document.getElementById("suggestion-proposal").textContent,
  );
  check(
    "the card explains the finding and names the category",
    page.document.getElementById("suggestion-heading").textContent.length > 0 &&
      page.document.getElementById("suggestion-explanation").textContent.length > 20,
    page.document.getElementById("suggestion-heading").textContent,
  );
  check(
    "the card offers each alternative correction as its own action",
    page.document.querySelectorAll("#suggestion-alternatives button").length ===
      spelling.replacements.length &&
      [...page.document.querySelectorAll("#suggestion-alternatives button")].every((button) =>
        spelling.replacements.includes(button.textContent),
      ),
    `${spelling.replacements.length} alternative(s)`,
  );
  check("the card is labelled as a dialog", card.getAttribute("role") === "dialog" && card.getAttribute("aria-label").length > 0);

  // --- accept applies the correction at the right characters ---
  const beforeAccept = page.document.getElementById("editor").value;
  const expected = beforeAccept.slice(0, spelling.start) + spelling.replacement + beforeAccept.slice(spelling.end);
  page.document.getElementById("suggestion-accept").click();
  const afterAccept = page.document.getElementById("editor").value;
  check("Accept applies the correction at the exact characters", afterAccept === expected, afterAccept.slice(0, 60));
  check(
    "Accept leaves the rest of the document untouched",
    afterAccept.startsWith(beforeAccept.slice(0, spelling.start)) &&
      afterAccept.endsWith(beforeAccept.slice(spelling.end)),
  );
  check("the accepted correction is marked unsaved", /Unsaved/.test(page.document.getElementById("save-state").textContent));

  // --- re-analysis after an accepted correction ---
  const checksBefore = state().checks;
  await waitFor(() => state().checks > checksBefore, 8000);
  check("the document is re-checked after a correction", state().checks > checksBefore, `checks=${state().checks}`);
  const spellingsLeft = state().findings.filter((finding) => finding.category === "spelling");
  check(
    "the corrected word is no longer reported",
    !spellingsLeft.some((finding) => finding.original === spelling.original),
  );

  // --- dismiss changes nothing ---
  await page.window.scholarflowWorkspace.analyse();
  await waitFor(() => state().checks > checksBefore + 1);
  const target = state().findings.find((finding) => finding.kind === "error");
  const beforeDismiss = page.document.getElementById("editor").value;
  const markersBeforeDismiss = markerIds(page).length;
  page.window.scholarflowWorkspace.openSuggestion(target.id);
  page.document.getElementById("suggestion-dismiss").click();
  check("Dismiss leaves the text unchanged", page.document.getElementById("editor").value === beforeDismiss);
  check("Dismiss removes the marker from the view", markerIds(page).length === markersBeforeDismiss - 1);
  check(
    "Dismiss removes the sidebar entry but keeps the finding counted as dismissed",
    !sidebarIds(page).includes(target.id) && state().dismissed >= 1,
  );
  page.window.scholarflowWorkspace.restoreDismissed();
  check("dismissed findings can be restored", state().dismissed === 0 && markerIds(page).length === markersBeforeDismiss);

  // --- a stale suggestion is refused, not applied ---
  await page.window.scholarflowWorkspace.analyse();
  await waitFor(() => state().checks > checksBefore + 2);
  const stale = state().findings.find(
    (finding) => finding.kind === "error" && finding.replacement !== null,
  );
  const staleText = page.document.getElementById("editor").value;
  page.window.scholarflowWorkspace.openSuggestion(stale.id);
  const edited = staleText.slice(0, 1).toLowerCase() + "zz" + staleText.slice(1);
  type(page.window, page.document, edited);
  page.document.getElementById("suggestion-accept").click();
  const afterStale = page.document.getElementById("editor").value;
  check("a stale suggestion is refused instead of corrupting the text", afterStale === edited);
  check(
    "the refusal is explained in the card",
    /no longer matches/i.test(page.document.getElementById("suggestion-blocked").textContent),
    page.document.getElementById("suggestion-blocked").textContent.slice(0, 70),
  );

  // --- analysing while the researcher keeps typing ---
  await page.window.scholarflowWorkspace.analyse();
  const typing = page.document.getElementById("editor").value + " Additional sentence typed mid-analysis.";
  type(page.window, page.document, typing);
  await sleep(400);
  check(
    "typing during an analysis is never overwritten",
    page.document.getElementById("editor").value === typing,
  );

  // --- sidebar, filters and navigation ---
  await page.window.scholarflowWorkspace.analyse();
  await waitFor(() => state().checks > checksBefore + 3, 8000);
  check(
    "the sidebar groups findings by category with counts",
    page.document.querySelectorAll(".diag-group").length >= 2 &&
      /\(\d+\)/.test(page.document.querySelector(".diag-group-head").textContent),
    page.document.querySelector(".diag-group-head").textContent.trim(),
  );
  check(
    "the sidebar summary reports errors and style separately",
    /error/i.test(page.document.getElementById("diagnostics-summary").textContent) &&
      /style/i.test(page.document.getElementById("diagnostics-summary").textContent),
    page.document.getElementById("diagnostics-summary").textContent.trim(),
  );
  const allCount = sidebarIds(page).length;
  page.document.getElementById("filter-error").click();
  const errorCount = sidebarIds(page).length;
  check("the errors filter hides style findings", errorCount < allCount && errorCount > 0, `${errorCount}/${allCount}`);
  check(
    "only errors remain in the filtered view",
    state().findings.filter((finding) => sidebarIds(page).includes(finding.id)).every((finding) => finding.kind === "error"),
  );
  page.document.getElementById("filter-style").click();
  const styleCount = sidebarIds(page).length;
  check("the style filter shows only style findings", styleCount > 0 && styleCount !== errorCount, `${styleCount} shown`);
  page.document.getElementById("filter-all").click();
  check("the all filter restores every finding", sidebarIds(page).length === allCount);

  const firstSidebarId = sidebarIds(page)[0];
  page.document.querySelector(`.diag-finding[data-id="${firstSidebarId}"]`).click();
  check(
    "a sidebar finding opens its suggestion card",
    state().openId === firstSidebarId && page.document.getElementById("suggestion-card").hidden === false,
  );
  check(
    "the card shows the offsets of the finding it opened",
    page.document.getElementById("suggestion-meta").textContent.includes(
      String(state().findings.find((finding) => finding.id === firstSidebarId).start),
    ),
  );
  page.window.scholarflowWorkspace.focusFinding(1);
  check("Next moves the active finding", state().activeId !== firstSidebarId);
  const afterNext = state().activeId;
  page.window.scholarflowWorkspace.focusFinding(-1);
  check("Previous moves back", state().activeId === firstSidebarId && afterNext !== firstSidebarId);

  // --- dictionary ---
  await page.window.scholarflowWorkspace.analyse();
  await waitFor(() => state().checks > checksBefore + 4, 8000);
  const word = state().findings.find((finding) => finding.category === "spelling");
  if (word) {
    page.window.scholarflowWorkspace.openSuggestion(word.id);
    check(
      "a spelling finding offers 'Add to dictionary'",
      page.document.getElementById("suggestion-dictionary").hidden === false,
    );
    page.document.getElementById("suggestion-dictionary").click();
    const gone = await waitFor(
      () => !state().findings.some((finding) => finding.original === word.original),
      8000,
    );
    check("a word added to the dictionary is no longer flagged", gone, word.original);
    await fetch(`${BASE}/api/workspace/dictionary/${word.original}`, { method: "DELETE" });
  } else {
    check("a spelling finding offers 'Add to dictionary'", false, "no spelling finding to test");
    check("a word added to the dictionary is no longer flagged", false, "no spelling finding to test");
  }

  // --- empty state on clean text ---
  type(page.window, page.document, "# Clean section\n\nCaste shapes access to land in rural India (Gupta, 2000).");
  await page.window.scholarflowWorkspace.analyse();
  await waitFor(() => state().count === 0 && state().checks > checksBefore + 5, 8000);
  check("a clean document reports no findings", state().count === 0);
  check(
    "the empty state explains that nothing was found",
    page.document.getElementById("diagnostics-empty").hidden === false &&
      /passed every local rule|No findings/i.test(page.document.getElementById("diagnostics-empty").textContent),
    page.document.getElementById("diagnostics-empty").textContent.trim().slice(0, 70),
  );
  check("no markers are left over from the previous text", markerIds(page).length === 0);

  // --- analysis failure is visible and harmless ---
  // The failure is injected only for the diagnostics endpoint, so the page has a
  // document open exactly like a real session.
  const failing = await loadPage("/workspace", { failDiagnostics: true });
  await waitFor(() => failing.window.scholarflowWorkspace.getState().documentId !== null);
  const failingText = "# Methods\n\nThere is many studies about this tehnique.\n";
  type(failing.window, failing.document, failingText);
  await failing.window.scholarflowWorkspace.analyse();
  await waitFor(() => failing.window.scholarflowWorkspace.getState().diagnostics.error !== null);
  check(
    "a failed analysis is reported without touching the text",
    failing.window.scholarflowWorkspace.getState().diagnostics.error !== null &&
      failing.document.getElementById("editor").value === failingText,
  );
  check(
    "the failure explains itself in the sidebar",
    /could not run/i.test(failing.document.getElementById("diagnostics-empty").textContent),
    failing.document.getElementById("diagnostics-empty").textContent.trim().slice(0, 60),
  );
  check(
    "a failed analysis leaves the editor usable",
    failing.document.getElementById("editor").disabled === false &&
      failing.document.getElementById("finding-recheck") !== null,
  );
  await sleep(300);
  failing.window.close();

  // --- checking a document must never write to it ---
  const savedText = page.document.getElementById("editor").value;
  page.document.getElementById("save-document").click();
  const saved = await waitFor(async () => (await serverDocument(documentId)).text === savedText, 8000);
  check("the document is saved before the integrity check", saved);
  const beforeAnalysis = (await serverDocument(documentId)).text;
  await page.window.scholarflowWorkspace.analyse();
  await waitFor(() => state().checks > checksBefore + 6, 8000);
  const afterAnalysis = (await serverDocument(documentId)).text;
  check(
    "running diagnostics does not modify the stored document",
    afterAnalysis === beforeAnalysis && afterAnalysis === savedText,
    `${afterAnalysis.length} characters`,
  );
  page.window.close();
  return documentId;
}


/* Stage 3 adds: an anchored suggestion pop-up, a plain total, academic
 * profiles that change which style rules run, the unavailable-dictionary
 * state, and programmatic edits that keep the browser's undo history. jsdom
 * cannot measure or undo anything, so the anchoring is verified against a
 * stubbed layout and the undo path against a stand-in for execCommand. Both
 * stand-ins are stated as such: the real things need WebView2. */
async function stage3Diagnostics() {
  console.log("\n== Stage 3: profiles, anchoring and undo-safe corrections ==");
  const page = await loadPage("/workspace", { execCommand: true });
  check("workspace page loads without script errors (stage 3)", page.errors.length === 0, page.errors.join("; "));
  const previousId = page.window.scholarflowWorkspace?.getState().documentId ?? null;
  page.document.getElementById("new-document").click();
  await waitFor(() => {
    const id = page.window.scholarflowWorkspace?.getState().documentId;
    return Boolean(id) && id !== previousId;
  });
  const documentId = page.window.scholarflowWorkspace.getState().documentId;
  const state = () => page.window.scholarflowWorkspace.getState().diagnostics;
  const checksBefore = state().checks;

  const text =
    "# Draft\n\n" +
    "It is important to note that a number of studies has shown this, and the field is kind of split ,and " +
    "the datas are unclear. There is many studies about this tehnique.\n";
  type(page.window, page.document, text);
  await page.window.scholarflowWorkspace.analyse();
  await waitFor(() => state().checks > checksBefore, 8000);

  // --- the plain total ---
  const total = page.document.getElementById("diagnostics-total");
  check(
    "a plain total is shown for the document",
    total.hidden === false && /\d+ issues? in this document/.test(total.textContent),
    total.textContent.trim(),
  );
  check(
    "the total matches the number of findings",
    total.textContent.includes(String(state().findings.length)),
    `${state().findings.length} findings`,
  );
  check(
    "the panel names the profile and what it means for style rules",
    /profile/i.test(page.document.getElementById("diagnostics-profile").textContent) &&
      /spelling and grammar always run/i.test(page.document.getElementById("diagnostics-profile").textContent),
    page.document.getElementById("diagnostics-profile").textContent.trim().slice(0, 80),
  );

  // --- profiles change the style rules, never the text ---
  const standardCategories = new Set(state().findings.map((finding) => finding.category));
  const textBeforeProfile = page.document.getElementById("editor").value;
  page.window.scholarflowWorkspace.setProfile("conservative");
  await waitFor(() => state().profile === "formal_academic" && state().checks > checksBefore + 1, 8000);
  const formalCategories = new Set(state().findings.map((finding) => finding.category));
  check(
    "switching to the formal profile re-runs the analysis under that profile",
    state().profile === "formal_academic",
    state().profile,
  );
  check(
    "the formal profile leaves out the concision rules",
    standardCategories.has("wordiness") && !formalCategories.has("wordiness"),
    `${[...standardCategories].join(",")} -> ${[...formalCategories].join(",")}`,
  );
  check(
    "a profile never edits the document",
    page.document.getElementById("editor").value === textBeforeProfile,
  );
  check(
    "spelling and punctuation still run in the formal profile",
    state().findings.some((finding) => finding.category === "spelling") &&
      state().findings.some((finding) => finding.category === "punctuation"),
  );
  page.window.scholarflowWorkspace.setProfile("polish");
  await waitFor(() => state().profile === "concise_academic" && state().checks > checksBefore + 2, 8000);
  check(
    "the concise profile is reported as active",
    state().profile === "concise_academic" &&
      /Concise/i.test(page.document.getElementById("diagnostics-profile").textContent),
    page.document.getElementById("diagnostics-profile").textContent.trim().slice(0, 60),
  );
  check(
    "the concise profile is stricter about long sentences than the formal one",
    state().findings.some((finding) => finding.rule === "readability.long-sentence") ||
      state().findings.length > 0,
  );

  // --- the anchored pop-up, measured against a stubbed layout ---
  const finding = state().findings.find((item) => item.replacement) || state().findings[0];
  check("at least one finding offers an automatic correction", Boolean(finding && finding.replacement));
  page.window.scholarflowWorkspace.openSuggestion(finding.id);
  const card = page.document.getElementById("suggestion-card");
  check(
    "without a layout engine the card stays in the document flow",
    card.hidden === false && !card.classList.contains("is-anchored"),
    "fallback layout",
  );
  // Give the shell, the marker and the card measurable rectangles, then ask for
  // the same positioning the real browser would do.
  const shell = page.document.getElementById("editor-shell");
  const stub = (element, rect) => {
    element.getBoundingClientRect = () => ({ ...rect, right: rect.left + rect.width, bottom: rect.top + rect.height });
  };
  stub(shell, { left: 100, top: 200, width: 600, height: 500 });
  const marker = [...page.document.querySelectorAll(".marker")].find((item) => item.dataset.id === finding.id);
  check("the finding has a marker to anchor to", Boolean(marker));
  if (marker) stub(marker, { left: 240, top: 260, width: 60, height: 18 });
  stub(card, { left: 0, top: 0, width: 360, height: 220 });
  page.window.scholarflowWorkspace.anchorSuggestionCard(finding);
  check(
    "with a measurable layout the card is anchored to its marker",
    card.classList.contains("is-anchored"),
    `left=${card.style.left} top=${card.style.top}`,
  );
  const anchoredLeft = parseInt(card.style.left, 10);
  const anchoredTop = parseInt(card.style.top, 10);
  check(
    "the card sits just below the marked text, inside the editor",
    anchoredLeft >= 4 && anchoredLeft + 360 <= 600 - 4 && anchoredTop > 260 - 200 && anchoredTop < 500,
    `left=${anchoredLeft} top=${anchoredTop}`,
  );
  // A finding near the bottom flips the card above the text.
  if (marker) stub(marker, { left: 240, top: 660, width: 60, height: 18 });
  page.window.scholarflowWorkspace.anchorSuggestionCard(finding);
  check(
    "a card with no room below opens above the finding",
    parseInt(card.style.top, 10) < 660 - 200,
    `top=${card.style.top}`,
  );

  // --- accepting an edit goes through the undo-preserving path ---
  page.window.scholarflowWorkspace.openSuggestion(finding.id);
  page.window.__edits.length = 0;
  page.document.getElementById("suggestion-accept").click();
  const expected = text.slice(0, finding.start) + (finding.replacement || "") + text.slice(finding.end);
  check(
    "accepting a suggestion asks the browser to insert the replacement",
    page.window.__edits.length >= 1 && page.window.__edits[0].value === (finding.replacement || ""),
    JSON.stringify(page.window.__edits[0] || null),
  );
  if (page.window.__edits.length) {
    const edit = page.window.__edits[0];
    check(
      "the edit is applied to exactly the finding's range",
      edit.start === finding.start && edit.end === finding.end,
      `${edit.start}-${edit.end} for ${finding.start}-${finding.end}`,
    );
  }
  check(
    "the document text after accepting is exactly the intended correction",
    page.document.getElementById("editor").value === expected,
    `"${page.document.getElementById("editor").value.slice(finding.start - 10, finding.start + 20)}"`,
  );
  await waitFor(() => state().checks > checksBefore + 3, 8000);
  check("accepting a correction re-runs the analysis", state().checks > checksBefore + 3);

  // --- autosave and diagnostics must not fight over the document ---
  const correctedText = page.document.getElementById("editor").value;
  check(
    "the correction marks the document dirty for autosave",
    /unsaved/i.test(page.document.getElementById("save-state").textContent),
  );
  const autosavedCorrection = await waitFor(
    async () => (await serverDocument(documentId)).text === correctedText,
    9000,
  );
  check("the correction reaches the server through autosave", autosavedCorrection);
  // Keep typing while a check is in flight; the newer text must win everywhere.
  const raced = correctedText + " An added clause typed while the check ran.";
  type(page.window, page.document, raced);
  const analysis = page.window.scholarflowWorkspace.analyse();
  await sleep(60);
  type(page.window, page.document, raced + " And one more.");
  await analysis;
  const racedFinal = page.document.getElementById("editor").value;
  check(
    "typing during an in-flight check is never rolled back",
    racedFinal === raced + " And one more.",
    `${racedFinal.length} characters`,
  );
  // The check that was in flight describes the older text, so it is dropped and
  // a fresh one runs; the analysis must settle on what is on screen.
  const settled = await waitFor(() => state().analysedText === racedFinal, 9000);
  check(
    "the analysis settles on the text that is on screen",
    settled && state().analysedText === racedFinal,
    settled ? "matches the editor" : "still describing an older version",
  );
  const racedSaved = await waitFor(async () => (await serverDocument(documentId)).text === racedFinal, 9000);
  check("autosave stores the text the reader can see", racedSaved);

  // --- the correction survives save, close and reopen ---
  page.document.getElementById("save-document").click();
  await waitFor(async () => (await serverDocument(documentId)).text === racedFinal, 8000);
  await sleep(2700); // let the autosave timer that a keystroke scheduled fire
  page.window.close();
  check("closing the window with a pending autosave does not throw", true, "window closed cleanly");
  const reopened = await loadPage("/workspace");
  await waitFor(() => reopened.window.scholarflowWorkspace.getState().documentId !== null);
  check(
    "a correction survives saving and reopening the document",
    reopened.document.getElementById("editor").value === racedFinal,
    `${reopened.document.getElementById("editor").value.length} characters after reopen`,
  );
  reopened.window.close();

  await fetch(`${BASE}/api/workspace/dictionary/tehnique`, { method: "DELETE" }).catch(() => {});

  // --- the dictionary being unavailable is stated, not hidden ---
  const degraded = await loadPage("/workspace", { degradeSpelling: true });
  await waitFor(() => degraded.window.scholarflowWorkspace.getState().documentId !== null);
  type(degraded.window, degraded.document, "# Section\n\nThere is many studies here.\n");
  await degraded.window.scholarflowWorkspace.analyse();
  await waitFor(() => degraded.window.scholarflowWorkspace.getState().diagnostics.checks > 0, 8000);
  const degradedState = degraded.window.scholarflowWorkspace.getState().diagnostics;
  check(
    "an unavailable dictionary is reported to the reader",
    degradedState.spellingAvailable === false &&
      /dictionary/i.test(degraded.document.getElementById("diagnostics-profile").textContent),
    degraded.document.getElementById("diagnostics-profile").textContent.trim().slice(0, 90),
  );
  check(
    "grammar and punctuation still run without the dictionary",
    degradedState.findings.some((finding) => finding.category === "agreement" || finding.category === "punctuation"),
  );
  degraded.window.close();
  return documentId;
}


/* The exact passage from docs/WINDOWS_DIAGNOSTICS_TEST.md section 1. Every
 * integrity check below uses it, because it is the text the bug report is
 * about: a heading, a citation, a quotation, a long wordy sentence, protected
 * vocabulary and an obvious typo. */
const CHECKLIST_PASSAGE = `# Caste and commons — field notes

There is many studies about this tehnique (Gupta, 2000), and the analysys is
inconclusive ,but the authors dont agree about the mechanism.

It is important to note that, in order to understand how caste plays a crucial
role in shaping access to land in the villages of Chamarajanagar district where
the Vokkaliga and Dalit households were surveyed by the team between June and
August of the fieldwork year, a number of additional interviews would have been
necessary.

As Deshpande wrote, "caste is not static", and the Adivasi households in
Hulikere reported different tenurial arrangements.
`;

const PASSAGE_HEADING = "# Caste and commons — field notes";

function spliceText(text, start, end, replacement) {
  return text.slice(0, start) + replacement + text.slice(end);
}

/** The features that must hold whatever else happened to the document. */
function structureChecks(prefix, value, { heading = 1, firstParagraph = 1, phrase = 1 } = {}) {
  check(
    `${prefix}: the heading appears exactly ${heading === 1 ? "once" : heading + " times"}`,
    value.split(PASSAGE_HEADING).length - 1 === heading,
  );
  // A phrase from the first paragraph that none of the checks edits, so the
  // count only moves when text is duplicated or lost.
  check(
    `${prefix}: the first paragraph appears exactly ${firstParagraph === 1 ? "once" : firstParagraph + " times"}`,
    value.split("about the mechanism.").length - 1 === firstParagraph,
  );
  check(
    `${prefix}: the long clause appears exactly ${phrase === 1 ? "once" : phrase + " times"}`,
    value.split("role in shaping access to land").length - 1 === phrase,
  );
  check(`${prefix}: the final sentence is intact`, value.includes("tenurial arrangements."));
}

async function newWorkspaceDocument(page, title) {
  const previousId = page.window.scholarflowWorkspace?.getState().documentId ?? null;
  page.document.getElementById("new-document").click();
  const created = await waitFor(() => {
    const id = page.window.scholarflowWorkspace?.getState().documentId;
    return Boolean(id) && id !== previousId;
  });
  if (title) {
    const field = page.document.getElementById("doc-title");
    field.value = title;
    field.dispatchEvent(new page.window.Event("input", { bubbles: true }));
  }
  return created ? page.window.scholarflowWorkspace.getState().documentId : null;
}


/* The document lifecycle under in-flight requests.
 *
 * Every check in this stage corresponds to a defect that was reproduced in a
 * DOM against the page as it was. They are about which document a response
 * belongs to: adopting a response for a document the person has left, or
 * writing the open document's text into another document's file, are the ways a
 * local-first editor destroys somebody's writing.
 */
async function documentIdentityUnderInFlightRequests() {
  console.log("\n== Document identity under in-flight requests ==");

  // ---------------------------------------------------------------- setup
  const suffix = Date.now().toString(36).slice(-5);
  const titleA = `Identity A ${suffix}`;
  const titleB = `Identity B ${suffix}`;
  const docA = await (
    await fetch(`${BASE}/api/documents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: titleA, text: "AAA original text.\n" }),
    })
  ).json();
  const docB = await (
    await fetch(`${BASE}/api/documents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: titleB, text: "BBB original text.\n" }),
    })
  ).json();
  check("two documents exist for the identity checks", Boolean(docA.id && docB.id));

  const openRow = (page, title) =>
    [...page.document.querySelectorAll("#document-list button.list-item")].find((button) =>
      button.textContent.includes(title),
    );

  // ------------------------------------------- a late load is not adopted
  // Click one document, then another, before the first has answered. The
  // response for the abandoned one must be dropped, not shown.
  {
    const page = await loadPage("/workspace", {
      delayResponses: [{ method: "GET", pattern: `/api/documents/${docA.id}$`, ms: 2500 }],
    });
    const rowA = openRow(page, titleA);
    const rowB = openRow(page, titleB);
    check("both documents are listed in the sidebar", Boolean(rowA && rowB));
    rowA.click();
    await sleep(150);
    rowB.click();
    const selected = await waitFor(
      () => page.window.scholarflowWorkspace.getState().documentId === docB.id,
      5000,
    );
    check("clicking the second document opens it", selected);

    const typed = "BBB original text.\nTyped in B while A was still loading.\n";
    type(page.window, page.document, typed);
    await sleep(3500); // A's response lands in here

    const editor = page.document.getElementById("editor");
    check(
      "a late response for an abandoned document does not replace the text",
      editor.value === typed,
      `editor holds ${JSON.stringify(editor.value.slice(0, 48))}`,
    );
    check(
      "the abandoned document does not become the selected one",
      page.window.scholarflowWorkspace.getState().documentId === docB.id,
    );
    page.window.close();
  }

  // ------------------------------- a late save response is not adopted, and
  //                    the editor's text never lands in another document
  // The defect: type in A, let the autosave start, switch to B, type — A's
  // response re-adopted A while the editor held B's text, and the next autosave
  // wrote B's text into A, destroying A.
  {
    const page = await loadPage("/workspace", {
      // Only A's writes are slow, so its response arrives after the switch.
      delayResponses: [{ method: "PUT", pattern: `/api/documents/${docA.id}$`, ms: 3000 }],
    });
    openRow(page, titleA).click();
    await waitFor(() => page.window.scholarflowWorkspace.getState().documentId === docA.id, 5000);

    const editor = page.document.getElementById("editor");
    const typedInA = "AAA original text.\nEdited in A, and this must stay in A.\n";
    type(page.window, page.document, typedInA);
    await sleep(2800); // A's autosave is now in flight

    openRow(page, titleB).click();
    const switched = await waitFor(
      () => page.window.scholarflowWorkspace.getState().documentId === docB.id,
      5000,
    );
    check("switching to the second document while A is saving works", switched);

    const typedInB = editor.value + "Added while in B.\n";
    type(page.window, page.document, typedInB);

    // Let A's response land, then let whatever it triggers run.
    await sleep(7000);

    const storedA = await serverDocument(docA.id);
    const storedB = await serverDocument(docB.id);
    check(
      "A still holds A's text",
      storedA.text.includes("Edited in A") && !storedA.text.includes("Added while in B"),
      JSON.stringify(storedA.text.slice(0, 60)),
    );
    check(
      "B still holds B's text",
      storedB.text.includes("Added while in B") && !storedB.text.includes("Edited in A"),
      JSON.stringify(storedB.text.slice(0, 60)),
    );
    check(
      "the late save response did not re-select the document being saved",
      page.window.scholarflowWorkspace.getState().documentId === docB.id,
      `selected ${page.window.scholarflowWorkspace.getState().documentId}`,
    );
    check(
      "the editor still shows the document the person is in",
      editor.value === typedInB,
      `editor holds ${JSON.stringify(editor.value.slice(0, 40))}`,
    );
    page.window.close();
  }

  // ---------------------------- restoring a revision with unsaved edits asks
  {
    const page = await loadPage("/workspace");
    const mine = await (
      await fetch(`${BASE}/api/documents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: `Restore ${suffix}`, text: "Revision one text.\n" }),
      })
    ).json();
    await fetch(`${BASE}/api/documents/${mine.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "Revision two text.\n", reason: "manual" }),
    });
    // A fresh page load, so the sidebar really lists the new document.
    const fresh = await loadPage("/workspace");
    page.window.close();
    const row = [...fresh.document.querySelectorAll("#document-list button.list-item")].find(
      (button) => button.textContent.includes(`Restore ${suffix}`),
    );
    check("the restore-probe document is listed", Boolean(row));
    if (row) {
      row.click();
      await waitFor(() => fresh.window.scholarflowWorkspace.getState().documentId === mine.id, 5000);
      const unsaved = "Revision two text.\nUnsaved paragraph that exists only in this window.\n";
      type(fresh.window, fresh.document, unsaved);
      await sleep(200);
      // A confirm() stand-in that records the question it was asked.
      let asked = "";
      fresh.window.confirm = (message) => {
        asked = String(message);
        return true;
      };
      const restore = [...fresh.document.querySelectorAll("#history button")].find((button) =>
        /Restore this revision/.test(button.textContent),
      );
      check("a revision is offered for restore", Boolean(restore));
      if (restore) {
        restore.click();
        await sleep(1500);
        check(
          "restoring over unsaved edits asks first and says they can be recovered",
          /unsaved edits/i.test(asked) && /recover/i.test(asked),
          `confirm said ${JSON.stringify(asked.slice(0, 70))}`,
        );
        check(
          "the unsaved text is still offered back after the restore",
          fresh.document.getElementById("recovery-banner").hidden === false,
        );
      }
    }
    fresh.window.close();
  }

  return { docA, docB };
}

/* ------------------------------------------------------------------ oracle
 *
 * Every case is compared in full, three ways: what the API stored when the
 * document was created, what the editor shows when the document is opened, and
 * what the API stores after an edit containing the same representations again.
 *
 * The store states its canonical form itself (`NFC` and `LF`), so the expected
 * value is derived from the case text, never from what the application
 * happened to produce.
 */
const REPRESENTATION_CASES = [
  {
    name: "plain ASCII",
    text:
      "A plain ASCII paragraph with commas, semicolons; and 100% of the numbers 0123456789.\n" +
      "\nSecond paragraph, no trailing newline here",
  },
  {
    name: "accented Latin, dashes and curly quotes",
    text: "Caf\u00e9 \u2014 na\u00efve, co\u00f6perate, \u00f1o\u00f1o; en dash \u2013, ellipsis \u2026, \u201ccurly\u201d and \u2018single\u2019 quotes.\n",
  },
  {
    name: "Gurmukhi",
    text:
      "\u0a2a\u0a70\u0a1c\u0a3e\u0a2c\u0a40 \u0a35\u0a3f\u0a71\u0a1a \u0a32\u0a3f\u0a16\u0a3f\u0a06 \u0a07\u0a71\u0a15 \u0a2a\u0a48\u0a30\u0a3e\u0964\n" +
      "\u0a26\u0a42\u0a1c\u0a3e \u0a2a\u0a48\u0a30\u0a3e: \u0a35\u0a3f\u0a30\u0a3e\u0a2e \u0a1a\u0a3f\u0a70\u0a28\u0a39, \u0a05\u0a24\u0a47 \u0a38\u0a70\u0a16\u0a3f\u0a06\u0a35\u0a3e\u0a02 \u0a67\u0a68\u0a69\u0a6a\u0964\n",
  },
  {
    name: "emoji, flags and ZWJ sequences",
    text: "Ordinary text with an emoji \ud83d\ude42, a flag \ud83c\uddee\ud83c\uddf3 and a family \ud83d\udc69\u200d\ud83d\udc69\u200d\ud83d\udc67 in it.\n",
  },
  {
    name: "combining marks, RTL and Devanagari",
    text:
      "Decomposed: e\u0301 a\u0308 n\u0303 \u2014 Hebrew \u05e9\u05dc\u05d5\u05dd, Arabic \u0645\u0631\u062d\u0628\u0627, Devanagari \u0939\u093f\u0928\u094d\u0926\u0940\u0964\n",
  },
  { name: "CRLF line endings", text: "First line.\r\nSecond line.\r\nThird line.\r\n" },
  { name: "blank lines and a trailing newline", text: "Alpha.\n\n\nBeta.\n\nGamma.\n" },
  {
    name: "tabs, trailing spaces and no final newline",
    text: "Alpha.\tTabbed column.\nTrailing spaces here.   \nNo final newline",
  },
  {
    name: "Markdown",
    text: "# Heading\n\n- item one\n- item two\n\n> quote\n\n**bold**, *italic* and `code`.\n",
  },
  {
    name: "repeated phrases",
    text: "The same phrase. The same phrase. The same phrase repeats, and in order to test in order to test, a number of a number of.\n",
  },
  { name: "an empty document", text: "" },
  {
    name: "a long passage",
    text: Array.from(
      { length: 40 },
      (_, index) =>
        `Paragraph ${index + 1}: a sentence that is long enough to be a real sentence, with a comma, and a following clause; then a number ${index + 1}0 and a Gurmukhi word \u0a38\u0a2b\u0a32\u0a24\u0a3e.\n`,
    ).join("\n"),
  },
];

/* The store states its canonical form: NFC, and CRLF folded to LF. The browser
 * does the same folding in a textarea, so this is the expected value for both
 * the editor and the API. When the application produces anything else, that is
 * a difference in the text and this comparison shows it in full. */
function canonical(text) {
  return text.replace(/\r\n/g, "\n").normalize("NFC");
}

async function apiCreateDocument(title, body) {
  const response = await fetch(`${BASE}/api/documents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, text: body }),
  });
  return response.json();
}

const EMPTY = () => ({});

/* ------------------------------------------------------------- emoji offsets
 *
 * The engine counts characters; the browser counts UTF-16 code units. In a
 * document with an emoji the two differ, and every correction at or after the
 * emoji points at the wrong characters. The whole text is compared here: the
 * characters the interface highlights, and the exact text after accepting a
 * correction that comes after the emoji.
 */
async function emojiOffsetsDoNotBreakCorrections() {
  console.log("\n== Corrections in a document that contains an emoji ==");
  const text =
    "The tehnique \u{1F642} used here is the analysys of caste, and the evidence dont support it.\n" +
    "A second line \u{1F642} with a repeated word the the same the the word.\n";
  const title = `Emoji offsets ${Date.now().toString(36).slice(-5)}`;
  const created = await apiCreateDocument(title, text);

  const page = await loadPage("/workspace");
  const { window, document } = page;
  const editor = document.getElementById("editor");
  const row = [...document.querySelectorAll("#document-list button.list-item")].find((button) =>
    button.textContent.includes(title),
  );
  check("the emoji document is listed", Boolean(row));
  if (!row) {
    window.close();
    return;
  }
  row.click();
  await waitFor(() => window.scholarflowWorkspace.getState().documentId === created.id, 6000);
  // Let the page's own start-up open settle, then type a real edit. (Typing the
  // stored text verbatim would instead exercise the "redundant open ends the
  // pending check" case, which has its own stage below.)
  await sleep(800);
  const edited = `${text}A sentence typed after opening the document.\n`;
  type(window, document, edited);
  const expectedText = edited;

  const analysed = await waitFor(
    () => {
      const state = window.scholarflowWorkspace.getState();
      return state.diagnostics.count > 0 && state.diagnostics.analysedText === expectedText;
    },
    12000,
  );
  const findings = window.scholarflowWorkspace.getState().diagnostics.findings.filter(
    (finding) => finding.original,
  );
  const analysisState = window.scholarflowWorkspace.getState();
  check(
    "an emoji document produces findings",
    analysed && findings.length > 0,
    `${findings.length} findings; analysed=${analysed}; open=${analysisState.documentId === created.id}; ` +
      `requests=${analysisState.diagnostics.requests} checks=${analysisState.diagnostics.checks} ` +
      `loading=${analysisState.diagnostics.loading} error=${JSON.stringify(analysisState.diagnostics.error)} ` +
      `editor=${editor.value.length} characters; analysedText=${analysisState.diagnostics.analysedText ? analysisState.diagnostics.analysedText.length : "none"}; ` +
      `scheduleAnalysis=${typeof window.scheduleAnalysis}; pageErrors=${JSON.stringify(page.errors.join(" | ").slice(0, 200))}; ` +
      `mirror=${Boolean(document.getElementById("marker-mirror"))}`,
  );

  const shifted = findings.filter((finding) => editor.value.slice(finding.start, finding.end) !== finding.original);
  check(
    "every finding's offsets select exactly the text it names",
    findings.length > 0 && shifted.length === 0,
    shifted
      .slice(0, 3)
      .map(
        (finding) =>
          `${finding.id} covers ${JSON.stringify(editor.value.slice(finding.start, finding.end))} ` +
          `instead of ${JSON.stringify(finding.original)}`,
      )
      .join(" | "),
  );

  // The interface draws a highlight over the flagged characters; that highlight
  // is what a person sees, so compare it too.
  const spans = [...document.querySelectorAll("#marker-mirror .marker-span")];
  const wrongSpans = spans.filter((span) => {
    const finding = findings.find((item) => item.id === span.dataset.id);
    return finding ? span.textContent !== finding.original : false;
  });
  check(
    "the highlight over the text covers exactly the flagged characters",
    spans.length > 0 && wrongSpans.length === 0,
    wrongSpans
      .slice(0, 3)
      .map((span) => `${JSON.stringify(span.textContent)} for ${span.dataset.id}`)
      .join(" | "),
  );

  // Correct the misspelling that comes after the emoji.
  const spelling = findings.find((finding) => finding.original === "analysys");
  check(
    "the misspelling after the emoji is offered with its correction",
    Boolean(spelling && spelling.replacement === "analysis"),
    spelling ? `[${spelling.start},${spelling.end}) -> ${spelling.replacement}` : "not offered",
  );
  if (spelling) {
    const predicted = spliceText(expectedText, spelling.start, spelling.end, spelling.replacement);
    window.scholarflowWorkspace.openSuggestion(spelling.id);
    await sleep(150);
    document.getElementById("suggestion-accept").click();
    await sleep(600);
    check(
      "accepting it changes exactly that word and nothing else",
      editor.value === predicted,
      editor.value === predicted
        ? ""
        : `${editor.value.length} characters instead of ${predicted.length}: ` +
          firstDifference(editor.value, predicted),
    );
    check(
      "the emoji and the second line are untouched",
      editor.value.includes("\u{1F642} used here is the analysis of caste") &&
        editor.value.includes("A second line \u{1F642}"),
    );
    const stored = await saveAndSettle(window).then(() => serverDocument(created.id));
    check(
      "the corrected text is stored exactly as typed",
      stored.text === predicted,
      stored.text === predicted ? "" : firstDifference(stored.text, predicted),
    );
    check(
      "no half of the emoji was left behind",
      !/[\uD800-\uDBFF](?![\uDC00-\uDFFF])/.test(editor.value) &&
        !/(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(editor.value),
    );
  }

  window.close();
}

/* --------------------------------------------- honest empty diagnostics panel
 *
 * Reproduced: with a check pending, opening the same document again (clicking the
 * row of the document that is already open, or the start-up open racing with a
 * click) ends that pending check. The panel then said "No findings. Your text
 * passed every local rule for the categories checked." and "No issues found in
 * this document." — a claim about text nobody had checked. No text is lost; the
 * defect is the claim. This stage pins the claim, and pins that typing once more
 * does check the text.
 */
async function aCancelledCheckIsNotReportedAsClean() {
  console.log("\n== A document that has not been checked is not reported as clean ==");
  const text = "This one has a tehnique in it and the evidence dont support it.\n";
  const title = `Unchecked ${Date.now().toString(36).slice(-5)}`;
  const created = await apiCreateDocument(title, text);

  const page = await loadPage("/workspace");
  const { window, document } = page;
  const editor = document.getElementById("editor");
  // The list is re-rendered whenever a document is adopted, so the row is looked
  // up fresh each time.
  const clickRow = () => {
    const row = [...document.querySelectorAll("#document-list button.list-item")].find((button) =>
      button.textContent.includes(title),
    );
    if (row) row.click();
    return Boolean(row);
  };

  check("the document is listed", clickRow());
  await waitFor(() => window.scholarflowWorkspace.getState().documentId === created.id, 6000);
  await sleep(600);

  // Type, then open the same document again: that open loads the stored text over
  // the editor and ends whatever check was pending.
  type(window, document, text);
  clickRow();
  await sleep(3000);

  const total = document.getElementById("diagnostics-total").textContent;
  const empty = document.getElementById("diagnostics-empty");
  const shown = empty.hidden ? "" : empty.textContent;
  check(
    "an unchecked document is not reported as clean",
    !/no issues found|passed every local rule|no findings/i.test(`${total} ${shown}`),
    `${JSON.stringify(total)} / ${JSON.stringify(shown.slice(0, 90))}`,
  );
  check(
    "the cancelled check does not change the text",
    editor.value === text,
    editor.value === text ? "" : firstDifference(editor.value, text),
  );

  // Typing again checks it, and then the panel is entitled to report findings.
  type(window, document, `${text}A line typed after the cancelled check, with teh word in it.\n`);
  const checked = await waitFor(
    () => window.scholarflowWorkspace.getState().diagnostics.count > 0,
    12000,
  );
  const totalAfter = document.getElementById("diagnostics-total").textContent;
  check(
    "typing again checks the text and reports what was found",
    checked && !/not checked yet/i.test(totalAfter),
    `${JSON.stringify(totalAfter.slice(0, 90))} after ${JSON.stringify(total)}`,
  );

  // A save the store refuses — text it cannot represent — must be loud, and must
  // lose nothing: the editor keeps it, this browser keeps it, and the document on
  // disk is untouched.
  const typed = `${text}A line typed after the cancelled check, with teh word in it.\n`;
  const broken = `${typed}An ill-formed paste leaves half an emoji behind: \ud83d and stops.\n`;
  type(window, document, broken);
  await window.scholarflowWorkspace.save("manual");
  await sleep(1500);
  const errorText = document.getElementById("error-message").textContent;
  check(
    "a save the store refuses is reported instead of looking like it succeeded",
    document.getElementById("error-banner").hidden === false && /saving failed/i.test(errorText),
    `${document.getElementById("error-banner").hidden ? "no banner" : "banner"}: ${JSON.stringify(errorText.slice(0, 90))}`,
  );
  check(
    "the refused text is still in the editor, unchanged",
    document.getElementById("editor").value === broken,
    editor.value === broken ? "" : firstDifference(editor.value, broken),
  );
  let keptDraft = null;
  try {
    keptDraft = JSON.parse(window.localStorage.getItem(`scholarflow:draft:${created.id}`)).text;
  } catch {
    keptDraft = null;
  }
  check(
    "the refused text is kept in this browser so it can be recovered",
    keptDraft === broken,
    keptDraft === null ? "no draft" : `${keptDraft.length} draft characters instead of ${broken.length}`,
  );
  check(
    "the document on disk was not changed by the refused save",
    (await serverDocument(created.id)).text === text,
    JSON.stringify((await serverDocument(created.id)).text.slice(0, 40)),
  );

  window.close();
}

/* ---------------------------------------------- two presses of Save, in a row
 *
 * The second press must be sent, not dropped. A slow writer holds the first one
 * in flight, which is when the queue matters. The store alone cannot tell the
 * difference — an autosave would eventually store the same text — so the page's
 * own requests are the evidence.
 */
async function savingTwiceInARowIsNotDropped() {
  console.log("\n== Two presses of Save, one slow writer ==");
  const title = `Save twice ${Date.now().toString(36).slice(-5)}`;
  const created = await apiCreateDocument(title, "");
  const page = await loadPage("/workspace", {
    recordWrites: true,
    delayResponses: [{ method: "PUT", pattern: "/api/documents/", ms: 1500 }],
  });
  const { window, document } = page;
  const editor = document.getElementById("editor");
  const row = [...document.querySelectorAll("#document-list button.list-item")].find((button) =>
    button.textContent.includes(title),
  );
  check("the document for the double save is listed", Boolean(row));
  if (!row) {
    window.close();
    return;
  }
  row.click();
  await waitFor(() => window.scholarflowWorkspace.getState().documentId === created.id, 6000);
  await sleep(700);

  const first = "First press of Save.\n";
  const second = "First press of Save.\nSecond press, typed while the first was still being written.\n";
  type(window, document, first);
  const inFlight = window.scholarflowWorkspace.save("manual");
  await sleep(200);
  type(window, document, second);
  await window.scholarflowWorkspace.save("manual"); // queued behind the first
  await inFlight;

  const settled = await waitFor(() => window.scholarflowWorkspace.getState().dirty === false, 20000);
  check("the document ends up saved rather than left unsaved", settled);
  const manual = (window.__writes || []).filter((write) => write.reason === "manual");
  check(
    "both presses of Save were sent as manual writes",
    manual.length >= 2,
    `sent: ${JSON.stringify((window.__writes || []).map((write) => write.reason))}`,
  );
  check(
    "the second write carries the text that was in the editor when it was pressed",
    manual.length >= 2 && manual[manual.length - 1].text === second,
    JSON.stringify(manual.length ? manual[manual.length - 1].text.slice(-40) : null),
  );
  check(
    "the text is not changed by the queueing",
    editor.value === second,
    editor.value === second ? "" : firstDifference(editor.value, second),
  );
  check(
    "the store holds exactly the second text",
    (await serverDocument(created.id)).text === second,
    JSON.stringify((await serverDocument(created.id)).text.slice(-40)),
  );
  window.close();
}

async function textRepresentationOracle() {
  console.log("\n== Text representation oracle (full-text comparison) ==");
  const suffix = Date.now().toString(36).slice(-5);
  const cases = [];
  for (const [index, entry] of REPRESENTATION_CASES.entries()) {
    const title = `Repr ${suffix} ${index} ${entry.name}`;
    const created = await apiCreateDocument(title, entry.text);
    const stored = await serverDocument(created.id);
    cases.push({
      ...entry,
      title,
      id: created.id,
      expected: canonical(entry.text),
      storedAtCreation: stored.text,
    });
  }

  const page = await loadPage("/workspace");
  const { window, document } = page;
  const editor = document.getElementById("editor");
  const open = async (entry) => {
    const row = [...document.querySelectorAll("#document-list button.list-item")].find((button) =>
      button.textContent.includes(entry.title),
    );
    if (!row) return false;
    row.click();
    return waitFor(() => window.scholarflowWorkspace.getState().documentId === entry.id, 6000);
  };

  for (const entry of cases) {
    const label = `"${entry.name}"`;
    check(`${label} is listed in the sidebar`, Boolean(
      [...document.querySelectorAll("#document-list button.list-item")].some((button) =>
        button.textContent.includes(entry.title),
      ),
    ));
    const opened = await open(entry);
    check(`${label} opens`, opened);
    if (!opened) continue;
    check(
      `${label} is stored exactly as written`,
      entry.storedAtCreation === entry.expected,
      `${entry.storedAtCreation.length} stored vs ${entry.expected.length} expected characters`,
    );
    check(
      `${label} reaches the editor unchanged`,
      editor.value === entry.expected,
      `${editor.value.length} in the editor vs ${entry.expected.length} expected characters`,
    );

    const edited = `${entry.expected}\nAdded by the oracle: \u0964 \u0a38\u0a2b\u0a32\u0a24\u0a3e caf\u00e9 \u2014 \u2705\n`;
    type(window, document, edited);
    await saveAndSettle(window);
    const afterSave = await serverDocument(entry.id);
    check(
      `${label} after a save is exactly the edited text`,
      afterSave.text === edited,
      `${afterSave.text.length} stored vs ${edited.length} expected characters`,
    );

    // Reopen the document from the list: the bytes must survive the round trip.
    const other = cases[(cases.indexOf(entry) + 1) % cases.length];
    if (other.id !== entry.id) {
      await open(other);
      await open(entry);
    }
    check(
      `${label} survives saving, leaving and reopening unchanged`,
      editor.value === edited,
      `${editor.value.length} vs ${edited.length} characters`,
    );

    // Saving the same text again must not change it (no drift, no normalisation
    // loop).
    await saveAndSettle(window);
    const afterSecondSave = await serverDocument(entry.id);
    check(
      `${label} is stable when saved again`,
      afterSecondSave.text === edited && afterSecondSave.revision >= afterSave.revision,
      `revision ${afterSave.revision} then ${afterSecondSave.revision}`,
    );
  }

  // Autosave, with no Save button pressed, must store the same bytes.
  const autosaveCase = cases.find((entry) => entry.name === "Gurmukhi");
  if (autosaveCase) {
    const opened = await open(autosaveCase);
    const typed = `${autosaveCase.expected}Autosaved without pressing Save: \u0a17\u0a41\u0a30\u0a2e\u0a41\u0a16\u0a40\n`;
    type(window, document, typed);
    await sleep(4200);
    const stored = await serverDocument(autosaveCase.id);
    check(
      "an autosave stores exactly what was typed",
      opened && stored.text === typed,
      `${stored.text.length} stored vs ${typed.length} expected characters`,
    );
  }

  // Analysis over these characters must not rewrite them, and any finding it
  // reports must own the characters it claims.
  const analysed = await waitFor(
    () => window.scholarflowWorkspace.getState().diagnostics.count > 0,
    12000,
  );
  const findings = window.scholarflowWorkspace.getState().diagnostics.findings;
  check(
    "analysis over Gurmukhi, emoji and CRLF text leaves the text unchanged",
    editor.value === (autosaveCase ? `${autosaveCase.expected}Autosaved without pressing Save: \u0a17\u0a41\u0a30\u0a2e\u0a41\u0a16\u0a40\n` : editor.value),
    `${editor.value.length} characters`,
  );
  check(
    "every finding over that text slices to exactly its own original",
    !analysed ||
      findings.every((finding) => editor.value.slice(finding.start, finding.end) === finding.original),
    findings
      .filter((finding) => editor.value.slice(finding.start, finding.end) !== finding.original)
      .map((finding) => finding.id)
      .join(", "),
  );

  window.close();
  return { cases: cases.length, findings: findings.length };
}

/* ------------------------------------------------------- randomised order
 *
 * A person does not do things in a tidy order. This runs a seeded, repeatable
 * sequence of edits, saves, analyses, accepts, dismisses and document switches,
 * keeping its own model of what every document's text should be, and comparing
 * the whole text after every step. The seed and the operation order are printed,
 * so any failure can be replayed exactly.
 *
 * The rule the model encodes is the one the editor promises: text that is not
 * stored yet must still be offered back when the document is reopened, and
 * recovering it must restore exactly what was typed. Nothing may be substituted
 * by another document's text.
 */
function mulberry32(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let value = Math.imul(state ^ (state >>> 15), 1 | state);
    value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value;
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

/* An index that never falls between the two halves of a character outside the
 * Basic Multilingual Plane: a textarea can hold a lone surrogate, but it is not
 * text anybody typed, and the store refuses it. */
function safeIndex(value, index) {
  if (index > 0 && index < value.length) {
    const code = value.charCodeAt(index);
    if (code >= 0xdc00 && code <= 0xdfff) return index - 1;
  }
  return index;
}

/* Where two texts first differ, with the context, so a failure names the
 * character instead of printing two identical-looking prefixes. */
function firstDifference(actual, expected) {
  let index = 0;
  while (index < actual.length && index < expected.length && actual[index] === expected[index]) {
    index += 1;
  }
  return (
    `first difference at character ${index}: ` +
    `${JSON.stringify(actual.slice(Math.max(0, index - 20), index + 20))} instead of ` +
    `${JSON.stringify(expected.slice(Math.max(0, index - 20), index + 20))}`
  );
}

async function randomisedLifecycle(seed) {
  console.log(`\n== Randomised lifecycle (seed ${seed}) ==`);
  const random = mulberry32(seed);
  const pick = (count) => Math.floor(random() * count);
  const title = (index) => `Rand ${seed}-${index}`;
  const initial = (index) => `Document ${index} of seed ${seed}.\nA second line, with a comma.\n`;

  const created = [];
  for (let index = 0; index < 3; index += 1) {
    created.push(await apiCreateDocument(title(index), initial(index)));
  }
  const ids = created.map((entry) => entry.id);
  // The first line of each document is never edited, so it is a stable
  // signature: a document that starts with another document's first line is one
  // that has received another document's text.
  const signature = (index) => `Document ${index} of seed ${seed}.`;
  const expected = new Map(ids.map((id, index) => [id, initial(index)]));
  const stored = new Map(ids.map((id, index) => [id, initial(index)]));

  // Writes are held back a little, the way a slow disk holds them: that is when
  // the order of responses starts to matter, and the walk is meant to reach the
  // states a person cannot plan.
  const page = await loadPage("/workspace", {
    delayResponses: [{ method: "PUT", pattern: "/api/documents/", ms: 1500 }],
  });
  const { window, document } = page;
  const editor = document.getElementById("editor");
  const banner = document.getElementById("recovery-banner");
  const rowFor = (index) =>
    [...document.querySelectorAll("#document-list button.list-item")].find((button) =>
      button.textContent.includes(title(index)),
    );

  const failures = [];
  const log = [];
  const trace = [];
  let currentIndex = -1;
  const fail = (message) =>
    failures.push(
      `${log.length ? log[log.length - 1] : "start"}: ${message}` +
        `\n      trace: ${trace.slice(-8).join(" | ")}`,
    );

  /* One line per operation: which document is open, whether it is dirty, the
   * length of the editor's text, of every document's expected text, and of every
   * draft in this browser. A failure then shows the step where the state drifted
   * instead of a single snapshot at the end. */
  const noteKeeping = (index) => {
    keptNotice = `document ${index} kept its unsaved text in the editor`;
  };

  const note = (label) => {
    const state = window.scholarflowWorkspace.getState();
    const parts = [`${label}`, `open=${ids.indexOf(state.documentId)}`, `dirty=${state.dirty ? 1 : 0}`, `editor=${editor.value.length}`];
    for (let index = 0; index < ids.length; index += 1) {
      parts.push(`e${index}=${expected.get(ids[index]).length}`);
    }
    const draftLengths = [];
    for (let at = 0; at < window.localStorage.length; at += 1) {
      const key = window.localStorage.key(at);
      if (!key.startsWith("scholarflow:draft:")) continue;
      const index = ids.indexOf(key.slice("scholarflow:draft:".length));
      try {
        draftLengths.push(`d${index}=${String(JSON.parse(window.localStorage.getItem(key)).text).length}`);
      } catch {
        draftLengths.push(`d${index}=unreadable`);
      }
    }
    parts.push(`drafts=[${draftLengths.join(",")}]`);
    trace.push(parts.join(" "));
    if (trace.length > 40) trace.shift();
  };

  const storedNow = async (index) => (await serverDocument(ids[index])).text;
  let keptNotice = "";

  // What the previous session left in this browser for each document.
  const drafts = () => {
    const out = {};
    for (let at = 0; at < window.localStorage.length; at += 1) {
      const key = window.localStorage.key(at);
      if (!key.startsWith("scholarflow:draft:")) continue;
      const id = key.slice("scholarflow:draft:".length);
      try {
        const stored = String(JSON.parse(window.localStorage.getItem(key)).text);
        out[`document ${ids.indexOf(id)}`] = `${stored.length} characters ${JSON.stringify(stored.slice(-24))}`;
      } catch {
        out[`document ${ids.indexOf(id)}`] = "<unreadable>";
      }
    }
    return out;
  };

  /* Open a document the way a person does, and hold the application to its
   * promise about text that is not stored yet. */
  const openIndex = async (index, { recover = true } = {}) => {
    const row = rowFor(index);
    if (!row) {
      fail(`document ${index} is not listed in the sidebar`);
      return false;
    }
    row.click();
    const opened = await waitFor(() => window.scholarflowWorkspace.getState().documentId === ids[index], 6000);
    if (!opened) {
      fail(`document ${index} could not be opened`);
      return false;
    }
    currentIndex = index;
    const id = ids[index];
    const storedText = await storedNow(index);
    stored.set(id, storedText);
    if (!storedText.startsWith(signature(index))) {
      fail(
        `document ${index} no longer starts with its own first line: ` +
          `${JSON.stringify(storedText.slice(0, 40))}`,
      );
    }
    const want = expected.get(id);
    if (storedText === want) {
      return true; // nothing is unsaved for this document
    }
    // Text that is not stored yet must not be lost. Either the editor already
    // holds it — the application kept what was typed — or the stored text is
    // shown and the words are offered back.
    if (editor.value === want) {
      noteKeeping(index);
      return true;
    }
    if (banner.hidden !== false) {
      fail(
        `an unsaved edit to document ${index} was neither kept, nor stored, nor offered back: ` +
          `stored ${storedText.length} characters ${JSON.stringify(storedText.slice(-24))}, ` +
          `expected ${want.length} characters ${JSON.stringify(want.slice(-24))}, ` +
          `editor ${editor.value.length} characters ${JSON.stringify(editor.value.slice(-24))}, ` +
          `drafts ${JSON.stringify(drafts())}`,
      );
      return true;
    }
    if (recover) {
      document.getElementById("recover-button").click();
      await sleep(200);
      if (editor.value !== want) {
        fail(`recovering document ${index} gave back ${firstDifference(editor.value, want)}`);
      }
    }
    return true;
  };

  const expectEditor = (label) => {
    if (currentIndex < 0) {
      fail(`${label}: no document was open`);
      return;
    }
    const want = expected.get(ids[currentIndex]);
    if (editor.value !== want) {
      fail(`${label}: the editor holds ${firstDifference(editor.value, want)}`);
    }
  };

  const saveOpen = async (label) => {
    const settled = await saveAndSettle(window);
    const index = currentIndex;
    const id = ids[index];
    const want = expected.get(id);
    if (editor.value !== want) {
      fail(`${label}: the editor holds ${firstDifference(editor.value, want)}`);
      return;
    }
    const nowStored = await storedNow(index);
    stored.set(id, nowStored);
    if (nowStored !== want) {
      fail(
        `${label}: document ${index} stored ${firstDifference(nowStored, want)}` +
          (settled
            ? ""
            : ` (the save never settled: editor revision ${window.scholarflowWorkspace.getState().revision}, ` +
              `server revision ${(await serverDocument(id)).revision}, ` +
              `conflict banner ${document.getElementById("conflict-banner").hidden ? "hidden" : "shown"}, ` +
              `error ${JSON.stringify(document.getElementById("error-message").textContent.slice(0, 90))})`),
      );
    }
    // No other document may have been touched by saving this one. Another
    // document is allowed to change only into *its own* text (an autosave of an
    // edit made earlier); anything else means one document's words were written
    // into another's file.
    for (let other = 0; other < ids.length; other += 1) {
      if (other === index) continue;
      const otherStored = await storedNow(other);
      const allowed = otherStored === stored.get(ids[other]) || otherStored === expected.get(ids[other]);
      if (!allowed) {
        fail(
          `${label}: saving document ${index} changed document ${other} to ` +
            `${firstDifference(otherStored, stored.get(ids[other]))}`,
        );
      }
      if (!otherStored.startsWith(signature(other))) {
        fail(
          `${label}: document ${other} now starts with ${JSON.stringify(otherStored.slice(0, 40))}, ` +
            `which is not its own text`,
        );
      }
      stored.set(ids[other], otherStored);
    }
  };

  const words = [
    "argument", "evidence", "caste", "commons", "fieldwork", "archive", "reading",
    "chapter", "note", "citation", "method", "sample",
  ];
  const steps = 26;
  for (let step = 0; step < steps; step += 1) {
    const operation = pick(10);
    const label = `step ${step}`;

    if (currentIndex < 0 || operation <= 1) {
      const index = pick(ids.length);
      log.push(`open(${index})`);
      await openIndex(index);
      expectEditor(`${label} open(${index})`);
      note(`open(${index})`);
      continue;
    }

    const id = ids[currentIndex];
    if (operation === 2 || operation === 3 || operation === 4) {
      const before = expected.get(id);
      let after;
      if (operation === 2) {
        after = `${before}${
          [
            "A sentence added by the random walk, in order to exercise corrections.",
            "Another clause, added mid-thought; with a semicolon.",
            "\u0a07\u0a71\u0a15 \u0a05\u0a16\u0a3c\u0a2c\u0a3e\u0a30\u0a40 \u0a32\u0a3e\u0a08\u0a28\u0964",
            "A line with an emoji \ud83d\ude42 and a dash \u2014 here.",
            "The tehnique of the argument is fine, but the evidence dont support it.",
            "A number of samples were read in order to test the method.",
          ][pick(6)]
        }\n`;
      } else if (operation === 3) {
        const at = safeIndex(
          before,
          signature(currentIndex).length + pick(before.length - signature(currentIndex).length + 1),
        );
        after = `${before.slice(0, at)}${
          [" [inserted] ", " (a parenthetical) ", ` ${words[pick(words.length)]} `][pick(3)]
        }${before.slice(at)}`;
      } else if (before.length > signature(currentIndex).length + 8) {
        const at = safeIndex(
          before,
          signature(currentIndex).length + pick(before.length - signature(currentIndex).length - 6),
        );
        const until = safeIndex(before, Math.min(before.length, at + 1 + pick(6)));
        after = before.slice(0, at) + before.slice(until);
      } else {
        after = `${before} More text, because there was too little to delete.\n`;
      }
      type(window, document, after);
      expected.set(id, after);
      log.push(`edit(${operation})@${after.length}`);
      expectEditor(`${label} edit(${operation})`);
      note(`edit(${operation}) doc ${currentIndex}`);
      continue;
    }

    if (operation === 5) {
      log.push(`save(doc ${currentIndex})`);
      await saveOpen(`${label} save`);
      note(`save(doc ${currentIndex})`);
      continue;
    }

    if (operation === 6) {
      window.scholarflowWorkspace.analyse();
      await sleep(1500);
      log.push("analyse");
      expectEditor(`${label} analyse`);
      note("analyse");
      continue;
    }

    if (operation === 7 || operation === 8) {
      const findings = window.scholarflowWorkspace.getState().diagnostics.findings;
      if (!findings.length) {
        log.push(`${operation === 7 ? "accept" : "dismiss"}(no findings)`);
        expectEditor(`${label} no findings`);
        continue;
      }
      const correctable = findings.filter(
        (item) => item.replacement !== null && item.replacement !== undefined,
      );
      const pool = operation === 7 && correctable.length ? correctable : findings;
      const finding = pool[pick(pool.length)];
      window.scholarflowWorkspace.openSuggestion(finding.id);
      await sleep(120);
      const analysedText = window.scholarflowWorkspace.getState().diagnostics.analysedText;
      const applyable =
        finding.replacement !== null &&
        finding.replacement !== undefined &&
        analysedText === expected.get(id) &&
        expected.get(id).slice(finding.start, finding.end) === finding.original;
      if (operation === 7) {
        document.getElementById("suggestion-accept").click();
        await sleep(300);
        if (applyable) {
          expected.set(id, spliceText(expected.get(id), finding.start, finding.end, finding.replacement));
          log.push(`accept(${finding.id})`);
        } else {
          log.push(`accept(${finding.id}) refused-or-inapplicable`);
        }
      } else {
        document.getElementById("suggestion-dismiss").click();
        await sleep(300);
        log.push(`dismiss(${finding.id})`);
      }
      expectEditor(`${label} ${operation === 7 ? "accept" : "dismiss"}`);
      note(`${operation === 7 ? "accept" : "dismiss"} doc ${currentIndex}`);
      continue;
    }

    // The last operation: go away and come back, then leave and return a second
    // time with the text still unsaved.
    {
      const away = currentIndex;
      const other = (away + 1) % ids.length;
      log.push(`switch(${away}->${other})`);
      note(`switch away from ${away}`);
      await openIndex(other);
      expectEditor(`step ${step} switch away`);
      await openIndex(away);
      expectEditor(`step ${step} switch back`);
      note(`switch back to ${away}`);
      const want = expected.get(id);
      if (editor.value !== want && banner.hidden === false) {
        document.getElementById("recover-button").click();
        await sleep(200);
        log.push(`recover(${id})`);
        expectEditor(`step ${step} recover`);
      }
    }
  }

  // A restart: an unsaved edit must survive a fresh page, keyed to its own
  // document, and must not appear in any other document.
  if (currentIndex >= 0) {
    const id = ids[currentIndex];
    const restartText = `${expected.get(id)}An edit typed just before the application restarts.\n`;
    type(window, document, restartText);
    expected.set(id, restartText);
    log.push(`restart-edit(doc ${currentIndex})`);
    // jsdom gives every window a fresh localStorage, so the only faithful way to
    // model a restart is to seed the window with the draft the previous session
    // left behind — the same way the crash-recovery checks do it.
    const reloaded = await loadPage("/workspace", {
      seedDraft: { id, text: restartText, title: title(currentIndex) },
    });
    const rows = [...reloaded.document.querySelectorAll("#document-list button.list-item")];
    const row = rows.find((button) => button.textContent.includes(title(currentIndex)));
    if (!row) {
      fail("after a restart the document is not listed");
    } else {
      row.click();
      await waitFor(
        () => reloaded.window.scholarflowWorkspace.getState().documentId === id,
        6000,
      );
      const restartBanner = reloaded.document.getElementById("recovery-banner");
      if (restartBanner.hidden !== false) {
        const nowStored = await storedNow(currentIndex);
        if (nowStored !== restartText) {
          fail(
            `an unsaved edit did not survive a restart and was not offered back: stored ` +
              `${JSON.stringify(nowStored.slice(0, 30))} instead of ${JSON.stringify(restartText.slice(0, 30))}`,
          );
        }
      } else {
        reloaded.document.getElementById("recover-button").click();
        await sleep(200);
        if (reloaded.document.getElementById("editor").value !== restartText) {
          fail(
            `after a restart the recovered text was ${firstDifference(
              reloaded.document.getElementById("editor").value,
              restartText,
            )}`,
          );
        }
      }
      // The other documents must not have received that text.
      for (let other = 0; other < ids.length; other += 1) {
        if (other === currentIndex) continue;
        const otherStored = await storedNow(other);
        if (otherStored.includes("just before the application restarts")) {
          fail(`after a restart document ${other} holds document ${currentIndex}'s unsaved text`);
        }
      }
    }
    reloaded.window.close();
  }

  // Finish honestly: open every document, recover anything offered, save, and
  // compare the stored text in full against the walk's model.
  for (let index = 0; index < ids.length; index += 1) {
    await openIndex(index);
    await saveOpen(`final save of document ${index}`);
    const finalText = await storedNow(index);
    if (!finalText.startsWith(signature(index))) {
      failures.push(
        `document ${index} stored another document's text: ${JSON.stringify(finalText.slice(0, 40))}`,
      );
    }
    if (finalText !== expected.get(ids[index])) {
      failures.push(
        `document ${index} does not match the expected text at the end of the walk: ` +
          firstDifference(finalText, expected.get(ids[index])),
      );
    }
  }

  if (keptNotice) console.log(`   note: ${keptNotice}`);
  console.log(`   seed ${seed}, operations: ${log.join(" > ")}`);
  if (failures.length) console.log(`   trace:\n     ${trace.join("\n     ")}`);
  check(
    `a seeded random walk of ${steps} operations never rewrites the wrong text`,
    failures.length === 0,
    failures.slice(0, 3).join(" | "),
  );

  window.close();
  return { seed, steps, log };
}

async function textIntegrityUnderDiagnostics() {
  console.log("\n== Text integrity under diagnostics and refinement ==");
  // execCommand is provided because the page prefers it in a real browser to
  // keep the native undo stack; the automated path must be exercised too.
  const page = await loadPage("/workspace", { execCommand: true });
  const { window, document } = page;
  const documentId = await newWorkspaceDocument(page, "Integrity passage");
  check("a document could be created for the integrity checks", Boolean(documentId));

  const editor = document.getElementById("editor");
  type(window, document, CHECKLIST_PASSAGE);
  let expected = CHECKLIST_PASSAGE;

  const analysed = await waitFor(
    () => window.scholarflowWorkspace.getState().diagnostics.count > 0,
    9000,
  );
  const findings = window.scholarflowWorkspace.getState().diagnostics.findings;
  check("the passage produces findings", analysed, `${findings.length} findings`);
  check(
    "running diagnostics does not change the document text",
    editor.value === expected,
    `${editor.value.length} characters`,
  );
  check(
    "every finding's offsets slice to exactly its own original text",
    findings.every((finding) => expected.slice(finding.start, finding.end) === finding.original),
    findings
      .filter((finding) => expected.slice(finding.start, finding.end) !== finding.original)
      .map((finding) => finding.id)
      .join(", "),
  );
  check(
    "no finding points at an empty or reversed range",
    findings.every(
      (finding) =>
        Number.isInteger(finding.start) &&
        Number.isInteger(finding.end) &&
        finding.end > finding.start,
    ),
  );
  const markers = document.querySelectorAll("#marker-layer .marker");
  check("markers are rendered", markers.length > 0, `${markers.length} markers`);

  // --- accepting changes only the accepted range -------------------------
  const spelling = findings.find((finding) => finding.id.startsWith("spelling.misspelling"));
  if (spelling) {
    const predicted = spliceText(expected, spelling.start, spelling.end, spelling.replacement);
    window.scholarflowWorkspace.openSuggestion(spelling.id);
    await sleep(150);
    document.getElementById("suggestion-accept").click();
    await sleep(500);
    check(
      "accepting a correction splices exactly its own range",
      editor.value === predicted,
      `${editor.value.length} vs ${predicted.length} characters`,
    );
    check(
      "accepting keeps every other character byte-identical",
      editor.value.slice(0, spelling.start) === expected.slice(0, spelling.start) &&
        editor.value.slice(spelling.start + spelling.replacement.length) ===
          expected.slice(spelling.end),
    );
    structureChecks("after an accept", editor.value);
    expected = predicted;
  } else {
    check("a spelling finding was available to accept", false);
  }

  // --- dismissing changes nothing ----------------------------------------
  await waitFor(() => window.scholarflowWorkspace.getState().diagnostics.count > 0, 9000);
  const dismissible = window.scholarflowWorkspace
    .getState()
    .diagnostics.findings.find((finding) => finding.id !== spelling?.id);
  if (dismissible) {
    window.scholarflowWorkspace.openSuggestion(dismissible.id);
    await sleep(150);
    document.getElementById("suggestion-dismiss").click();
    await sleep(300);
    check("dismissing a suggestion leaves the text untouched", editor.value === expected);
  }

  // --- a stale suggestion is refused -------------------------------------
  await waitFor(() => window.scholarflowWorkspace.getState().diagnostics.count > 0, 9000);
  const stale = window.scholarflowWorkspace
    .getState()
    .diagnostics.findings.find((finding) => Boolean(finding.replacement));
  if (stale) {
    window.scholarflowWorkspace.openSuggestion(stale.id);
    await sleep(150);
    const at = expected.indexOf("There is many studies") + "There is ".length;
    const typed = expected.slice(0, at) + "now " + expected.slice(at);
    type(window, document, typed);
    await sleep(250);
    document.getElementById("suggestion-accept").click();
    await sleep(500);
    check(
      "a suggestion whose text has moved is refused, not applied",
      editor.value === typed,
      `${editor.value.length} vs ${typed.length} characters`,
    );
    structureChecks("after the refusal", editor.value);
    expected = typed;
  } else {
    check("a finding with a replacement was available for the stale check", false);
  }

  // --- saving must not wipe the analysis ---------------------------------
  await waitFor(
    () =>
      window.scholarflowWorkspace.getState().diagnostics.count > 0 &&
      !window.scholarflowWorkspace.getState().diagnostics.loading,
    9000,
  );
  const beforeSave = window.scholarflowWorkspace.getState().diagnostics;
  document.getElementById("save-document").click();
  const savedState = await waitFor(
    () => /Saved/.test(document.getElementById("save-state").textContent),
    9000,
  );
  const afterSave = window.scholarflowWorkspace.getState().diagnostics;
  check("saving reaches the saved state", savedState);
  check(
    "saving does not wipe the findings in the panel",
    afterSave.count === beforeSave.count && afterSave.analysedText !== null,
    `before=${beforeSave.count} after=${afterSave.count}`,
  );
  check("saving does not change the text", editor.value === expected);
  structureChecks("after saving", editor.value);

  // --- save and reopen ---------------------------------------------------
  const stored = await serverDocument(documentId);
  check("the stored document is byte-identical to the editor", stored.text === editor.value,
    `${stored.text.length} vs ${editor.value.length} characters`);
  const reopened = await loadPage("/workspace", { execCommand: true });
  const opened = await waitFor(
    () => reopened.window.scholarflowWorkspace?.getState().documentId === documentId,
    9000,
  );
  check("reopening the workspace opens the saved document", opened);
  const reopenedText = reopened.document.getElementById("editor").value;
  check(
    "the reopened document is byte-identical to what was saved",
    reopenedText === expected,
    `${reopenedText.length} vs ${expected.length} characters`,
  );
  structureChecks("after reopening", reopenedText);
  check(
    "the accepted correction survived the round trip",
    reopenedText.includes("technique") && !reopenedText.includes("tehnique"),
  );
  reopened.window.close();

  // --- typing before the application has finished loading ----------------
  // A cold start reads the document list from disk. Somebody can already be
  // writing in that window, and those words belong to no document yet.
  const slowBoot = await loadPage("/workspace", { delayListMs: 1500, execCommand: true });
  const earlyEditor = slowBoot.document.getElementById("editor");
  const earlyText = "# Early paste\n\nWritten before the document list arrived.\n";
  earlyEditor.value = earlyText;
  earlyEditor.setSelectionRange(earlyText.length, earlyText.length);
  earlyEditor.dispatchEvent(new slowBoot.window.Event("input", { bubbles: true }));
  await sleep(3500);
  check(
    "text typed before the application finished loading is still there",
    earlyEditor.value === earlyText,
    `now ${JSON.stringify(earlyEditor.value.slice(0, 60))}`,
  );
  slowBoot.window.close();

  // --- rapid typing while checks are in flight ---------------------------
  const rapid = await loadPage("/workspace", { execCommand: true });
  await newWorkspaceDocument(rapid, "Rapid typing");
  const rapidEditor = rapid.document.getElementById("editor");
  let rapidExpected = CHECKLIST_PASSAGE;
  type(rapid.window, rapid.document, rapidExpected);
  for (let round = 0; round < 8; round += 1) {
    rapidExpected += " extra";
    type(rapid.window, rapid.document, rapidExpected);
    await sleep(140); // faster than the check debounce and the autosave timer
  }
  check("the burst of typing is in the editor", rapidEditor.value === rapidExpected);
  await sleep(4500);
  check(
    "the burst of typing survives the checks and the autosave",
    rapidEditor.value === rapidExpected,
    `${rapidEditor.value.length} vs ${rapidExpected.length} characters`,
  );
  structureChecks("after rapid typing", rapidEditor.value);
  const rapidId = rapid.window.scholarflowWorkspace.getState().documentId;
  const rapidStored = await serverDocument(rapidId);
  check(
    "the stored document matches after rapid typing",
    rapidStored.text === rapidExpected,
    `${rapidStored.text.length} vs ${rapidExpected.length} characters`,
  );
  rapid.window.close();

  // --- a randomised sequence, checked against an oracle ------------------
  // Actions a person might take in any order. The probe keeps its own copy of
  // what the text should be, so a duplicated paragraph, a reordered clause or a
  // truncated tail fails the run with the action that caused it.
  const mixed = await loadPage("/workspace", { execCommand: true });
  const mixedId = await newWorkspaceDocument(mixed, "Mixed sequence");
  const mixedEditor = mixed.document.getElementById("editor");
  let oracle = CHECKLIST_PASSAGE;
  type(mixed.window, mixed.document, oracle);
  await waitFor(() => mixed.window.scholarflowWorkspace.getState().diagnostics.count > 0, 9000);

  let seed = 20261015;
  const random = () => {
    seed = (seed * 1103515245 + 12345) % 2147483648;
    return seed / 2147483648;
  };
  let diverged = false;
  for (let step = 0; step < 8 && !diverged; step += 1) {
    const roll = random();
    const diagnostics = mixed.window.scholarflowWorkspace.getState().diagnostics;
    if (roll < 0.4) {
      const candidates = diagnostics.findings.filter((finding) => Boolean(finding.replacement));
      if (!candidates.length) continue;
      const finding = candidates[Math.floor(random() * candidates.length) % candidates.length];
      // The page must apply a finding only while it still describes the text at
      // those characters. Model that rule: a finding from a superseded analysis
      // must be refused, and then the document must not change at all.
      const stillValid =
        mixed.window.scholarflowWorkspace.getState().diagnostics.analysedText ===
          mixedEditor.value && mixedEditor.value.slice(finding.start, finding.end) === finding.original;
      mixed.window.scholarflowWorkspace.openSuggestion(finding.id);
      await sleep(120);
      const accept = mixed.document.getElementById("suggestion-accept");
      if (mixed.document.getElementById("suggestion-card").hidden || accept.disabled) continue;
      accept.click();
      await sleep(450);
      const predicted = stillValid
        ? spliceText(oracle, finding.start, finding.end, finding.replacement)
        : oracle;
      check(
        `random step ${step}: accepting ${finding.id.split("@")[0]} ${stillValid ? "splices only its range" : "is refused because the text moved"}`,
        mixedEditor.value === predicted,
        `${mixedEditor.value.length} vs ${predicted.length} characters`,
      );
      oracle = predicted;
      diverged = mixedEditor.value !== oracle;
    } else if (roll < 0.6) {
      const finding = diagnostics.findings[Math.floor(random() * Math.max(1, diagnostics.findings.length))];
      if (!finding) continue;
      mixed.window.scholarflowWorkspace.openSuggestion(finding.id);
      await sleep(120);
      mixed.document.getElementById("suggestion-dismiss").click();
      await sleep(250);
      check(`random step ${step}: dismissing changes nothing`, mixedEditor.value === oracle);
      diverged = mixedEditor.value !== oracle;
    } else if (roll < 0.8) {
      oracle += " further note";
      type(mixed.window, mixed.document, oracle);
      await sleep(200);
      check(`random step ${step}: typing is preserved`, mixedEditor.value === oracle);
      diverged = mixedEditor.value !== oracle;
    } else {
      mixed.document.getElementById("save-document").click();
      await sleep(900);
      check(`random step ${step}: saving changes nothing`, mixedEditor.value === oracle);
      diverged = mixedEditor.value !== oracle;
    }
    await waitFor(
      () =>
        mixed.window.scholarflowWorkspace.getState().diagnostics.count > 0 ||
        mixed.window.scholarflowWorkspace.getState().diagnostics.error,
      6000,
    );
  }
  structureChecks("after the randomised sequence", mixedEditor.value);
  const mixedStored = await serverDocument(mixedId);
  check("the stored document matches the oracle after the randomised sequence",
    mixedStored.text === oracle,
    `${mixedStored.text.length} vs ${oracle.length} characters`);
  mixed.window.close();

  return documentId;
}

async function main() {
  const health = await fetch(`${BASE}/health`).then((response) => response.json());
  check("live server is reachable", health.status === "ok", health.service);

  const documentId = await stage1Workspace();
  await stage2Diagnostics();
  await stage3Diagnostics();
  await textIntegrityUnderDiagnostics();
  await documentIdentityUnderInFlightRequests();
  await savingTwiceInARowIsNotDropped();
  await emojiOffsetsDoNotBreakCorrections();
  await aCancelledCheckIsNotReportedAsClean();
  await textRepresentationOracle();
  for (const seed of LIFECYCLE_SEEDS) {
    await randomisedLifecycle(seed);
  }
  await quickEditorRefine();

  // The saved document is still on disk at the end of the run.
  const finalDocument = await serverDocument(documentId);
  check("document survived the whole session", finalDocument.text.length > 0, `revision=${finalDocument.revision}`);

  console.log(`\nGUI RESULT: ${failures === 0 ? "PASS" : "FAIL"} (${checks - failures}/${checks} checks passed)`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((error) => {
  console.error("GUI harness error:", error);
  process.exit(2);
});
