# Test entry point for the standalone R helper layer.
# The repository is not an R package, so tests source the R modules explicitly.

source("R/academic_review.R")
source("R/researcher_decisions.R")
source("R/workspace.R")
source("R/academic_workflow.R")

testthat::test_dir("tests/testthat")