import os


class FolderNavigator:
    """Keeps track of the set of folders and which one is active."""

    def __init__(self, folders, root_dir):
        self.folders = folders
        self.root_dir = root_dir
        self.idx = 0

    # Properties ------------------------------------------------------- #
    @property
    def current_abs(self):
        return self.folders[self.idx]

    @property
    def current_rel(self) -> str:
        return os.path.join(
            self.root_dir.name, os.path.relpath(self.current_abs, self.root_dir)
        )

    # Navigation ------------------------------------------------------- #
    def next(self) -> bool:
        if self.idx < len(self.folders) - 1:
            self.idx += 1
            return True
        return False

    def prev(self) -> bool:
        if self.idx > 0:
            self.idx -= 1
            return True
        return False

    def jump_to(self, index: int):
        if 0 <= index < len(self.folders):
            self.idx = index
