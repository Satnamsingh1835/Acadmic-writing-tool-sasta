testthat::test_that("academic workspace creates standard directories", {
  path <- tempfile("academic-workspace-")
  dir.create(path)

  academic_workspace_create(path)

  expected <- file.path(
    path,
    c("drafts", "literature", "notes", "citations", "feedback")
  )

  testthat::expect_true(all(dir.exists(expected)))
})

testthat::test_that("workspace directory listing is deterministic", {
  path <- tempfile("academic-workspace-")

  expected <- file.path(
    path,
    c("drafts", "literature", "notes", "citations", "feedback")
  )

  testthat::expect_identical(academic_workspace_dirs(path), expected)
})
