"""Utility per aprire dialoghi file/cartella Tkinter dal main thread."""
from __future__ import annotations

from pathlib import Path


def _build_root():
    try:
        import tkinter as tk
    except Exception:
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root


def ask_open_filename(
    *,
    initialdir: str | Path,
    title: str,
    filetypes: list[tuple[str, str]] | tuple[tuple[str, str], ...],
) -> str:
    """Apre un file picker Tkinter sul thread principale."""
    root = _build_root()
    if root is None:
        return ""

    from tkinter import filedialog

    try:
        selected_file = filedialog.askopenfilename(
            initialdir=str(initialdir),
            title=title,
            filetypes=filetypes,
        )
    finally:
        root.destroy()
    return selected_file or ""


def ask_directory(
    *,
    initialdir: str | Path,
    title: str,
    mustexist: bool = False,
) -> str:
    """Apre un directory picker Tkinter sul thread principale."""
    root = _build_root()
    if root is None:
        return ""

    from tkinter import filedialog

    try:
        selected_dir = filedialog.askdirectory(
            initialdir=str(initialdir),
            title=title,
            mustexist=mustexist,
        )
    finally:
        root.destroy()
    return selected_dir or ""
