# Workflow entrypoints

The canonical interface is `python -m agent.cli`. Each file in this directory
is also directly executable and injects its matching subcommand, for example:

```bash
python workflows/source_analysis.py paper.txt --id S1
python workflows/literature_matrix.py literature/*.txt --format csv
python workflows/paragraph_audit.py --paragraph "Your paragraph here"
python workflows/human_edit.py drafts/review.txt --profile standard
```

Run any wrapper with `--help` for its command-specific arguments.
