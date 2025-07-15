import os

import pandas as pd

from .config import Config

CONFIG = Config()


class AnnotationManager:
    """Load / persist annotation CSV."""

    def __init__(self, csv_path=CONFIG.CSV_PATH):
        self.csv_path = csv_path
        self.df = self._load()

    def _load(self) -> pd.DataFrame:
        if self.csv_path.exists():
            df = pd.read_csv(self.csv_path, dtype=str)
            if CONFIG.COMMENT_COLUMN not in df.columns:
                df[CONFIG.COMMENT_COLUMN] = pd.NA
        else:
            cols = (
                ["key", "root", "folder"]
                + list(CONFIG.TISSUE_TYPES)
                + list(CONFIG.CLINICAL_CLASSIFICATION)
                + list(CONFIG.OTHER_ATTRIBUTES)
                + [CONFIG.COMMENT_COLUMN]
            )
            df = pd.DataFrame(columns=cols)
        if "key" not in df.columns:
            df["key"] = df["root"].astype(str) + os.sep + df["folder"].astype(str)
        return df.set_index("key")

    def get(self, key):
        return self.df.loc[key] if key in self.df.index else None

    def update(self, key: str, data):
        self.df.loc[key] = data
        self.df.reset_index(names="key").drop(columns="key").to_csv(
            self.csv_path, index=False
        )
