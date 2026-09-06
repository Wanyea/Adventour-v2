"""Validated regional acquisition configuration; no SQL or credentials in config."""

import json
import math
import re
from pathlib import Path

DEFAULT = Path(__file__).with_name("metros.json")


def read_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.\d+", config.get("release", "")):
        raise ValueError("release must be a pinned Overture release, YYYY-MM-DD.N")
    if not isinstance(config.get("metros"), dict) or not config["metros"]:
        raise ValueError("Provide at least one named metro bounding box.")
    for name, box in {**config["metros"], "reference": config["reference_bbox"]}.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name):
            raise ValueError(f"Invalid metro name: {name}")
        if set(box) != {"xmin", "xmax", "ymin", "ymax"} or any(
                not isinstance(v, (int, float)) or not math.isfinite(v) for v in box.values()):
            raise ValueError(f"Invalid bounding box for {name}")
        if not (-180 <= box["xmin"] < box["xmax"] <= 180
                and -90 <= box["ymin"] < box["ymax"] <= 90):
            raise ValueError(f"Invalid coordinates for {name}")
    reference = config["reference_bbox"]
    boxes = list(config["metros"].items())
    for index, (name, box) in enumerate(boxes):
        if any(box[k] < reference[k] for k in ("xmin", "ymin")) or any(
                box[k] > reference[k] for k in ("xmax", "ymax")):
            raise ValueError(f"Reference area must contain {name}.")
        for other, b in boxes[index + 1:]:
            if max(box["xmin"], b["xmin"]) <= min(box["xmax"], b["xmax"]) and max(
                    box["ymin"], b["ymin"]) <= min(box["ymax"], b["ymax"]):
                raise ValueError(f"Metro bounding boxes overlap: {name}, {other}")
    return config


def sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def bbox_clause(box):
    return (f"bbox.xmin BETWEEN {box['xmin']} AND {box['xmax']} "
            f"AND bbox.ymin BETWEEN {box['ymin']} AND {box['ymax']}")
