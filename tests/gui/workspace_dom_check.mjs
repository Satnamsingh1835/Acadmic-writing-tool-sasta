/*
 * ScholarFlow GUI checks — drives the real pages in a DOM against a live server.
 *
 * Usage: node tests/gui/workspace_dom_check.mjs <base-url>
 *
 * These checks exercise the writing workspace (stage 1) and the quick editor's
 * refine path the way a person uses them: typing, toolbar edits, saving,
 * reloading, crash recovery, accepting and dismissing suggestions, and error
 * handling. They are run from tests/test_workspace_gui.py so `pytest` covers
 * both the API and the interface.
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
async function loadPage(path, { offline = false, seedDraft = null } = {}) {
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
      window.fetch = (input, options) => {
        if (offline) return Promise.reject(new TypeError("Failed to fetch"));
        return fetch(new URL(input, BASE).href, options);
      };
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

async function main() {
  const health = await fetch(`${BASE}/health`).then((response) => response.json());
  check("live server is reachable", health.status === "ok", health.service);

  const documentId = await stage1Workspace();
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
