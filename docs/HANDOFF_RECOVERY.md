# ScholarFlow handoff and recovery

This file describes the intended review workflow; it does not assert access to the user's Windows PC.

1. Use a dedicated branch and preserve the workspace. Check `git status`, `git diff`, and recent commits before cleanup.
2. Do not run `git reset --hard` or `git clean` while user changes may exist.
3. Keep backups, local SQLite databases, Zotero files, tokens, private PDFs and REA browser artifacts outside Git.
4. The local coding agent writes repo files, scripts and tests; it does not remotely operate the user's Windows PC.
5. For tasks requiring Windows, provide precise PowerShell commands and review only non-sensitive output.
6. Keep pull requests unmerged until code and CI are reviewed.
7. Earlier local reports from a closed session are not proof of remote files or tests unless the matching commit is available in GitHub.
