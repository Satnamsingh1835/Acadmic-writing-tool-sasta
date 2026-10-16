const byId = (id) => document.getElementById(id);
const statusNode = byId("library-status");

async function request(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || payload.message || ("HTTP " + response.status));
  return payload;
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function renderWorkList(container, records) {
  container.replaceChildren();
  if (!records.length) {
    container.append(node("p", "empty", "No matching records. Import references or broaden your search."));
    return;
  }
  records.forEach((record) => {
    const card = node("article", "record");
    const heading = node("h3", "", record.title || "(untitled record)");
    card.append(heading);
    const authors = Array.isArray(record.authors) ? record.authors.join(", ") : "";
    card.append(node("p", "meta", [authors, record.year || "", record.publication || ""].filter(Boolean).join(" · ")));
    card.append(node("p", "meta", "Type: " + (record.item_type || "unknown") + " · Access: " + (record.access_status || "metadata_only")));
    if (record.doi) card.append(node("p", "meta", "DOI: " + record.doi));
    if (record.abstract) card.append(node("p", "abstract", record.abstract.slice(0, 900)));
    const actions = node("div", "record-actions");
    const idText = node("code", "", "ID: " + record.id);
    actions.append(idText);
    const use = node("button", "secondary", "Use in matrix");
    use.type = "button";
    use.addEventListener("click", () => {
      byId("matrix-work-id").value = record.id;
      byId("work-id").value = record.id;
      byId("matrix-question").focus();
    });
    actions.append(use);
    if (record.url) {
      const link = node("a", "text-link", "Source link");
      link.href = record.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      actions.append(link);
    }
    card.append(actions);
    container.append(card);
  });
}

async function searchLibrary() {
  const params = new URLSearchParams();
  const values = {
    q: byId("query").value.trim(),
    author: byId("author").value.trim(),
    year: byId("year").value,
    item_type: byId("item-type").value,
    access_status: byId("access-status").value,
    sort: byId("sort").value,
    limit: 50,
  };
  Object.entries(values).forEach(([key, value]) => { if (value !== "") params.set(key, value); });
  try {
    const result = await request("/api/library/search?" + params.toString());
    renderWorkList(byId("library-results"), result.results || []);
  } catch (error) {
    byId("library-results").textContent = "Search failed: " + error.message;
  }
}

async function loadHealth() {
  try {
    const health = await request("/api/library/health");
    statusNode.textContent = "Local database ready · " + health.work_count + " records · " +
      health.document_count + " indexed documents · FTS5 " + (health.fts5_available ? "available" : "fallback search");
    const settings = await request("/api/library/settings");
    byId("offline").checked = !!settings.offline;
    byId("crossref-enabled").checked = !!settings.crossref_enabled;
    byId("openalex-enabled").checked = !!settings.openalex_enabled;
    await loadMatrix();
    // Show existing records immediately so a reopened library is not
    // mistaken for an empty one; the search form still re-filters them.
    await searchLibrary();
  } catch (error) {
    statusNode.textContent = "Library unavailable: " + error.message;
    statusNode.classList.add("error");
  }
}

byId("library-search").addEventListener("submit", async (event) => {
  event.preventDefault();
  await searchLibrary();
});

byId("add-work-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const resultNode = byId("add-work-result");
  const title = byId("add-title").value.trim();
  if (!title) { resultNode.textContent = "Add a title before saving the reference."; return; }
  const record = {
    title,
    authors: byId("add-authors").value.split(",").map((name) => name.trim()).filter(Boolean),
    year: byId("add-year").value ? Number(byId("add-year").value) : null,
    item_type: byId("add-type").value,
    publication: byId("add-publication").value.trim(),
    doi: byId("add-doi").value.trim(),
    url: byId("add-url").value.trim(),
    abstract: byId("add-abstract").value.trim(),
    source: "manual",
  };
  resultNode.textContent = "Saving reference…";
  try {
    const result = await request("/api/library/work", { method: "POST", body: JSON.stringify({ record }) });
    resultNode.textContent = result.duplicate
      ? "That reference already exists in your library (ID: " + result.id + ")."
      : "Reference saved locally (ID: " + result.id + "). It will remain after restarting ScholarFlow.";
    if (!result.duplicate) byId("add-work-form").reset();
    await loadHealth();
  } catch (error) {
    resultNode.textContent = "Could not save the reference: " + error.message;
  }
});

byId("zotero-import").addEventListener("click", async () => {
  const resultNode = byId("zotero-result");
  resultNode.textContent = "Reading Zotero metadata…";
  try {
    const params = new URLSearchParams({
      source: byId("zotero-source").value,
      collection_key: byId("zotero-collection").value.trim(),
      limit: "100",
    });
    const result = await request("/api/library/import/zotero?" + params.toString(), { method: "POST", body: "{}" });
    resultNode.textContent = "Read " + result.items_read + "; imported " + result.imported +
      "; duplicates " + result.duplicates + "; skipped " + result.skipped + ". Read-only import.";
    await loadHealth();
  } catch (error) {
    resultNode.textContent = "Zotero import failed: " + error.message;
  }
});

byId("csl-import").addEventListener("click", async () => {
  const resultNode = byId("csl-result");
  const file = byId("csl-file").files[0];
  if (!file) { resultNode.textContent = "Choose a Zotero/CSL JSON export first."; return; }
  if (file.size > 5 * 1024 * 1024) { resultNode.textContent = "JSON export exceeds the 5 MiB UI limit."; return; }
  try {
    const parsed = JSON.parse(await file.text());
    const records = Array.isArray(parsed) ? parsed : [parsed];
    const result = await request("/api/library/import/csl-json", { method: "POST", body: JSON.stringify({ records }) });
    resultNode.textContent = "Imported " + result.imported + "; duplicates " + result.duplicates + "; skipped " + result.skipped + ".";
    await loadHealth();
  } catch (error) {
    resultNode.textContent = "Import failed: " + error.message;
  }
});

byId("document-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const resultNode = byId("document-result");
  const file = byId("document-file").files[0];
  if (!file) { resultNode.textContent = "Choose a document."; return; }
  if (file.size > 20 * 1024 * 1024) { resultNode.textContent = "The document exceeds the 20 MiB limit."; return; }
  const body = new FormData();
  body.append("file", file);
  body.append("work_id", byId("work-id").value.trim());
  body.append("source_url", byId("source-url").value.trim());
  body.append("licence", byId("licence").value.trim());
  try {
    const response = await fetch("/api/library/documents", { method: "POST", body });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || ("HTTP " + response.status));
    resultNode.textContent = "Indexed " + result.passages_indexed + " passages. " + (result.warning || "");
    await loadHealth();
  } catch (error) {
    resultNode.textContent = "Indexing failed: " + error.message;
  }
});

byId("discovery-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const container = byId("discovery-results");
  const provider = byId("provider").value;
  container.textContent = "Searching " + provider + "…";
  try {
    const params = new URLSearchParams({ q: byId("discovery-query").value.trim(), limit: "10" });
    const response = await request("/api/library/discovery/" + provider + "?" + params.toString());
    renderWorkList(container, response.results || []);
    if (response.status) container.prepend(node("p", "meta", "Provider status: " + response.status));
  } catch (error) {
    container.textContent = "Discovery failed: " + error.message;
  }
});

byId("save-settings").addEventListener("click", async () => {
  try {
    const settings = await request("/api/library/settings", {
      method: "PUT",
      body: JSON.stringify({
        offline: byId("offline").checked,
        crossref_enabled: byId("crossref-enabled").checked,
        openalex_enabled: byId("openalex-enabled").checked,
      }),
    });
    byId("settings-result").textContent = "Saved. Offline: " + settings.offline;
  } catch (error) {
    byId("settings-result").textContent = "Settings failed: " + error.message;
  }
});

byId("passage-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const container = byId("passage-results");
  try {
    const params = new URLSearchParams({ q: byId("passage-query").value.trim(), limit: "12" });
    const result = await request("/api/library/passages?" + params.toString());
    container.replaceChildren();
    if (!result.results.length) container.append(node("p", "empty", "No indexed passage matched. This is not proof that a research gap exists."));
    result.results.forEach((passage) => {
      const card = node("article", "record");
      card.append(node("h3", "", passage.title || passage.filename || "Local source"));
      card.append(node("p", "meta", "Page: " + (passage.page_number || "not available") + " · Evidence status: candidate passage"));
      card.append(node("p", "abstract", passage.supporting_passage || passage.text));
      card.append(node("p", "hint", passage.warning || "Verify in the original source."));
      container.append(card);
    });
  } catch (error) { container.textContent = "Passage search failed: " + error.message; }
});

byId("matrix-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = {
    work_id: byId("matrix-work-id").value.trim(),
    research_question: byId("matrix-question").value.trim(),
    claim: byId("matrix-claim").value.trim(),
    method: byId("matrix-method").value.trim(),
    supporting_passage: byId("matrix-passage").value.trim(),
    page_number: byId("matrix-page").value ? Number(byId("matrix-page").value) : null,
    evidence_level: "candidate",
  };
  try {
    await request("/api/library/matrix", { method: "POST", body: JSON.stringify(data) });
    byId("matrix-result").textContent = "Saved as a candidate row; verify evidence in the source.";
    byId("matrix-form").reset();
    await loadMatrix();
  } catch (error) { byId("matrix-result").textContent = "Could not save matrix row: " + error.message; }
});

async function loadMatrix() {
  try {
    const result = await request("/api/library/matrix");
    const container = byId("matrix-results");
    container.replaceChildren();
    (result.results || []).forEach((item) => {
      const card = node("article", "record");
      card.append(node("h3", "", item.title || "Untitled"));
      card.append(node("p", "meta", "Research question: " + item.research_question));
      if (item.claim) card.append(node("p", "abstract", item.claim));
      if (item.supporting_passage) card.append(node("blockquote", "", item.supporting_passage));
      card.append(node("p", "hint", "Evidence level: " + item.evidence_level + " · Page: " + (item.page_number || "not provided")));
      container.append(card);
    });
  } catch (error) {
    byId("matrix-results").textContent = "Matrix could not load: " + error.message;
  }
}

loadHealth();
