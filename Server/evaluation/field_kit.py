"""Versioned offline-kit contract; returned answers never supply index metadata."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KITS = ROOT / "kits"
VERSION = 2
LABELS = {"gem", "solid", "generic", "not_worth", "chain", "trap", "junk", "unknown"}
ATTRIBUTES = {
    "operation": {"open", "closed", "unknown"},
    "public_access": {"yes", "restricted", "unknown"},
    "booking": {"required", "optional", "no", "unknown"},
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def model_revision():
    pipeline = ROOT.parent / "data_pipeline"
    return {name: hashlib.sha256((pipeline / name).read_bytes()).hexdigest()
            for name in ("junk_filter.py", "authenticity.py", "dedup.py")}


def make_manifest(rows, sampling):
    body = {"schema_version": VERSION, "sampling": sampling,
            "model_revision": model_revision(), "places": rows}
    return {**body, "kit_id": digest(body)[:24]}


def validate_answers(returned, manifest):
    body = {k: v for k, v in manifest.items() if k != "kit_id"}
    if digest(body)[:24] != manifest.get("kit_id"):
        raise ValueError("Kit manifest changed since generation; restore the original manifest.")
    if returned.get("schema_version") != VERSION or returned.get("kit_id") != manifest["kit_id"]:
        raise ValueError("Answers must come from this version-2 kit; keep the matching manifest.")
    known = {p["id"]: p for p in manifest["places"]}
    zips = returned.get("zips", [])
    if not isinstance(zips, list) or not zips or not set(zips) <= {p["postcode"] for p in known.values()}:
        raise ValueError("Unrecognized ZIP selection.")
    labels, seen = [], set()
    if not isinstance(returned.get("labels"), list):
        raise ValueError("labels must be a list.")
    for answer in returned["labels"]:
        pid = answer.get("id")
        if pid not in known or pid in seen or known[pid]["postcode"] not in zips:
            raise ValueError(f"Duplicate, unknown or unselected place: {pid}")
        seen.add(pid)
        if answer.get("label") not in LABELS | {None}:
            raise ValueError(f"Invalid quality label for {pid}")
        attrs = answer.get("attributes", {})
        if not isinstance(attrs, dict) or set(attrs) - ATTRIBUTES.keys():
            raise ValueError(f"Invalid attributes for {pid}")
        if any(value not in ATTRIBUTES[key] for key, value in attrs.items()):
            raise ValueError(f"Invalid attribute answer for {pid}")
        note = answer.get("note") or ""
        if not isinstance(note, str) or len(note) > 20000:
            raise ValueError(f"Invalid or overlong note for {pid}")
        labels.append({**known[pid], "label": answer.get("label"), "note": note,
                       "attributes": attrs})
    freeform = returned.get("freeform", {})
    if not isinstance(freeform, dict) or any(not isinstance(v, str) or len(v) > 20000
                                            for v in freeform.values()):
        raise ValueError("Written answers must be text, at most 20,000 characters each.")
    if not labels and not freeform:
        raise ValueError("The return contains no answers.")
    return {"schema_version": VERSION, "kit_id": manifest["kit_id"], "zips": zips,
            "labels": labels, "freeform": freeform}
