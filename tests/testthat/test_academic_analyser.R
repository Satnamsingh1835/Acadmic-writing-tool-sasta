source("R/academic_analyser.R")

testthat::test_that("analyser detects literature-review signals", {
  a <- AcademicAnalyzer()
  x <- "Jodhka (2004) examines caste and land relations. This suggests that land access is socially structured. However, Gupta (2000) identifies regional variation."
  r <- a$analyse(x)
  testthat::expect_equal(r$sentence_count, 3)
  testthat::expect_gte(r$citation_count, 2)
  testthat::expect_true(r$literature_review_signals$source_or_evidence)
  testthat::expect_true(r$literature_review_signals$interpretation)
  testthat::expect_true(r$literature_review_signals$comparison_or_synthesis)
})

testthat::test_that("analyser flags long sentences and formulaic language", {
  a <- AcademicAnalyzer(long_sentence_words=10)
  x <- "It is important to note that caste plays a crucial role in shaping access to land and this relationship changes across regions. This sentence is short."
  r <- a$analyse(x)
  testthat::expect_true(length(r$formulaic_phrases) >= 1)
  testthat::expect_true(length(r$long_sentences) >= 1)
})

testthat::test_that("analyser identifies possible uncited source claims", {
  a <- AcademicAnalyzer()
  r <- a$analyse("According to the survey, land access remains unequal.")
  testthat::expect_equal(r$citation_diagnostics$possible_uncited_source_claims, 1)
})

testthat::test_that("analyser rejects invalid input", {
  a <- AcademicAnalyzer()
  testthat::expect_error(a$analyse(123), "text must be a single character string")
  testthat::expect_error(AcademicAnalyzer(0), "long_sentence_words must be positive")
})
