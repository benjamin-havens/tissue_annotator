import json

import tifffile
from ome_types import from_xml


class MetadataExtractor:
    """Static helpers for best-effort OME-TIFF metadata extraction."""

    @staticmethod
    def extract(path):
        if not tifffile:
            return {}
        md = {}
        try:
            with tifffile.TiffFile(path) as tif:
                md["pages"] = str(len(tif.pages))
                md["dtype"] = str(tif.series[0].dtype) if tif.series else ""
                # ImageDescription can live in various places
                page0 = tif.pages[0]
                if "ImageDescription" in page0.tags:
                    desc = page0.tags["ImageDescription"].value
                else:
                    desc = getattr(page0, "description", None)
                ome_xml = desc.decode() if isinstance(desc, bytes) else desc
        except Exception as e:
            md["error"] = str(e)
            return md
        if ome_xml and from_xml and ome_xml.strip().startswith("<?xml"):
            try:
                ome = from_xml(ome_xml)
                img0 = ome.images[0] if ome.images else None
                if img0:
                    p = img0.pixels
                    md.update(
                        {
                            "SizeX": p.size_x,
                            "SizeY": p.size_y,
                            "SizeZ": p.size_z,
                            "VoxelSizeX": p.physical_size_x,
                            "VoxelSizeY": p.physical_size_y,
                            "VoxelSizeZ": p.physical_size_z,
                            "DimensionOrder": (
                                p.dimension_order.value if p.dimension_order else ""
                            ),
                        }
                    )
                    # extra pixel info
                    md["SizeC"] = p.size_c
                    md["SizeT"] = p.size_t
                    md["PixelType"] = p.type.value if p.type else ""
                    md["Channels"] = ", ".join(
                        [ch.name or f"Ch{i}" for i, ch in enumerate(p.channels)]
                    )

                    # gather any MapAnnotation / XMLAnnotation key‑values
                    sa = getattr(ome, "structured_annotations", None)
                    if sa:
                        for ann in sa:
                            # MapAnnotation: ann.value is list[KeyValuePair]
                            if hasattr(ann, "value") and isinstance(ann.value, list):
                                first = ann.value[0] if ann.value else None
                                if (
                                    first
                                    and hasattr(first, "key")
                                    and hasattr(first, "value")
                                ):
                                    for kv in ann.value:
                                        md[str(kv.key)] = str(kv.value)
                                    continue
                            # XMLAnnotation: attempt JSON decode
                            if hasattr(ann, "value") and isinstance(ann.value, str):
                                try:
                                    data = json.loads(ann.value)
                                    if isinstance(data, dict):
                                        md.update(
                                            {str(k): str(v) for k, v in data.items()}
                                        )
                                except Exception:
                                    pass
            except Exception as e:
                md["ome_parse_error"] = str(e)
        return md
