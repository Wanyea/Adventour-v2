"""Exercise actual export/import boundaries with an isolated registry."""

import json

import pytest

from evaluation.field_kit import make_manifest, validate_answers
from evaluation.import_labels import apply_return, prepare


def sample():
    rows = [{"id": "one", "name": "Our indexed name", "metro": "new_city", "postcode": "12345"},
            {"id": "two", "name": "Other place", "metro": "other_city", "postcode": "67890"}]
    manifest = make_manifest(rows, {"population": "all_tiers"})
    answer = {"schema_version": 2, "kit_id": manifest["kit_id"], "zips": ["12345", "67890"],
              "labels": [{"id": "one", "name": "Untrusted name", "label": "gem",
                          "attributes": {"operation": "closed"}}, {"id": "two", "label": "junk"}],
              "freeform": {"missing": "A locally loved place"}}
    return manifest, answer


def test_quality_and_closure_are_independent_and_metadata_is_trusted():
    manifest, answer = sample()
    result = validate_answers(answer, manifest)
    assert result["labels"][0]["name"] == "Our indexed name"
    assert result["labels"][0]["label"] == "gem"
    assert result["labels"][0]["attributes"]["operation"] == "closed"
    answer["labels"].append(answer["labels"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        validate_answers(answer, manifest)


def test_preview_apply_multi_metro_and_duplicate_handling(tmp_path):
    manifest, answer = sample()
    kits = tmp_path / "kits"
    kits.mkdir()
    (kits / f"{manifest['kit_id']}.json").write_text(json.dumps(manifest))
    path, registry = tmp_path / "answers.json", tmp_path / "registry.json"
    path.write_text(json.dumps(answer))
    registry.write_text(json.dumps({"sets": [], "fitted_on": {}}))
    kwargs = {"registry_path": registry, "kits": kits}
    assert apply_return(path, "reviewer-a", **kwargs) == 2
    assert json.loads(registry.read_text())["sets"] == []
    assert apply_return(path, "reviewer-a", apply=True, **kwargs) == 2
    assert apply_return(path, "reviewer-a", apply=True, **kwargs) == 0
    assert len(json.loads(registry.read_text())["sets"]) == 2
    answer["labels"][0]["label"] = "solid"
    path.write_text(json.dumps(answer))
    with pytest.raises(ValueError, match="already answered"):
        apply_return(path, "reviewer-a", apply=True, **kwargs)


def test_holdout_cannot_reuse_tuned_metro_or_wrong_kit():
    manifest, answer = sample()
    with pytest.raises(ValueError, match="already informed"):
        prepare(answer, manifest, "reviewer-a", {"fitted_on": {"filter": ["new_city"]}}, "holdout")
    answer["kit_id"] = "wrong"
    with pytest.raises(ValueError, match="version-2"):
        validate_answers(answer, manifest)
