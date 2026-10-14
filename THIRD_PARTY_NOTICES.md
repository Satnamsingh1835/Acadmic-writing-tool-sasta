# Third-party notices

ScholarFlow itself is distributed under the licence in `LICENSE` (if present)
or as stated in `README.md`. This file records the third-party components that
the **packaged desktop application** carries, together with the licence that
applies to each and the obligations that come with it. The list covers the
diagnostics work; the research-library dependencies are recorded in the same
style further down.

## Bundled in the packaged application

| Component | Version | Licence | Why it is bundled | Redistribution obligation |
|---|---|---|---|---|
| `pyspellchecker` | 0.8.2 | MIT | The offline spelling dictionary and the one-edit candidate search | Ship the MIT copyright notice and permission text. The full text is in `packaging/third_party/pyspellchecker-LICENSE.txt` and is copied into the built application's `licenses/` folder by `ScholarFlowDesktop.spec`. |
| `pyspellchecker` English dictionary (`spellchecker/resources/en.json.gz`) | ships with 0.8.2 | MIT, as part of the package | Word frequencies for spelling and candidate ranking | Same notice as above; no separate attribution is required by the package. The dictionary is a frequency list built by the package's author, not a database with its own licence terms. |
| `pywebview` | 6.2.1 | BSD-3-Clause | The desktop window and its embedded WebView | Ship the BSD-3-Clause notice. |
| `fastapi`, `starlette`, `uvicorn`, `pydantic`, `httpx` | pinned in `requirements.txt` | MIT (FastAPI, Starlette, Uvicorn, HTTPX), MIT (Pydantic) | The local API server the window talks to | Ship the notices. |

## Deliberate non-bundling decisions

| Component | Licence | Decision |
|---|---|---|
| LanguageTool (a local server) | LGPL-2.1 | **Not bundled.** It needs a Java runtime and a second process; LGPL would add relinking obligations to a frozen PyInstaller build. Recorded as an optional, user-installed backend only. No paid or cloud grammar service is used anywhere. |
| Harper | Apache-2.0 | **Not bundled.** It needs a Rust toolchain to build; tracked as a future option. |
| Vale | MIT | **Not bundled.** Style rules rather than grammar. |
| Cloud grammar or LLM APIs (Grammarly, LanguageTool cloud, OpenAI, Anthropic, …) | proprietary | **Never required and off by default.** No document text is sent to any of them by diagnostics, at any time, with or without a network connection. |

## The personal dictionary

The words a researcher adds in the workspace are stored as plain JSON in the
user's data directory (`writing-dictionary.json`). They are their own content,
not third-party material, and are never uploaded.

## Verifying what a build actually contains

The packaged smoke gate (`desktop_app.py --smoke-test`) checks that the frozen
application can load the bundled dictionary, and the spec collects the notice
files above, so a build that lost either one fails its own gate instead of
quietly shipping without them.
