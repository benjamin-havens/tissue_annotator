import json
from typing import TypedDict, Union, Literal
import datetime

import tifffile
from ome_types import from_xml


class SampleMetadata(TypedDict, total=False):
    sample_id: str
    subsample_id: Union[str, None]
    patient_id: str
    patient_age: Union[int, None]
    patient_sex: Literal["female", "male"]
    organ: Literal["breast", "lung", "liver", "pancreas", "No Match"]
    designation: Literal["Tumor", "Normal Adjacent", "Uninvolved", "No Match"]
    metastatic: bool
    primary: bool
    arrival_date: datetime.date
    acq_datetime: datetime.datetime
    agency: Literal["CHTN", "NDRI"]


class MetadataExtractor:
    """Static helpers for best-effort OME-TIFF metadata extraction."""

    @staticmethod
    def _extract_sample_metadata(ome):
        """Extract sample metadata from OME-TIFF."""
        sample_metadata = SampleMetadata()

        if ome.structured_annotations and ome.structured_annotations.map_annotations:
            for annotation in ome.structured_annotations.map_annotations:
                if annotation.namespace == "custom.sample.metadata":
                    for m in annotation.value.ms:
                        key = m.k
                        if key in ["sample_id", "subsample_id"]:
                            value = m.value.replace("_", "-").upper()
                        elif key in ["metastatic", "primary"]:
                            value = bool(m.value.lower() == "true")
                        elif key in ["patient_age"]:
                            value = int(m.value)
                        elif key in ["patient_sex"]:
                            value = m.value.lower()
                        else:
                            value = m.value
                        sample_metadata[key] = value
        return sample_metadata

    @staticmethod
    def _extract_image_parameters(ome):
        imaging_params = {}
        if ome.images and ome.images[0].pixels:
            pixels = ome.images[0].pixels
            imaging_params = {
                "dimension_order": (
                    pixels.dimension_order.value if pixels.dimension_order else None
                ),
                "size_x": pixels.size_x,
                "size_y": pixels.size_y,
                "size_z": pixels.size_z,
                "size_c": pixels.size_c,
                "size_t": pixels.size_t,
                "type": pixels.type,
                "physical_size_x": pixels.physical_size_x,
                "physical_size_y": pixels.physical_size_y,
                "physical_size_z": pixels.physical_size_z,
                "channels": (
                    [ch.name for ch in pixels.channels] if pixels.channels else []
                ),
            }
        return imaging_params

    @staticmethod
    def extract(path):
        md = {}

        try:
            with tifffile.TiffFile(path) as tif:
                md["pages"] = str(len(tif.pages))
                md["dtype"] = str(tif.series[0].dtype) if tif.series else ""
                ome_xml = tif.pages[0].description
                ome = from_xml(ome_xml)
        except Exception as e:
            md["error"] = f"Failed to read OME-TIFF: {e}"
            return md

        sample_metadata = MetadataExtractor._extract_sample_metadata(ome)
        imaging_params = MetadataExtractor._extract_image_parameters(ome)

        return md | sample_metadata | imaging_params
