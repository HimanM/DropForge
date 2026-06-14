# -*- mode: python ; coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

SELF_PATH = str(Path(".").resolve())
if SELF_PATH not in sys.path:
    sys.path.insert(0, SELF_PATH)

from PyInstaller.building.api import EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_data_files

from core.constants import DEFAULT_LANG, WORKING_DIR


app_name = "tdminer"
upx = False
optimize = None

datas = collect_data_files("textual")
for lang_filepath in WORKING_DIR.joinpath("lang").glob("*.json"):
    if lang_filepath.stem != DEFAULT_LANG:
        datas.append((str(lang_filepath), "lang"))

hiddenimports = [
    "tui.cli",
    "textual.drivers.headless_driver",
    "textual.drivers.linux_driver",
    "textual.drivers.linux_inline_driver",
    "textual.widgets._button",
    "textual.widgets._data_table",
    "textual.widgets._footer",
    "textual.widgets._header",
    "textual.widgets._input",
    "textual.widgets._label",
    "textual.widgets._log",
    "textual.widgets._progress_bar",
    "textual.widgets._static",
    "textual.widgets._tab_pane",
    "textual.widgets._tabbed_content",
]

a = Analysis(
    ["tdminer.py"],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "IPython",
        "PIL",
        "PIL.Image",
        "PIL.ImageTk",
        "_tkinter",
        "gi",
        "jedi",
        "matplotlib",
        "nbformat",
        "numpy",
        "parso",
        "py",
        "pystray",
        "pytest",
        "tkinter",
        "zmq",
    ],
)

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.datas,
    a.binaries,
    upx=upx,
    debug=False,
    name=app_name,
    console=True,
    optimize=optimize,
)
