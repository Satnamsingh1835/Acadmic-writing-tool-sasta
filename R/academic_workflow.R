# Simple researcher-facing helpers for the hybrid academic writing assistant.

academic_assistant_health <- function(base_url = "http://127.0.0.1:8000") {
  if (!requireNamespace("httr2", quietly = TRUE)) stop("Install the httr2 package first.")
  httr2::request(paste0(base_url, "/health")) |>
    httr2::req_perform() |>
    httr2::resp_body_json()
}

academic_print_review <- function(review_response) {
  cat("\n=== Academic Literature Review Assistant ===\n")
  if (!is.null(review_response$refined_text)) {
    cat("\n--- Refined text (language-level only) ---\n")
    cat(review_response$refined_text, "\n")
  }
  suggestions <- review_response$suggestions
  cat("\n--- Suggestions ---\n")
  if (length(suggestions) == 0L) {
    cat("No sentence-level suggestions returned.\n")
  } else {
    for (i in seq_along(suggestions)) {
      s <- suggestions[[i]]
      cat("\n[", i, "] ", s$category, " | ", s$suggestion_id, "\n", sep = "")
      cat("Original: ", s$original, "\n", sep = "")
      cat("Suggestion: ", s$suggested_revision, "\n", sep = "")
      cat("Why: ", s$why, "\n", sep = "")
      cat("Confidence: ", s$confidence, "\n", sep = "")
      cat("Decision: ", s$decision, "\n", sep = "")
    }
  }
  cat("\n--- Researcher safeguards ---\n")
  print(review_response$safeguards)
  cat("\n--- Literature-review diagnostics ---\n")
  print(review_response$literature_review)
  invisible(review_response)
}

academic_save_refined <- function(review_response, path) {
  if (is.null(review_response$refined_text)) stop("This review response does not contain refined_text.")
  stopifnot(length(path) == 1L, nzchar(path))
  parent <- dirname(path)
  if (!dir.exists(parent) && !identical(parent, ".")) dir.create(parent, recursive = TRUE, showWarnings = FALSE)
  writeLines(review_response$refined_text, con = path, useBytes = TRUE)
  invisible(normalizePath(path, winslash = "/", mustWork = FALSE))
}