# Tissue annotator
A simple, scrappy tissue annotation GUI developed for use with OCT scans for Margin-Dx at Illinois. 

# Setup
Tested with Python 3.12, `pillow==11.2.1`, and `pandas==2.2.3`.

I recommend using a virtual environment. 
Assuming Python 3.12 is accessible from the command line as `python`, you can run the following.
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

The program expects a file structure like
```
root
├── subject_1
│   ├── site_1
│   │    ├── image_001.tif
│   │    ├── image_002.tif
│   │    ...
│   ├── site_2
│   │    ├── image_001.tif
│   │    ├── image_002.tif
│   │    ...
│   ...
├── subject_2
│   ├── site_1
│   │    ├── image_001.tif
│   │    ├── image_002.tif
│   │    ...
│   ├── site_2
│   │    ├── image_001.tif
│   │    ├── image_002.tif
│   │    ...
│   ...
...
```
though the particular names of the folders and files do not matter. 
It is important that the images end with a three digit frame number, followed by the extension `.tif`, and that each subject have 1 or more sites.
The root folder will be selected by an OS file selection window when the program starts.

# Visualization
A drop-down menu shows the site folders detected in the root folder. 
There are three methods to navigate through the images in a given site folder, which will be displayed one at a time, in frame number order. 
The navigation methods are:
1. previous and next buttons, moving one frame at a time;
1. a slider, where the left side represents the first frame and the right side the last;
1. and the ability to scroll with the mouse, as long as the mouse is hovering over the image.

# Annotation
This was developed in order to facilitate annotation on a site-by-site basis.
Each site folder can be independently annotated with any combination of tissue types, represented as checkboxes.
If desired, each site folder can also be annotated with tumor labels (normal, normal-adjacent, tumor-adjacent, or tumor) based on what is visible in the scans.
Lastly, some miscellaneous other attributes and a generic text comment box are available.
The annotations are saved per folder in `annotations.csv`. 
Each tissue type or tumor label is formatted as a column in the CSV, with binary entries.

These annotations are saved upon clicking `Next folder`, meaning that work is saved even if not all folders are annotated.
If the folder is skipped or another folder is selected in the drop-down, no changes are saved to the CSV.

If the annotations file already exists and contains an entry for a given folder when it is loaded, the annotations will be loaded into the GUI.
These can be updated or the folder can be skipped.

# Caveats
Most deviations from expected structure are not handled gracefully.
The main exception is 3D TIFF volumes, which are quietly supported (they can be quite a bit slower).
