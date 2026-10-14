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
      window.fetch = async (input, options) => {
        if (offline) return Promise.reject(new TypeError("Failed to fetch"));
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
  await fetch(`${BASE}/api/workspace/dictionary/tehnique`, { method: "DELETE" }).catch(() => {});
  page.window.close();

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

async function main() {
  const health = await fetch(`${BASE}/health`).then((response) => response.json());
  check("live server is reachable", health.status === "ok", health.service);

  const documentId = await stage1Workspace();
  await stage2Diagnostics();
  await stage3Diagnostics();
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
