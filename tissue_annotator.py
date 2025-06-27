"""
TissueAnnotator – GUI tool for manual tissue‑type labelling
==========================================================

Purpose
-------
Provide a zero‑config desktop application (Tkinter) that lets a user rapidly
review microscopy *.tif* image sequences organised inside a root directory and
record which tissue types (and optional tumour/normal context) are present in
each *folder* (either a patient folder containing images, or a site sub‑folder).

Main workflow
-------------
1.  User is prompted to pick the *root* directory.
2.  The program discovers every labellable folder:
      • If a patient folder contains .tif files directly, that folder is used.
      • Otherwise each site sub‑folder containing .tif files is used.
3.  For each folder the GUI shows:
      • A scrollable/slider‑controlled preview of all frames (sorted by their
        3‑digit suffix).
      • Check‑boxes for tissue types (list editable at top of file).
      • A master checkbox that enables four tumour/normal check‑boxes.
4.  User ticks the appropriate boxes and clicks **Next Folder →** (or **Skip
    Folder**) to advance.  Annotations are written immediately to *annotations.csv*.
5.  The CSV carries two location fields:
      *root* — the selected root directory’s basename
      *folder* — the relative path *inside* the root
   plus one column per tissue label.

The GUI can be closed and reopened any time; previous annotations are pre‑loaded.

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

# === CONFIGURATION ===
TISSUE_TYPES = [
    "adipose",
    "adrenal",
    "bone",
    "cartilage",
    "connective",
    "epithelium",
    "lymphoid",
    "muscle",
    "nervous",
    "vascular",
]
TUMOR_LABELS = ["normal", "normal_adjacent", "tumor_adjacent", "tumor"]
CSV_PATH = "annotations.csv"
THUMBNAIL_SIZE = (800, 600)  # max display size


# === UTILITIES ===
def find_folders(root):
    """Walk root; for each subject, if it has .tif files use it,
    else find its subdirs with .tif and use each."""
    folders = []
    for sub in sorted(os.listdir(root)):
        p = os.path.join(root, sub)
        if not os.path.isdir(p):
            continue
        tif_files = [f for f in os.listdir(p) if f.lower().endswith(".tif")]
        if tif_files:
            folders.append(p)
        else:
            for site in sorted(os.listdir(p)):
                sitep = os.path.join(p, site)
                if os.path.isdir(sitep):
                    if any(f.lower().endswith(".tif") for f in os.listdir(sitep)):
                        folders.append(sitep)
    return folders


def sorted_tifs(folder):
    """Return list of .tif filepaths sorted by 3-digit frame number."""
    pattern = re.compile(r"(\d{3})\.tif$", re.IGNORECASE)
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
        else:
            cols = ["key", "root", "folder"] + TISSUE_TYPES + TUMOR_LABELS
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
        self.tumor_vars = {t: tk.IntVar() for t in TUMOR_LABELS}

        self.build_ui()
        self.load_folder()

    def build_ui(self):
        # path label
        self.path_lbl = ttk.Label(self, text="", font=("Arial", 12))
        self.path_lbl.pack(pady=5)

        # image frame
        img_frame = ttk.Frame(self)
        img_frame.pack()
        self.prev_btn = ttk.Button(img_frame, text="◀ Prev", command=self.prev_image)
        self.prev_btn.grid(row=0, column=0)
        self.img_lbl = ttk.Label(img_frame)
        self.img_lbl.grid(row=0, column=1)
        # allow mouse‑wheel scrolling directly on the image
        self.img_lbl.bind("<MouseWheel>", self.on_mousewheel)
        self.next_btn = ttk.Button(img_frame, text="Next ▶", command=self.next_image)
        self.next_btn.grid(row=0, column=2)

        # slider to jump through frames quickly
        self.scale = ttk.Scale(self, orient="horizontal", command=self.on_scale)
        self.scale.pack(fill="x", padx=10, pady=5)

        # tissue checkboxes
        tissue_frame = ttk.LabelFrame(self, text="Tissue Types")
        tissue_frame.pack(fill="x", padx=10, pady=5)
        for i, t in enumerate(TISSUE_TYPES):
            cb = ttk.Checkbutton(tissue_frame, text=t, variable=self.tissue_vars[t])
            cb.grid(row=i // 5, column=i % 5, sticky="w", padx=5)

        # tumor/normal
        tumor_frame = ttk.LabelFrame(self, text="Tumor / Normal")
        tumor_frame.pack(fill="x", padx=10, pady=5)
        master_cb = ttk.Checkbutton(
            tumor_frame,
            text="Enable tumor/normal labels",
            variable=self.tumor_master,
            command=self.toggle_tumor,
        )
        master_cb.grid(row=0, column=0, columnspan=4, sticky="w", pady=2)
        self.tumor_cbs = []
        for i, t in enumerate(TUMOR_LABELS):
            cb = ttk.Checkbutton(tumor_frame, text=t, variable=self.tumor_vars[t])
            cb.grid(row=1, column=i, sticky="w", padx=5)
            self.tumor_cbs.append(cb)

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
        folder_sub = os.path.relpath(folder_abs, self.root_dir)
        folder_key = folder_rel
        self.path_lbl.config(text=folder_rel)
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
            has_vals = any(pd.notna(row[t]) for t in TUMOR_LABELS)
            self.tumor_master.set(has_vals)
            for t in TUMOR_LABELS:
                self.tumor_vars[t].set(int(row[t]) if pd.notna(row[t]) else 0)
        else:
            for v in self.tissue_vars.values():
                v.set(0)
            self.tumor_master.set(False)
            for v in self.tumor_vars.values():
                v.set(0)
        self.toggle_tumor()

    def show_image(self):
        if not self.image_paths:
            return
        path = self.image_paths[self.image_idx]
        img = Image.open(path)
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
            for t in TUMOR_LABELS:
                data[t] = self.tumor_vars[t].get()
        else:
            for t in TUMOR_LABELS:
                data[t] = pd.NA
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


if __name__ == "__main__":
    app = TissueAnnotator()
    app.mainloop()
