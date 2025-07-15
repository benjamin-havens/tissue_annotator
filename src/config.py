import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    TISSUE_TYPES = (
        "tumor",
        "dense",
        "fatty",
        "lymphatic",
        "muscle",
        "blood vessel",
        "fibrotic",
    )
    CLINICAL_CLASSIFICATION = tuple(
        f"CLINICAL_{c}" for c in ("normal", "normal_adjacent", "tumor")
    )
    OTHER_ATTRIBUTES = tuple(
        sorted(
            (
                "artifact",
                "missing_sheath",
                "dark",
                "unidentified_structure",
                "exclude",
            )
        )
    )
    COMMENT_COLUMN: str = "comments"
    CSV_PATH = Path("annotations.csv")
    THUMBNAIL_SIZE = (800 // 1.1, 600 // 1.1)
    FRAME_REGEX = re.compile(r"(\d{3})(?:_oct)?\.tif$", re.IGNORECASE)
