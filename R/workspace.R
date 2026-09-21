#' Create the standard workspace for an academic writing project.
#'
#' @param path Project directory.
#' @return Invisibly returns the created path.
academic_workspace_create <- function(path = ".") {
  stopifnot(length(path) == 1L, nzchar(path))

  dirs <- file.path(
    path,
    c(
      "drafts",
      "literature",
      "notes",
      "citations",
      "feedback"
    )
  )

  for (dir in dirs) {
    if (!dir.exists(dir)) {
      dir.create(dir, recursive = TRUE, showWarnings = FALSE)
    }
  }

  invisible(normalizePath(path, winslash = "/", mustWork = FALSE))
}

#' List the standard academic-writing workspace directories.
#'
#' @param path Project directory.
#' @return A character vector of workspace directories.
academic_workspace_dirs <- function(path = ".") {
  file.path(
    path,
    c("drafts", "literature", "notes", "citations", "feedback")
  )
}
