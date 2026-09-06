"""Validate a kit return; --apply registers immutable per-metro observations."""

import argparse
import json
import re
from pathlib import Path

from evaluation import datasets
from evaluation.field_kit import KITS, digest, validate_answers


def prepare(returned, manifest, reviewer, registry, role="development"):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", reviewer):
        raise ValueError("Use a stable anonymous reviewer ID: lowercase letters, digits, _ or -.")
    data = validate_answers(returned, manifest)
    metros = sorted({p["metro"] for p in manifest["places"] if p["postcode"] in data["zips"]})
    if role == "holdout" and any(m in used for m in metros for used in registry["fitted_on"].values()):
        raise ValueError("This metro already informed a component; it cannot be declared held out.")
    result = []
    for metro in metros:
        subset = {**data, "labels": [p for p in data["labels"] if p["metro"] == metro]}
        content_id = digest({"reviewer": reviewer, "metro": metro, "answers": subset})[:24]
        entry = {"id": content_id, "file": f"returns/{content_id}.json", "metro": metro,
                 "reviewer_id": reviewer, "sampling_population": manifest["sampling"]["population"],
                 "role": role, "kit_id": manifest["kit_id"],
                 "model_revision_at_sampling": manifest["model_revision"],
                 "answers_sha256": digest(subset)}
        result.append((entry, subset))
    return result


def apply_return(path, reviewer, role="development", apply=False, registry_path=None, kits=None):
    registry_path = registry_path or datasets.REGISTRY
    kits = kits or KITS
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    returned = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    kit_id = returned.get("kit_id", "")
    if not isinstance(kit_id, str) or not re.fullmatch(r"[a-f0-9]{24}", kit_id):
        raise ValueError("Missing or invalid kit ID. Legacy returns require explicit provenance review.")
    manifest = json.loads((kits / f"{kit_id}.json").read_text(encoding="utf-8"))
    pending = []
    for entry, answers in prepare(returned, manifest, reviewer, registry, role):
        if any(s["id"] == entry["id"] for s in registry["sets"]):
            print(f"Already imported: {entry['metro']} / {entry['id']}")
            continue
        ids = {p["id"] for p in answers["labels"]}
        for old in registry["sets"]:
            if old["reviewer_id"] != reviewer or old["metro"] != entry["metro"]:
                continue
            existing = json.loads((registry_path.parent / old["file"]).read_text(encoding="utf-8"))
            overlap = ids & {p["id"] for p in existing.get("labels", [])}
            if overlap:
                raise ValueError(f"Reviewer already answered {len(overlap)} places in {old['id']}. "
                                 "Resolve revisions explicitly; do not count this as another reviewer.")
        pending.append((entry, answers))
        print(f"Validated {entry['metro']}: {len(answers['labels'])} observations, role={role}")
    if apply and pending:
        for entry, answers in pending:
            target = registry_path.parent / entry["file"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(answers, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            registry["sets"].append(entry)
        temporary = registry_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
        temporary.replace(registry_path)
    elif pending:
        print("Preview only. Repeat with --apply to register these answers.")
    return len(pending)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--role", choices=("development", "holdout"), default="development",
                        help="holdout requires a prospectively reserved, untuned metro")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        apply_return(args.file, args.reviewer, args.role, args.apply)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(1, f"Import refused: {exc}\n")


if __name__ == "__main__":
    main()
