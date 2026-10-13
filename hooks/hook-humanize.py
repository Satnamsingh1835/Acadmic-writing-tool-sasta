# Override hook for the name `humanize`.
#
# _pyinstaller_hooks_contrib ships `hook-humanize.py` for the third-party
# PyPI package "humanize" (fuzzy time/size formatting). This repository
# instead defines its own top-level `humanize` module (the academic
# humanizer). When Analysis encounters it, the community hook runs
# `copy_metadata("humanize")`, cannot find any `humanize-*.dist-info`
# distribution, and aborts the build with ImportErrorWhenRunningHook.
#
# Hooks placed in this directory take precedence over hooks-contrib, so
# this no-op hook disables the mismatched community hook. The repository's
# `humanize` module is a plain pure-Python module and needs no hook.
