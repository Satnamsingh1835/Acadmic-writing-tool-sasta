#' Review academic literature-review text through the local API
#'
#' @param text Character vector containing the draft.
#' @param profile One of "conservative", "standard", or "polish".
#' @param base_url Local API URL.
#' @return Parsed API response.
academic_review <- function(text, profile = "standard",
                            base_url = "http://127.0.0.1:8000") {
  stopifnot(length(text) == 1L, nzchar(trimws(text)))
  if (!requireNamespace("httr2", quietly = TRUE)) {
    stop("Install the httr2 package first.")
  }

  httr2::request(paste0(base_url, "/review")) |>
    httr2::req_method("POST") |>
    httr2::req_body_json(list(
      text = text,
      profile = profile,
      include_refined_text = TRUE
    )) |>
    httr2::req_perform() |>
    httr2::resp_body_json()
}

#' Review a UTF-8 text file through the local API
#'
#' @param path Path to a UTF-8 .txt file.
#' @param profile One of "conservative", "standard", or "polish".
#' @param base_url Local API URL.
#' @return Parsed API response.
academic_review_file <- function(path, profile = "standard",
                                 base_url = "http://127.0.0.1:8000") {
  stopifnot(file.exists(path), grepl("\\.[Tt][Xx][Tt]$", path))
  if (!requireNamespace("httr2", quietly = TRUE)) {
    stop("Install the httr2 package first.")
  }

  httr2::request(paste0(base_url, "/review/file")) |>
    httr2::req_method("POST") |>
    httr2::req_body_multipart(
      file = httr2::upload_file(path),
      profile = profile,
      include_refined_text = "true"
    ) |>
    httr2::req_perform() |>
    httr2::resp_body_json()
}
