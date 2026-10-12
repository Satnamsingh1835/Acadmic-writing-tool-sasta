(() => {
  "use strict";

  const elements = {
    source: document.querySelector("#source-text"),
    refined: document.querySelector("#refined-text"),
    sourceCount: document.querySelector("#source-count"),
    outputCount: document.querySelector("#output-count"),
    outputEmpty: document.querySelector("#output-empty"),
    refineButton: document.querySelector("#refine-button"),
    useLlm: document.querySelector("#use-llm"),
    aiCaption: document.querySelector("#ai-caption"),
    engineStatus: document.querySelector("#engine-status"),
    providerLabel: document.querySelector("#provider-label"),
    results: document.querySelector("#results"),
    statRow: document.querySelector("#stat-row"),
    noticeList: document.querySelector("#notice-list"),
    suggestionsPanel: document.querySelector("#suggestions-panel"),
    structurePanel: document.querySelector("#structure-panel"),
    safeguardsPanel: document.querySelector("#safeguards-panel"),
    receiptPanel: document.querySelector("#receipt-panel"),
    suggestionCount: document.querySelector("#suggestion-count"),
    structureCount: document.querySelector("#structure-count"),
    unknownCount: document.querySelector("#unknown-count"),
    copyButton: document.querySelector("#copy-button"),
    downloadButton: document.querySelector("#download-button"),
    fileInput: document.querySelector("#file-input"),
    toast: document.querySelector("#toast"),
  };

  const state = {
    profile: "standard",
    capabilities: null,
    lastResult: null,
    toastTimer: null,
  };

  const sampleText = [
    "It is important to note that caste plays a crucial role in shaping access to land and village commons. Jodhka (2004) documents the relationship between caste location and agrarian resources.",
    "However, other studies identify regional variation in these arrangements (Gupta, 2000). This suggests that institutional context should be examined rather than assuming a uniform relationship. The issue remains underexplored in relation to changing local governance.",
  ].join("\n\n");

  function countText(value) {
    const trimmed = value.trim();
    return {
      words: trimmed ? trimmed.split(/\s+/u).length : 0,
      characters: value.length,
    };
  }

  function formatCount(value) {
    const count = countText(value);
    return `${count.words.toLocaleString()} words · ${count.characters.toLocaleString()} characters`;
  }

  function refreshCounts() {
    elements.sourceCount.textContent = formatCount(elements.source.value);
    elements.outputCount.textContent = formatCount(elements.refined.value);
  }

  function showToast(message, isError = false) {
    window.clearTimeout(state.toastTimer);
    elements.toast.textContent = message;
    elements.toast.classList.toggle("is-error", isError);
    elements.toast.classList.add("is-visible");
    state.toastTimer = window.setTimeout(() => {
      elements.toast.classList.remove("is-visible");
    }, 3200);
  }

  function setLoading(loading) {
    elements.refineButton.disabled = loading;
    elements.refineButton.querySelector(".button-label").textContent = loading
      ? "Refining…"
      : "Refine passage";
  }

  function createElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function emptyResult(message) {
    return createElement("div", "empty-result", message);
  }

  function renderStats(stats) {
    elements.statRow.replaceChildren();
    const values = [
      [stats.original_words, "Original words"],
      [stats.refined_words, "Refined words"],
      [`${stats.similarity_percent}%`, "Text retained"],
    ];
    values.forEach(([value, label]) => {
      const card = createElement("div", "stat-card");
      card.append(createElement("strong", "", String(value)));
      card.append(createElement("span", "", label));
      elements.statRow.append(card);
    });
  }

  function renderNotices(notices) {
    elements.noticeList.replaceChildren();
    notices.forEach((notice) => {
      elements.noticeList.append(createElement("div", "notice", notice));
    });
  }

  function renderSuggestions(suggestions) {
    elements.suggestionsPanel.replaceChildren();
    elements.suggestionCount.textContent = String(suggestions.length);
    if (!suggestions.length) {
      elements.suggestionsPanel.append(
        emptyResult("No sentence-level language issues were flagged. Review the refined passage for meaning and emphasis."),
      );
      return;
    }

    const list = createElement("div", "insight-list");
    suggestions.forEach((suggestion) => {
      const card = createElement("article", "insight-card");
      const header = document.createElement("header");
      header.append(
        createElement("h3", "", `Sentence ${suggestion.sentence}: ${suggestion.issue}`),
        createElement("span", "badge", "Manual check"),
      );
      card.append(header);
      card.append(createElement("p", "", suggestion.why || "Review this proposed revision."));
      if (suggestion.suggested_revision) {
        const quote = document.createElement("blockquote");
        quote.textContent = suggestion.suggested_revision;
        card.append(quote);
      }
      list.append(card);
    });
    elements.suggestionsPanel.append(list);
  }

  function readableRole(role) {
    return role.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function renderStructure(literatureReview) {
    const paragraphs = literatureReview.paragraphs || [];
    elements.structurePanel.replaceChildren();
    elements.structureCount.textContent = String(paragraphs.length);
    if (!paragraphs.length) {
      elements.structurePanel.append(emptyResult("No paragraph diagnostics are available."));
      return;
    }

    const list = createElement("div", "insight-list");
    paragraphs.forEach((paragraph) => {
      const missing = paragraph.missing || [];
      const card = createElement("article", "insight-card");
      const header = document.createElement("header");
      header.append(createElement("h3", "", `Paragraph ${paragraph.paragraph}`));
      header.append(
        createElement(
          "span",
          `badge ${missing.length ? "is-warning" : "is-good"}`,
          missing.length ? `${missing.length} prompts` : "Flow detected",
        ),
      );
      card.append(header);

      if (missing.length) {
        card.append(
          createElement("p", "", `Consider: ${missing.map(readableRole).join(", ")}.`),
        );
        const prompts = paragraph.editorial_prompts || [];
        prompts.slice(0, 2).forEach((prompt) => card.append(createElement("p", "", prompt)));
      } else {
        card.append(
          createElement("p", "", "All tracked literature-review roles were detected. This is a heuristic, not a quality score."),
        );
      }

      const synthesis = paragraph.synthesis_diagnostics || {};
      if (synthesis.possible_source_listing && synthesis.editorial_prompt) {
        const quote = document.createElement("blockquote");
        quote.textContent = synthesis.editorial_prompt;
        card.append(quote);
      }
      list.append(card);
    });
    elements.structurePanel.append(list);
  }

  function renderSafeguards(safeguards) {
    elements.safeguardsPanel.replaceChildren();
    const entries = Object.entries(safeguards).filter(([, value]) => typeof value === "boolean");
    const list = createElement("ul", "check-list");
    entries.forEach(([name, passed]) => {
      const item = document.createElement("li");
      item.append(
        createElement("span", `check-icon ${passed ? "" : "is-false"}`, passed ? "✓" : "!"),
        createElement("span", "", readableRole(name)),
      );
      list.append(item);
    });
    elements.safeguardsPanel.append(list);
    if (safeguards.note) {
      elements.safeguardsPanel.append(createElement("p", "intro-copy", safeguards.note));
    }
  }

  function downloadText(content, filename, type = "text/plain;charset=utf-8") {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  function renderReceipt(receipt) {
    elements.receiptPanel.replaceChildren();
    const unknowns = receipt.residual_unknowns || [];
    elements.unknownCount.textContent = String(unknowns.length);

    const summary = createElement("div", "receipt-summary");
    const summaryText = document.createElement("div");
    summaryText.append(
      createElement("span", "badge is-good", `Contract ${receipt.schema_version}`),
      createElement("h3", "", "A reproducible record of this revision"),
      createElement("code", "receipt-id", receipt.receipt_id),
    );
    const download = createElement("button", "text-button receipt-download", "Download JSON");
    download.type = "button";
    download.addEventListener("click", () => {
      downloadText(
        `${JSON.stringify(receipt, null, 2)}\n`,
        "scholarflow-revision-receipt.json",
        "application/json;charset=utf-8",
      );
    });
    summary.append(summaryText, download);
    elements.receiptPanel.append(summary);

    const operationsTitle = createElement("h3", "section-title", "Operations performed");
    const operationList = createElement("div", "insight-list");
    (receipt.operations || []).forEach((operation) => {
      const card = createElement("article", "insight-card");
      const header = document.createElement("header");
      const statusClass = operation.status === "completed" ? "is-good" : "is-warning";
      header.append(
        createElement("h3", "", readableRole(operation.name)),
        createElement("span", `badge ${statusClass}`, operation.status),
      );
      card.append(header, createElement("p", "", operation.detail));
      card.append(createElement("p", "receipt-meta", `Confidence: ${operation.confidence}`));
      operationList.append(card);
    });
    elements.receiptPanel.append(operationsTitle, operationList);

    const unknownTitle = createElement("h3", "section-title", "Questions that remain open");
    const unknownList = createElement("div", "insight-list");
    unknowns.forEach((unknown) => {
      const card = createElement("article", "insight-card");
      const header = document.createElement("header");
      header.append(
        createElement("h3", "", unknown.question),
        createElement("span", "badge is-warning", unknown.severity),
      );
      card.append(header, createElement("p", "", unknown.recommended_action));
      unknownList.append(card);
    });
    elements.receiptPanel.append(unknownTitle, unknownList);

    const limitations = receipt.limitations || [];
    if (limitations.length) {
      const limitationTitle = createElement("h3", "section-title", "Limitations");
      const list = createElement("ul", "limitation-list");
      limitations.forEach((limitation) => {
        list.append(createElement("li", "", limitation));
      });
      elements.receiptPanel.append(limitationTitle, list);
    }
  }

  function renderResult(result) {
    state.lastResult = result;
    elements.refined.value = result.refined_text;
    elements.outputEmpty.hidden = true;
    elements.copyButton.disabled = false;
    elements.downloadButton.disabled = false;
    elements.providerLabel.textContent = result.used_llm
      ? `Enhanced with ${result.provider}`
      : "Deterministic local editor";
    refreshCounts();
    renderStats(result.stats);
    renderNotices(result.notices || []);
    renderSuggestions(result.suggestions || []);
    renderStructure(result.literature_review || {});
    renderSafeguards(result.safeguards || {});
    renderReceipt(result.receipt || {});
    elements.results.hidden = false;
    elements.results.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function errorMessage(payload, status) {
    if (typeof payload?.detail === "string") return payload.detail;
    if (Array.isArray(payload?.detail)) {
      return payload.detail.map((item) => item.msg || "Invalid input").join("; ");
    }
    return `The editor returned an error (${status}).`;
  }

  async function refine() {
    const text = elements.source.value;
    if (!text.trim()) {
      showToast("Add an academic passage before refining.", true);
      elements.source.focus();
      return;
    }

    setLoading(true);
    try {
      const response = await fetch("/editor/rewrite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          profile: state.profile,
          use_llm: elements.useLlm.checked,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(errorMessage(payload, response.status));
      renderResult(payload);
    } catch (error) {
      showToast(error.message || "The passage could not be refined.", true);
    } finally {
      setLoading(false);
    }
  }

  async function loadCapabilities() {
    try {
      const response = await fetch("/editor/capabilities");
      if (!response.ok) throw new Error("Capability request failed");
      state.capabilities = await response.json();
      elements.engineStatus.classList.add("is-ready");
      elements.engineStatus.lastChild.textContent = " Engine ready";
      elements.useLlm.disabled = !state.capabilities.llm_available;
      elements.aiCaption.textContent = state.capabilities.llm_available
        ? `${state.capabilities.llm_provider} available`
        : "Provider not configured";
      if (state.capabilities.max_text_chars) {
        elements.source.maxLength = state.capabilities.max_text_chars;
      }
    } catch {
      elements.engineStatus.lastChild.textContent = " Engine unavailable";
      elements.aiCaption.textContent = "Provider status unavailable";
      elements.useLlm.disabled = true;
    }
  }

  async function copyOutput() {
    if (!elements.refined.value) return;
    try {
      await navigator.clipboard.writeText(elements.refined.value);
      showToast("Refined passage copied.");
    } catch {
      elements.refined.select();
      document.execCommand("copy");
      showToast("Refined passage copied.");
    }
  }

  function downloadOutput() {
    if (!elements.refined.value) return;
    downloadText(elements.refined.value, "scholarflow-refined.txt");
  }

  document.querySelectorAll(".mode-button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".mode-button").forEach((item) => item.classList.remove("is-active"));
      button.classList.add("is-active");
      state.profile = button.dataset.profile;
    });
  });

  document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab-button").forEach((item) => {
        const active = item === button;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", String(active));
      });
      document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.hidden = panel.id !== `${button.dataset.tab}-panel`;
      });
    });
  });

  elements.source.addEventListener("input", refreshCounts);
  elements.refined.addEventListener("input", () => {
    refreshCounts();
    if (state.lastResult && elements.refined.value !== state.lastResult.refined_text) {
      elements.providerLabel.textContent = "Edited manually · safeguards need recheck";
    }
  });
  elements.refineButton.addEventListener("click", refine);
  elements.copyButton.addEventListener("click", copyOutput);
  elements.downloadButton.addEventListener("click", downloadOutput);

  document.querySelector("#sample-button").addEventListener("click", () => {
    elements.source.value = sampleText;
    refreshCounts();
    elements.source.focus();
  });

  document.querySelector("#clear-button").addEventListener("click", () => {
    elements.source.value = "";
    elements.refined.value = "";
    elements.outputEmpty.hidden = false;
    elements.results.hidden = true;
    elements.copyButton.disabled = true;
    elements.downloadButton.disabled = true;
    refreshCounts();
    elements.source.focus();
  });

  elements.fileInput.addEventListener("change", async () => {
    const [file] = elements.fileInput.files;
    if (!file) return;
    try {
      const text = await file.text();
      const limit = state.capabilities?.max_text_chars || 500000;
      if (text.length > limit) throw new Error(`The file exceeds the ${limit.toLocaleString()} character limit.`);
      elements.source.value = text;
      refreshCounts();
      showToast(`${file.name} loaded.`);
    } catch (error) {
      showToast(error.message || "The file could not be read.", true);
    } finally {
      elements.fileInput.value = "";
    }
  });

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      refine();
    }
  });

  refreshCounts();
  loadCapabilities();
})();
