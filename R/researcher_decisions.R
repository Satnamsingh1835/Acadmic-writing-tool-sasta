# Researcher-controlled decision helpers for review suggestions.

academic_decision <- function(suggestion, decision = "pending",
                              revised_text = NULL, note = NULL) {
  stopifnot(length(decision) == 1L)
  valid <- c("accept", "modify", "reject", "pending")

  if (!decision %in% valid) {
    stop("decision must be one of: ", paste(valid, collapse = ", "))
  }

  if (decision == "modify" &&
      (is.null(revised_text) || !nzchar(trimws(revised_text)))) {
    stop("A modified decision requires revised_text.")
  }

  list(
    suggestion_id = suggestion$suggestion_id,
    decision = decision,
    revised_text = revised_text,
    researcher_note = note
  )
}

academic_apply_decision <- function(original, suggestion, decision) {
  stopifnot(length(original) == 1L)

  if (!identical(decision$suggestion_id, suggestion$suggestion_id)) {
    stop("Decision does not match the suggestion.")
  }

  if (decision$decision == "accept") {
    return(suggestion$suggested_revision)
  }

  if (decision$decision == "modify") {
    return(decision$revised_text)
  }

  original
}
