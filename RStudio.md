# RStudio workflow

Start the API from the repository root:

```bash
python -m uvicorn api:app --reload
```

In RStudio:

```r
source("R/academic_review.R")
result <- academic_review("Jodhka (2004) examines caste and land relations. This remains underexplored.")
cat(result$refined_text)
```

Use `academic_review_file()` for UTF-8 `.txt` drafts. The API has deterministic tools for academic improvement and literature-review structure; optional LLM tools require `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`.
