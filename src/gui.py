"""
tissue_annotator.py

Tissue annotation GUI.

Architecture
------------
- `Config`: centralised constants.
- `ImageSequence`: wrapper around microscopy frames.
- `MetadataExtractor`: static helpers for OME-TIFF meta-data.
- `AnnotationManager`: handles CSV persistence of labels.
- `FolderNavigator`: discovers and iterates labellable folders.
- `TissueAnnotatorApp`: Tk application composing the above.
"""

import os
import tkinter as tk
from pathlib import Path

import numpy as np
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox, ttk

from .config import Config
from .utils import *
from .image_sequence import ImageSequence
from .metadata_extractor import MetadataExtractor
from .annotation_manager import AnnotationManager
from .folder_navigator import FolderNavigator

CONFIG = Config()


class TissueAnnotatorGUI(tk.Tk):
    """Tk GUI that composes domain components."""

    def __init__(self):
        super().__init__()
        self.title("Tissue Type Annotator")

        # --- root directory selection ---
        root_path = filedialog.askdirectory(title="Select root directory")
        if not root_path:
            self.destroy()
            return
        self.root_dir = Path(root_path)

        folders = find_labellable_folders(self.root_dir)
        if not folders:
            messagebox.showerror("Error", "No .tif folders found under root.")
            self.destroy()
            return

        self.nav = FolderNavigator(folders, self.root_dir)
        self.annotations = AnnotationManager()
        self._metadata_cache = {}

        # Tk variables -------------------------------------------------- #
        self.scale_mode = tk.StringVar(value="default")
        self.image_idx = tk.IntVar(value=0)

        # dynamic check-button vars
        self.var_tissue = {t: tk.IntVar() for t in CONFIG.TISSUE_TYPES}
        self.var_clinical_master = tk.BooleanVar()
        self.var_clinical = {c: tk.IntVar() for c in CONFIG.CLINICAL_CLASSIFICATION}
        self.var_other = {o: tk.IntVar() for o in CONFIG.OTHER_ATTRIBUTES}

        # Build UI ------------------------------------------------------ #
        self._build_ui()
        self._load_folder()

    # ------------------------------------------------------------------ #
    # UI construction

    # ------------------------------------------------------------------ #
    # Fit main window to available screen height                         #
    # ------------------------------------------------------------------ #
    def _fit_to_screen(self):
        scr_h = self.winfo_screenheight()
        scr_w = self.winfo_screenwidth()
        win_w = self.winfo_width()
        win_h = self.winfo_height()
        max_h = scr_h - 80  # 40 px margin top/bottom
        max_w = scr_w - 80
        if win_h > max_h or win_w > max_w:
            new_w = min(win_w, max_w)
            new_h = min(win_h, max_h)
            self.geometry(f"{new_w}x{new_h}")

    def _build_ui(self):
        self._build_info_panel()
        self._build_image_panel()
        self._build_annotation_panel()
        self._build_control_panel()
        self.update_idletasks()
        self._fit_to_screen()

    def _build_info_panel(self):
        info = ttk.Frame(self)
        info.pack(fill="x", padx=10, pady=5)

        self.lbl_root = ttk.Label(info)
        self.lbl_root.grid(row=0, column=0, sticky="w")
        self.lbl_subject = ttk.Label(info)
        self.lbl_subject.grid(row=1, column=0, sticky="w")
        self.lbl_site = ttk.Label(info)
        self.lbl_site.grid(row=2, column=0, sticky="w")
        self.lbl_frame = ttk.Label(info)
        self.lbl_frame.grid(row=3, column=0, sticky="w")
        # full‑path label (wrap long paths)
        self.lbl_path = ttk.Label(info, wraplength=800)
        self.lbl_path.grid(row=4, column=0, sticky="w")

        # clipboard button
        ttk.Button(info, text="Copy path 📋", command=self._copy_path).grid(
            row=0, column=1, rowspan=2, padx=10
        )

        # folder‑jump combobox (below info frame)
        self.combo_folders = ttk.Combobox(
            self,
            state="readonly",
            width=100,
            values=[str(p.relative_to(self.root_dir.parent)) for p in self.nav.folders],
        )
        self.combo_folders.bind("<<ComboboxSelected>>", self._on_jump_folder)
        self.combo_folders.pack(pady=5, anchor="w", fill="x")
        # highlight the current folder in the list
        self.combo_folders.current(self.nav.idx)

    # ------------------------------------------------------------------ #
    # 2.  IMAGE PANEL (viewer + metadata + scaling)
    # ------------------------------------------------------------------ #
    def _build_image_panel(self):
        panel = ttk.Frame(self)
        panel.pack(fill="both", expand=True, padx=10, pady=5)

        # ------- Metadata ----------
        meta_frame = ttk.LabelFrame(panel, text="Metadata")
        meta_frame.grid(row=0, column=0, sticky="n", padx=(0, 5))
        self.txt_metadata = tk.Text(
            meta_frame, width=40, height=25, state="disabled", wrap="word"
        )
        self.txt_metadata.pack(fill="both", expand=True)

        # ------- Image viewer -------
        viewer = ttk.Frame(panel)
        viewer.grid_columnconfigure(1, weight=1)
        viewer.grid_rowconfigure(0, weight=1)
        viewer.grid(row=0, column=1)
        panel.grid_columnconfigure(1, weight=1)

        self.btn_prev = ttk.Button(viewer, text="◀ Prev", command=self._prev_image)
        self.btn_prev.grid(row=0, column=0)

        self.lbl_img = ttk.Label(viewer, anchor="center")
        self.lbl_img.grid(row=0, column=1)
        self.lbl_img.bind("<MouseWheel>", self._on_mousewheel)

        self.btn_next = ttk.Button(viewer, text="Next ▶", command=self._next_image)
        self.btn_next.grid(row=0, column=2)

        # ------- Colour scaling -----
        color = ttk.LabelFrame(panel, text="Color Scaling")
        color.grid(row=0, column=2, sticky="e", padx=(5, 0))
        for i, (text, val) in enumerate((("Default", "default"), ("Log", "log"))):
            ttk.Radiobutton(
                color,
                text=text,
                variable=self.scale_mode,
                value=val,
                command=self._show_image,
            ).grid(row=i, column=0, sticky="w", padx=5)

        # Slider for quick navigation (added below panel for full width)
        self.scale = ttk.Scale(self, orient="horizontal", command=self._on_slider)
        self.scale.pack(fill="x", padx=10, pady=5)

    # ------------------------------------------------------------------ #
    # 3.  ANNOTATION PANEL (tissue / clinical / other / comments)
    # ------------------------------------------------------------------ #
    def _build_annotation_panel(self):
        wrapper = ttk.Frame(self)
        wrapper.pack(fill="x", padx=10, pady=5)

        # Tissue types
        tissue = ttk.LabelFrame(wrapper, text="Tissue Types")
        tissue.pack(side="left", fill="both", expand=True, padx=(0, 5))
        for i, t in enumerate(CONFIG.TISSUE_TYPES):
            ttk.Checkbutton(tissue, text=t, variable=self.var_tissue[t]).grid(
                row=i // 5, column=i % 5, sticky="w", padx=5
            )

        # Clinical classification
        clinical = ttk.LabelFrame(wrapper, text="Clinical Classification")
        clinical.pack(side="left", padx=(5, 0))
        ttk.Checkbutton(
            clinical,
            text="Enable clinical classification",
            variable=self.var_clinical_master,
            command=self._toggle_clinical,
        ).grid(row=0, column=0, columnspan=4, sticky="w")
        self._clinical_cbs = []
        for i, c in enumerate(CONFIG.CLINICAL_CLASSIFICATION):
            cb = ttk.Checkbutton(clinical, text=c, variable=self.var_clinical[c])
            cb.grid(row=1, column=i, sticky="w", padx=5)
            self._clinical_cbs.append(cb)

        # Other attributes
        other = ttk.LabelFrame(self, text="Other Attributes")
        other.pack(fill="x", padx=10, pady=5)
        for i, o in enumerate(CONFIG.OTHER_ATTRIBUTES):
            ttk.Checkbutton(other, text=o, variable=self.var_other[o]).grid(
                row=0, column=i, sticky="w", padx=5
            )

        # Comments
        comment = ttk.LabelFrame(self, text="Comments")
        comment.pack(fill="x", padx=10, pady=5)
        self.txt_comment = tk.Text(comment, height=2)
        self.txt_comment.pack(fill="x")

    # ------------------------------------------------------------------ #
    # 4.  CONTROL PANEL (save / navigation)
    # ------------------------------------------------------------------ #

    def _build_control_panel(self):
        ctrl = ttk.Frame(self)
        ctrl.pack(pady=10)

        ttk.Button(ctrl, text="Skip Folder", command=self._skip_folder).pack(
            side="left", padx=5
        )
        ttk.Button(ctrl, text="Next Folder →", command=self._next_folder).pack(
            side="left", padx=5
        )

    # ------------------------------------------------------------------ #
    #            STATE — CLINICAL CLASSIFICATION CHECK-BOXES
    # ------------------------------------------------------------------ #
    def _toggle_clinical(self):
        state = "normal" if self.var_clinical_master.get() else "disabled"
        for cb in self._clinical_cbs:
            cb.config(state=state)

    # ------------------------------------------------------------------ #
    #             IMAGE — NAVIGATION & DISPLAY HELPERS
    # ------------------------------------------------------------------ #
    def _update_slider(self):
        self.scale.config(to=max(len(self.images) - 1, 0))
        self.scale.set(self.image_idx)

    def _on_slider(self, val):
        idx = int(float(val))
        if idx != self.image_idx:
            self.image_idx = idx
            self._show_image()

    def _on_mousewheel(self, event):
        delta = -1 if event.delta > 0 else 1  # Windows / macOS share sign
        self._change_image(delta)

    def _prev_image(self):
        self._change_image(-1)

    def _next_image(self):
        self._change_image(1)

    def _change_image(self, step: int):
        new_idx = self.image_idx + step
        if 0 <= new_idx < len(self.images):
            self.image_idx = new_idx
            self._update_slider()
            self._show_image()

    def _show_image(self):
        if not self.images:
            return
        fp, page = self.images.get(self.image_idx)
        img = Image.open(fp)
        if page:
            try:
                img.seek(page)
            except EOFError:
                pass

        if self.scale_mode.get() == "log":  # optional log intensity
            arr = np.array(img, dtype=np.float32)
            arr[arr < 0] = 0  # avoid NaNs
            mx = arr.max()
            if mx > 0:
                norm = np.log1p(arr) / np.log1p(mx)
            else:
                norm = arr  # all-zero fallback
            img = Image.fromarray((norm.clip(0, 1) * 255).astype(np.uint8))

        img.thumbnail(CONFIG.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        self._tk_img = ImageTk.PhotoImage(img)
        self.lbl_img.config(image=self._tk_img)

        # buttons enabled/disabled
        self.btn_prev.state(["!disabled"] if self.image_idx else ["disabled"])
        last = len(self.images) - 1
        self.btn_next.state(["!disabled"] if self.image_idx < last else ["disabled"])

        # info labels
        frame_txt = f"Frame {self.image_idx+1}/{last+1}"
        self.lbl_frame.config(text=frame_txt)
        self.lbl_path.config(text=str(fp))

        # metadata (cached)
        md = self._metadata_cache.get(fp)
        if md is None:
            md = MetadataExtractor.extract(fp)
            self._metadata_cache[fp] = md
        self.txt_metadata.config(state="normal")
        self.txt_metadata.delete("1.0", tk.END)
        for k, v in md.items():
            self.txt_metadata.insert(tk.END, f"{k}: {v}\n")
        self.txt_metadata.config(state="disabled")
        # keep window within the visible screen even when image size pushes it
        self._fit_to_screen()

    # ------------------------------------------------------------------ #
    #                        FOLDER NAVIGATION
    # ------------------------------------------------------------------ #
    def _on_jump_folder(self, event):
        new_idx = self.combo_folders.current()
        if new_idx != self.nav.idx:
            self._nav_to(new_idx, save_current=False)

    def _skip_folder(self):
        self._nav_to(self.nav.idx + 1, save_current=False)

    def _next_folder(self):
        self._save_current_annotations()
        self._nav_to(self.nav.idx + 1, save_current=True)

    def _nav_to(self, idx: int, save_current: bool):
        if idx >= len(self.nav.folders):
            messagebox.showinfo("Finished", "All folders processed.")
            self.destroy()
            return
        self.nav.jump_to(idx)
        self._load_folder()

    # ------------------------------------------------------------------ #
    #                ANNOTATION CSV — LOAD / SAVE
    # ------------------------------------------------------------------ #
    def _gather_annotation_row(self) -> dict:
        row: dict[str, str | int] = {
            "root": self.root_dir.name,
            "folder": os.path.relpath(self.nav.current_abs, self.root_dir),
        }
        row.update({t: var.get() for t, var in self.var_tissue.items()})
        row.update(
            {
                c: (
                    self.var_clinical[c].get() if self.var_clinical_master.get() else ""
                )
                for c in CONFIG.CLINICAL_CLASSIFICATION
            }
        )
        row.update({o: var.get() for o, var in self.var_other.items()})
        comment = self.txt_comment.get("1.0", "end").strip()
        row[CONFIG.COMMENT_COLUMN] = comment
        return row

    def _save_current_annotations(self):
        key = self.nav.current_rel
        self.annotations.update(key, self._gather_annotation_row())

    # ------------------------------------------------------------------ #
    #                       INITIAL FOLDER LOAD
    # ------------------------------------------------------------------ #
    def _load_folder(self):
        # reset scroll variables
        self.image_idx = 0
        self.images = ImageSequence(self.nav.current_abs)
        self._update_slider()
        self._restore_annotation_state()
        self._refresh_info_labels()
        self._show_image()

    def _restore_annotation_state(self):
        key = self.nav.current_rel
        row = self.annotations.get(key)
        vars_to_clear = [
            *self.var_tissue.values(),
            *self.var_clinical.values(),
            *self.var_other.values(),
        ]
        for v in vars_to_clear:
            v.set(0)
        self.var_clinical_master.set(False)
        self.txt_comment.delete("1.0", tk.END)

        if row is not None:
            for t in CONFIG.TISSUE_TYPES:
                self.var_tissue[t].set(int(row.get(t, 0)))
            has_clin = any(row.get(c) == 1 for c in CONFIG.CLINICAL_CLASSIFICATION)
            self.var_clinical_master.set(has_clin)
            for c in CONFIG.CLINICAL_CLASSIFICATION:
                self.var_clinical[c].set(int(row.get(c, 0)))
            for o in CONFIG.OTHER_ATTRIBUTES:
                self.var_other[o].set(int(row.get(o, 0)))
            if row.get(CONFIG.COMMENT_COLUMN):
                self.txt_comment.insert(tk.END, str(row[CONFIG.COMMENT_COLUMN]))
        self._toggle_clinical()

    def _refresh_info_labels(self):
        # update subject / site labels
        rel = os.path.relpath(self.nav.current_abs, self.root_dir)
        parts = rel.split(os.sep)
        subj = parts[0] if parts else ""
        site = parts[1] if len(parts) > 1 else ""
        self.lbl_root.config(text=f"Root: {self.root_dir.name}")
        self.lbl_subject.config(text=f"Subject: {subj}")
        self.lbl_site.config(text=f"Site: {site}")

    # ------------------------------------------------------------------ #
    #                               CLIPBOARD
    # ------------------------------------------------------------------ #
    def _copy_path(self):
        if not self.images:
            return
        fp, page = self.images.get(self.image_idx)
        txt = f"{fp}  [page {page}]" if page else str(fp)
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.update()  # keep after quit
