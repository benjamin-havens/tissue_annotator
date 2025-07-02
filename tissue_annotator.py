"""
TissueAnnotator - GUI tool for manual tissue-type labelling
==========================================================

Purpose
-------
Provide a zero-config desktop application (Tkinter) that lets a user rapidly
review microscopy *.tif* image sequences organised inside a root directory and
record which tissue types (and optional tumour/normal context) are present in
each *folder* (either a patient folder containing images, or a site sub-folder).

Main workflow
-------------
1.  User is prompted to pick the *root* directory.
2.  The program discovers every labellable folder:
      • If a patient folder contains .tif files directly, that folder is used.
      • Otherwise each site sub-folder containing .tif files is used.
3.  For each folder the GUI shows:
      • A scrollable/slider-controlled preview of all frames (sorted by their
        3-digit suffix).
      • Check-boxes for tissue types (list editable at top of file).
      • A master checkbox that enables four tumour/normal check-boxes.
4.  User ticks the appropriate boxes and clicks **Next Folder →** (or **Skip
    Folder**) to advance.  Annotations are written immediately to *annotations.csv*.
5.  The CSV carries two location fields:
      *root* — the selected root directory's basename
      *folder* — the relative path *inside* the root
   plus one column per tissue label.

The GUI can be closed and reopened any time; previous annotations are pre-loaded.

Running
-------
Install dependencies once::

    pip install pillow pandas

Then simply::

    python tissue_annotator.py
"""

import os
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import pandas as pd
import numpy as np

# === CONFIGURATION ===
TISSUE_TYPES = [
    "tumor",
    "dense",
    "fatty",
    "lymphatic",
    "muscle",
    "blood vessel",
    "fibrotic",
]
CLINICAL_CLASSIFICATION = [
    "normal",  # healthy, non-cancerous tissue
    "normal_adjacent",  # normal tissue that is adjacent to tumor
    "tumor",  # cancerous tissue
]
CLINICAL_CLASSIFICATION = [f"CLINICAL_{c}" for c in CLINICAL_CLASSIFICATION]
# Classifications are defined by current standard of care.
# METHODS: Tissue is removed from patient.
# In a cancer patient, tissue is labeled as "normal_adjacent" or "tumor" based on gross morphology
# (what it looks like with naked eye) and touch (firmer tissue indicate cancerous tissue).
OTHER_ATTRIBUTES = [
    "artifact",  # Heavy/noticeable artifacts
    "missing_sheath",  # Missing sheath artifact (bright line at top of image, used for calibrating some methods)
    "dark",  # Not bright enough
    "unidentified_structure",  # Clear structure that needs expert review
    "exclude",  # Do not use to train models
].sort()
# Column name for free‑text comments
COMMENT_COLUMN = "comments"
CSV_PATH = "annotations.csv"
THUMBNAIL_SIZE = (800, 600)  # max display size


# === UTILITIES ===
def find_folders(root):
    """Recursively walk *root* and collect every directory that directly
    contains one or more *.tif* files. If a directory qualifies, its
    sub-directories are not inspected further so each set of frames is
    treated as its own site, even when nested multiple levels deep."""
    folders = []
    for subject in sorted(os.listdir(root)):
        subj_path = os.path.join(root, subject)
        if not os.path.isdir(subj_path):
            continue

        for dirpath, dirnames, filenames in os.walk(subj_path):
            dirnames.sort()  # ensure deterministic traversal order
            if any(f.lower().endswith(".tif") for f in filenames):
                folders.append(dirpath)
                # Skip descendants to avoid recording nested duplicates
                dirnames[:] = []
    return sorted(folders)


def sorted_tifs(folder):
    """Return list of .tif filepaths sorted by 3-digit frame number."""
    pattern = re.compile(r"(\d{3})(?:_oct)?\.tif$", re.IGNORECASE)
    files = []
    for fn in os.listdir(folder):
        m = pattern.search(fn)
        if m:
            files.append((int(m.group(1)), fn))
    files.sort()
    return [os.path.join(folder, fn) for _, fn in files]


# === MAIN APP ===
class TissueAnnotator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tissue Type Annotator")
        # ask for root dir
        self.root_dir = filedialog.askdirectory(title="Select root directory")
        if not self.root_dir:
            self.destroy()
            return

        # build folder list
        abs_folders = find_folders(self.root_dir)
        rootname = os.path.basename(self.root_dir)
        self.root_name = rootname
        self.folders_abs = abs_folders
        self.folders = [
            os.path.join(rootname, os.path.relpath(p, self.root_dir))
            for p in abs_folders
        ]
        if not self.folders:
            messagebox.showerror("Error", "No .tif folders found under root.")
            self.destroy()
            return

        # load or init CSV
        if os.path.exists(CSV_PATH):
            self.df = pd.read_csv(CSV_PATH, dtype=str)
            if COMMENT_COLUMN not in self.df.columns:
                self.df[COMMENT_COLUMN] = pd.NA
        else:
            cols = (
                ["key", "root", "folder"]
                + TISSUE_TYPES
                + CLINICAL_CLASSIFICATION
                + OTHER_ATTRIBUTES
                + [COMMENT_COLUMN]
            )
            self.df = pd.DataFrame(columns=cols)
        # ensure a 'key' column (root + os.sep + folder) exists
        if "key" not in self.df.columns:
            self.df["key"] = (
                self.df["root"].astype(str) + os.sep + self.df["folder"].astype(str)
            )
        self.df.set_index("key", inplace=True)

        # GUI variables
        self.idx = 0
        self.image_paths = []
        self.image_idx = 0

        # vars for checkboxes
        self.tissue_vars = {t: tk.IntVar() for t in TISSUE_TYPES}
        self.tumor_master = tk.BooleanVar()
        self.tumor_vars = {t: tk.IntVar() for t in CLINICAL_CLASSIFICATION}
        self.other_vars = {t: tk.IntVar() for t in OTHER_ATTRIBUTES}

        # colour‑scale mode: "default" or "log"
        self.scale_mode = tk.StringVar(value="default")

        self.build_ui()
        self.load_folder()

    def build_ui(self):
        # detailed information display + copy‑path button
        info_container = ttk.Frame(self)
        info_container.pack(fill="x", padx=10, pady=5)

        info_frame = ttk.Frame(info_container)
        info_frame.pack(side="left", fill="x", expand=True)

        self.root_info = ttk.Label(info_frame, text="Root folder: ")
        self.root_info.grid(row=0, column=0, sticky="w")

        self.subject_info = ttk.Label(info_frame, text="Subject folder: ")
        self.subject_info.grid(row=1, column=0, sticky="w")

        self.site_info = ttk.Label(info_frame, text="Site folder: ")
        self.site_info.grid(row=2, column=0, sticky="w")

        self.frame_info = ttk.Label(info_frame, text="Frame number: ")
        self.frame_info.grid(row=3, column=0, sticky="w")

        self.path_info = ttk.Label(
            info_frame,
            text="Path: ",
            anchor="w",
            justify="left",
            wraplength=800,  # pixels – long paths will wrap instead of stretching the window
        )
        self.path_info.grid(row=4, column=0, sticky="w")

        # button to copy current image path to clipboard
        ttk.Button(info_container, text="Copy path 📋", command=self.copy_path).pack(
            side="left", padx=10
        )

        # drop‑down menu to jump to any folder
        self.folder_combo = ttk.Combobox(
            self, values=self.folders, state="readonly", width=60
        )
        self.folder_combo.pack(pady=5)
        self.folder_combo.bind("<<ComboboxSelected>>", self.on_folder_combo)

        # image + colour‑scaling side‑by‑side
        img_color_frame = ttk.Frame(self)
        img_color_frame.pack(fill="x", padx=10, pady=5)

        img_frame = ttk.Frame(img_color_frame)
        img_frame.grid(row=0, column=0)
        img_color_frame.grid_columnconfigure(
            0, weight=1
        )  # let the image column expand so img_frame sits centered
        self.prev_btn = ttk.Button(img_frame, text="◀ Prev", command=self.prev_image)
        self.prev_btn.grid(row=0, column=0)
        self.img_lbl = ttk.Label(img_frame)
        self.img_lbl.grid(row=0, column=1)
        # allow mouse-wheel scrolling directly on the image
        self.img_lbl.bind("<MouseWheel>", self.on_mousewheel)
        self.next_btn = ttk.Button(img_frame, text="Next ▶", command=self.next_image)
        self.next_btn.grid(row=0, column=2)

        # colour‑scaling options placed to the right of the image
        color_frame = ttk.LabelFrame(img_color_frame, text="Color Scaling")
        color_frame.grid(row=0, column=1, sticky="e", padx=(5, 0))

        ttk.Radiobutton(
            color_frame,
            text="Default",
            variable=self.scale_mode,
            value="default",
            command=self.show_image,
        ).grid(row=0, column=0, sticky="", padx=5, pady=(2, 0))

        ttk.Radiobutton(
            color_frame,
            text="Log",
            variable=self.scale_mode,
            value="log",
            command=self.show_image,
        ).grid(row=1, column=0, sticky="w", padx=5, pady=(0, 2))

        # slider to jump through frames quickly
        self.scale = ttk.Scale(self, orient="horizontal", command=self.on_scale)
        self.scale.pack(fill="x", padx=10, pady=5)

        # container so Tissue Types (left) and Tumor / Normal (right) sit side‑by‑side
        tt_frame = ttk.Frame(self)
        tt_frame.pack(fill="x", padx=10, pady=5)

        tissue_frame = ttk.LabelFrame(tt_frame, text="Tissue Types")
        tissue_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        for i, t in enumerate(TISSUE_TYPES):
            cb = ttk.Checkbutton(tissue_frame, text=t, variable=self.tissue_vars[t])
            cb.grid(row=i // 5, column=i % 5, sticky="w", padx=5)

        tumor_frame = ttk.LabelFrame(tt_frame, text="Clinical Classification")
        tumor_frame.pack(side="left", fill="both", padx=(5, 0))
        master_cb = ttk.Checkbutton(
            tumor_frame,
            text="Enable clinical classification",
            variable=self.tumor_master,
            command=self.toggle_tumor,
        )
        master_cb.grid(row=0, column=0, columnspan=4, sticky="w", pady=2)
        self.tumor_cbs = []
        for i, t in enumerate(CLINICAL_CLASSIFICATION):
            cb = ttk.Checkbutton(tumor_frame, text=t, variable=self.tumor_vars[t])
            cb.grid(row=1, column=i, sticky="w", padx=5)
            self.tumor_cbs.append(cb)

        # other attributes
        other_frame = ttk.LabelFrame(self, text="Other Attributes")
        other_frame.pack(fill="x", padx=10, pady=5)
        self.other_cbs = []
        for i, t in enumerate(OTHER_ATTRIBUTES):
            cb = ttk.Checkbutton(other_frame, text=t, variable=self.other_vars[t])
            cb.grid(row=1, column=i, sticky="w", padx=5)
            self.other_cbs.append(cb)

        # comments textbox within Other Attributes
        comment_frame = ttk.LabelFrame(self, text="Comments")
        comment_frame.pack(fill="x", padx=10, pady=5)

        self.comment_text = tk.Text(comment_frame, height=2, wrap="word")
        self.comment_text.pack(fill="x", expand=True, padx=5, pady=5)

        # next folder and skip folder buttons centered
        button_frame = ttk.Frame(self)
        button_frame.pack(pady=10)
        btn_skip = ttk.Button(
            button_frame, text="Skip Folder", command=self.skip_folder
        )
        btn_skip.pack(side="left", padx=5)
        btn_next = ttk.Button(
            button_frame, text="Next Folder →", command=self.next_folder
        )
        btn_next.pack(side="left", padx=5)

    def toggle_tumor(self):
        state = "normal" if self.tumor_master.get() else "disabled"
        for cb in self.tumor_cbs:
            cb.config(state=state)

    def load_folder(self):
        folder_rel = self.folders[self.idx]  # includes root/
        folder_abs = self.folders_abs[self.idx]
        folder_key = folder_rel
        # update info labels for root/subject/site
        parts = os.path.relpath(folder_abs, self.root_dir).split(os.sep)
        subject = parts[0] if len(parts) >= 1 else "N/A"
        site = parts[1] if len(parts) >= 2 else "N/A"

        self.root_info.config(text=f"Root folder: {self.root_name}")
        self.subject_info.config(text=f"Subject folder: {subject}")
        self.site_info.config(text=f"Site folder: {site}")
        self.frame_info.config(text="Frame number: ")
        self.path_info.config(text="Path: ")

        # keep drop‑down in sync
        self.folder_combo.current(self.idx)
        # load images
        self.image_paths = sorted_tifs(folder_abs)
        self.image_idx = 0
        # set up slider limits
        max_idx = max(len(self.image_paths) - 1, 0)
        self.scale.config(from_=0, to=max_idx)
        self.scale.set(0)
        self.show_image()

        # load annotation state if present
        if folder_key in self.df.index:
            row = self.df.loc[folder_key]
            # tissues
            for t in TISSUE_TYPES:
                self.tissue_vars[t].set(int(row[t]) if pd.notna(row[t]) else 0)
            # tumors
            # master on if any label is numeric
            has_vals = any(pd.notna(row[t]) for t in CLINICAL_CLASSIFICATION)
            self.tumor_master.set(has_vals)
            for t in CLINICAL_CLASSIFICATION:
                self.tumor_vars[t].set(int(row[t]) if pd.notna(row[t]) else 0)
            # other attributes
            for t in OTHER_ATTRIBUTES:
                self.other_vars[t].set(int(row[t]) if pd.notna(row[t]) else 0)
            # comments
            self.comment_text.delete("1.0", tk.END)
            if pd.notna(row.get(COMMENT_COLUMN)):
                self.comment_text.insert(tk.END, str(row[COMMENT_COLUMN]))
        else:
            for v in self.tissue_vars.values():
                v.set(0)
            self.tumor_master.set(False)
            for v in self.tumor_vars.values():
                v.set(0)
            for v in self.other_vars.values():
                v.set(0)
            self.comment_text.delete("1.0", tk.END)
        self.toggle_tumor()

    def show_image(self):
        if not self.image_paths:
            return
        path = self.image_paths[self.image_idx]
        img = Image.open(path)

        # apply optional log colour scaling
        if self.scale_mode.get() == "log":
            arr = np.array(img).astype(np.float32)

            # handle both grayscale (H,W) and colour (H,W,3) images
            max_val = arr.max() if arr.max() > 0 else 1.0
            arr = np.log1p(arr) / np.log1p(max_val) * 255.0
            arr = arr.astype(np.uint8)

            img = Image.fromarray(arr)

        img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(img)
        self.img_lbl.config(image=self.photo)
        # enable/disable prev/next
        self.prev_btn.state(["!disabled"] if self.image_idx > 0 else ["disabled"])
        self.next_btn.state(
            ["!disabled"]
            if self.image_idx < len(self.image_paths) - 1
            else ["disabled"]
        )
        # update frame number and path display
        match = re.search(
            r"(\d{3})(?:_oct)?\.tif$", os.path.basename(path), re.IGNORECASE
        )
        frame_no = match.group(1) if match else "N/A"
        self.frame_info.config(text=f"Frame number: {frame_no}")
        self.path_info.config(text=f"Path: {path}")

    def change_image(self, step):
        """Move step frames forward/backward, clamped to valid range."""
        new_idx = self.image_idx + step
        if 0 <= new_idx < len(self.image_paths):
            self.image_idx = new_idx
            self.scale.set(new_idx)
            self.show_image()

    def prev_image(self):
        self.change_image(-1)

    def next_image(self):
        self.change_image(1)

    def on_scale(self, val):
        """Called when user drags the slider."""
        idx = int(float(val))
        if idx != self.image_idx:
            self.image_idx = idx
            self.show_image()

    def on_mousewheel(self, event):
        """Scroll wheel moves through frames quickly."""
        step = -1 if event.delta > 0 else 1
        self.change_image(step)

    def on_folder_combo(self, event):
        """Jump to the selected folder without saving current annotations."""
        sel = self.folder_combo.get()
        if not sel:
            return
        try:
            new_idx = self.folders.index(sel)
        except ValueError:
            return
        if new_idx == self.idx:
            return
        # treat current folder as skipped
        self.idx = new_idx
        self.load_folder()

    def next_folder(self):
        # gather and save
        folder_rel = self.folders[self.idx]
        folder_abs = self.folders_abs[self.idx]
        folder_sub = os.path.relpath(folder_abs, self.root_dir)
        data = {}
        data["root"] = self.root_name
        data["folder"] = folder_sub
        for t in TISSUE_TYPES:
            data[t] = self.tissue_vars[t].get()
        # tumors
        if self.tumor_master.get():
            for t in CLINICAL_CLASSIFICATION:
                data[t] = self.tumor_vars[t].get()
        else:
            for t in CLINICAL_CLASSIFICATION:
                data[t] = pd.NA
        # other attributes
        for t in OTHER_ATTRIBUTES:
            data[t] = self.other_vars[t].get()
        # comments
        comment_val = self.comment_text.get("1.0", "end").strip()
        data[COMMENT_COLUMN] = comment_val if comment_val else pd.NA
        # update df
        self.df.loc[folder_rel] = data
        # write CSV
        df_out = self.df.reset_index(names="key")
        df_out.drop(columns="key").to_csv(CSV_PATH, index=False)

        # advance
        if self.idx < len(self.folders) - 1:
            self.idx += 1
            self.load_folder()
        else:
            messagebox.showinfo("Done", "All folders processed.")
            self.destroy()

    def skip_folder(self):
        """Advance to the next folder without saving."""
        if self.idx < len(self.folders) - 1:
            self.idx += 1
            self.load_folder()
        else:
            messagebox.showinfo("Done", "All folders processed.")
            self.destroy()

    def copy_path(self):
        """Copy the current image path to the system clipboard."""
        if not self.image_paths:
            return
        path = self.image_paths[self.image_idx]
        self.clipboard_clear()
        self.clipboard_append(path)
        self.update()  # keep clipboard after window closes


if __name__ == "__main__":
    app = TissueAnnotator()
    app.mainloop()
