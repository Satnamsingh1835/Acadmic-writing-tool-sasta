from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path.cwd()
webview_datas, webview_binaries, webview_hiddenimports = collect_all("webview")
hiddenimports = webview_hiddenimports + collect_submodules("uvicorn") + collect_submodules("fastapi") + collect_submodules("starlette") + ["api", "academic_engine", "editor_service", "research_library.store", "research_library.discovery", "research_library.documents", "research_library.importers", "research_library.zotero"]
a = Analysis(["desktop_app.py"], pathex=[str(root)], binaries=webview_binaries, datas=webview_datas + [(str(root / "web"), "web")], hiddenimports=hiddenimports, hookspath=[str(root / "packaging" / "pyinstaller_hooks")], hooksconfig={}, runtime_hooks=[], excludes=["PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ScholarFlow", debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name="ScholarFlow")
