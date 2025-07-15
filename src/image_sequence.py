from PIL import Image

from .utils import *


class ImageSequence:
    """Treat a folder (or volume) as a sequence of frames."""

    def __init__(self, folder):
        self._items = self._collect(folder)

    def __len__(self):
        return len(self._items)

    def get(self, idx):
        return self._items[idx]

    # ------------------------------------------------------------------ #
    @staticmethod
    def _collect(folder):
        frames = []
        for fp in sorted_tifs(folder):
            try:
                with Image.open(fp) as im:
                    n_pages = getattr(im, "n_frames", 1)
            except Exception:
                n_pages = 1
            if n_pages > 1:
                frames += [(fp, i) for i in range(n_pages)]
            else:
                frames.append((fp, 0))
        return frames
