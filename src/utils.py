from pathlib import Path
import os

from .config import Config

CONFIG = Config()


def find_labellable_folders(root):
    """Return every directory that contains at least one .tif file."""
    folders = []
    for subject in sorted(root.iterdir()):
        if not subject.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(subject):
            dirnames.sort()
            if any(fname.lower().endswith(".tif") for fname in filenames):
                folders.append(Path(dirpath))
                dirnames[:] = []  # stop descent
    return sorted(folders)


def sorted_tifs(folder):
    """Return .tif filepaths sorted by 3-digit frame suffix, else alphabetically."""
    matches = []
    for fn in folder.iterdir():
        m = CONFIG.FRAME_REGEX.search(fn.name)
        if m:
            matches.append((int(m.group(1)), fn))
    if not matches:
        matches = [(0, fp) for fp in folder.glob("*.tif")]
    return [fp for _, fp in sorted(matches)]
