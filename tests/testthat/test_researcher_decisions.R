testthat::test_that("accept decision applies suggestion", {
  suggestion <- list(
    suggestion_id = "1",
    suggested_revision = "A clearer sentence."
  )
  decision <- academic_decision(suggestion, "accept")

  testthat::expect_identical(
    academic_apply_decision("Original.", suggestion, decision),
    "A clearer sentence."
  )
})

testthat::test_that("reject decision preserves original", {
  suggestion <- list(
    suggestion_id = "1",
    suggested_revision = "A clearer sentence."
  )
  decision <- academic_decision(suggestion, "reject")

  testthat::expect_identical(
    academic_apply_decision("Original.", suggestion, decision),
    "Original."
  )
})

testthat::test_that("modify decision requires revised text", {
  suggestion <- list(
    suggestion_id = "1",
    suggested_revision = "A clearer sentence."
  )

  testthat::expect_error(
    academic_decision(suggestion, "modify"),
    "requires revised_text"
  )
})
