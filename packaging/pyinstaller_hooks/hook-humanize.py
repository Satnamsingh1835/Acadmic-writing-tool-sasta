"""Override the third-party hook for this repository's local humanize.py module.

The project uses a top-level ``humanize.py`` module, not the PyPI distribution
named ``humanize``. The contrib hook attempts to copy distribution metadata for
an unrelated package and fails because that distribution is not installed.
The project module is included by normal import analysis, so no metadata is needed.
"""

datas = []
hiddenimports = []
