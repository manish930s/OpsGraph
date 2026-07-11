import json
from pathlib import Path
from enum import Enum
from typing import Any, Iterable, Sequence
from evals.schemas import GoldenScenario, DatasetSummary


def discover_scenarios(base_dir: str | Path) -> list[Path]:
    """
    Scans a base directory to locate scenarios.
    A scenario is represented either as a directory containing 'golden.json'
    or a standalone '.json' file.
    Returns a list of Paths sorted deterministically by name.
    """
    path = Path(base_dir)
    scenarios = []
    if not path.exists():
        return []

    for item in path.iterdir():
        if item.is_dir():
            if (item / "golden.json").exists():
                scenarios.append(item)
        elif item.is_file() and item.suffix == ".json":
            # Exclude non-scenario json files (like topology.json)
            try:
                with open(item, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "scenario_id" in data:
                    scenarios.append(item)
            except Exception:
                pass

    return sorted(scenarios, key=lambda p: p.name)


def load_scenario(path: str | Path) -> tuple[GoldenScenario | None, list[str], list[str]]:
    """
    Loads and validates a GoldenScenario from a directory or a standalone JSON file.
    Maps legacy/custom schemas for backward compatibility and runs validations.
    Returns: (GoldenScenario or None, errors list, warnings list)
    """
    path = Path(path)
    errors = []
    warnings = []

    json_path = path / "golden.json" if path.is_dir() else path
    if not json_path.exists():
        errors.append(f"Scenario configuration file not found at {json_path}")
        return None, errors, warnings

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        errors.append(f"JSON parsing failed for {json_path.name}: {str(e)}")
        return None, errors, warnings

    if not isinstance(data, dict):
        errors.append(f"Invalid JSON content in {json_path.name}: expected dict, got {type(data).__name__}")
        return None, errors, warnings

    # Compatibility Mapping: expected_tools -> required_tools
    if "expected_tools" in data and "required_tools" not in data:
        data["required_tools"] = data["expected_tools"]

    # Optional field fallbacks for schema consistency
    if "split" not in data:
        data["split"] = "dev"
    if "ambiguity" not in data:
        data["ambiguity"] = "unambiguous"
    if "expected_terminal_outcome" not in data:
        data["expected_terminal_outcome"] = "finalize_rca"
    if "acceptable_terminal_outcomes" not in data:
        data["acceptable_terminal_outcomes"] = ["finalize_rca"]

    # Mapping ground_truth to labels
    if "labels" not in data:
        if "ground_truth" in data and isinstance(data["ground_truth"], dict):
            gt = data["ground_truth"]
            fc = data.get("fault_category") or gt.get("fault_category") or ""
            forbidden_codes = gt.get("forbidden_unsupported_cause_codes") or data.get("forbidden_unsupported_causes") or []
            equiv_codes = gt.get("acceptable_equivalent_root_cause_codes") or data.get("acceptable_root_cause_codes") or []
            data["labels"] = {
                "affected_service": gt.get("affected_service") or "",
                "fault_category": fc,
                "root_cause_code": gt.get("root_cause_code") or "",
                "root_cause_summary": gt.get("root_cause_summary") or "",
                "acceptable_equivalent_root_cause_codes": equiv_codes,
                "forbidden_unsupported_cause_codes": forbidden_codes
            }
        else:
            warnings.append(f"{json_path.name}: Labels/ground_truth missing. Initializing empty values.")
            data["labels"] = {
                "affected_service": "",
                "fault_category": "",
                "root_cause_code": "",
                "root_cause_summary": ""
            }

    # Normalize inner labels lists
    if "labels" in data and isinstance(data["labels"], dict):
        lbl = data["labels"]
        if not lbl.get("forbidden_unsupported_cause_codes"):
            lbl["forbidden_unsupported_cause_codes"] = data.get("forbidden_unsupported_causes") or []
        if not lbl.get("acceptable_equivalent_root_cause_codes"):
            lbl["acceptable_equivalent_root_cause_codes"] = data.get("acceptable_root_cause_codes") or []

    # Strict scenario ID/incident ID presence check
    scenario_id = data.get("scenario_id")
    if not scenario_id:
        errors.append(f"Missing required field 'scenario_id' in {json_path.name}")
    incident_id = data.get("incident_id")
    if not incident_id:
        errors.append(f"Missing required field 'incident_id' in {json_path.name}")

    if errors:
        return None, errors, warnings

    # Pydantic schema validation
    scenario = None
    try:
        scenario = GoldenScenario.model_validate(data)
    except Exception as e:
        errors.append(f"Schema validation failed: {str(e)}")
        return None, errors, warnings

    # Verify evidence references if scenario is inside a directory containing evidence.json
    if scenario and path.is_dir():
        evidence_path = path / "evidence.json"
        if evidence_path.exists():
            try:
                with open(evidence_path, "r", encoding="utf-8") as f:
                    evidence_data = json.load(f)
                if not isinstance(evidence_data, list):
                    errors.append(f"evidence.json is invalid: expected list, got {type(evidence_data).__name__}")
                else:
                    evidence_ids = {
                        ev.get("evidence_id")
                        for ev in evidence_data
                        if isinstance(ev, dict) and ev.get("evidence_id")
                    }
                    for req_ev_id in scenario.required_evidence_ids:
                        if req_ev_id not in evidence_ids:
                            errors.append(f"Required evidence ID '{req_ev_id}' not found in evidence.json.")
            except Exception as e:
                errors.append(f"Failed to load/parse evidence.json: {str(e)}")
        else:
            if scenario.required_evidence_ids:
                warnings.append("evidence.json is missing; cannot validate required evidence IDs.")

    return scenario, errors, warnings


def load_dataset(base_dir: str | Path) -> tuple[list[GoldenScenario], DatasetSummary]:
    """
    Loads all discovered scenarios in the base directory.
    Validates each scenario, checks for duplicate IDs, and returns a sorted list of
    validated GoldenScenario objects along with a DatasetSummary.
    """
    paths = discover_scenarios(base_dir)
    scenarios = []
    validation_errors = {}
    validation_warnings = {}

    split_counts = {}
    ambiguity_counts = {}
    scenario_ids = []

    for path in paths:
        scenario, errs, warns = load_scenario(path)
        scenario_id = scenario.scenario_id if scenario else path.name

        if errs:
            validation_errors[scenario_id] = errs
        if warns:
            validation_warnings[scenario_id] = warns

        if scenario:
            scenarios.append(scenario)
            scenario_ids.append(scenario.scenario_id)

            split_val = scenario.split.value if isinstance(scenario.split, Enum) else str(scenario.split)
            split_counts[split_val] = split_counts.get(split_val, 0) + 1

            amb_val = scenario.ambiguity.value if isinstance(scenario.ambiguity, Enum) else str(scenario.ambiguity)
            ambiguity_counts[amb_val] = ambiguity_counts.get(amb_val, 0) + 1

    # Detect duplicate scenario IDs
    id_counts = {}
    for s in scenarios:
        id_counts[s.scenario_id] = id_counts.get(s.scenario_id, 0) + 1

    for sid, count in id_counts.items():
        if count > 1:
            err_msg = f"Duplicate scenario ID found across dataset: {sid}"
            if sid not in validation_errors:
                validation_errors[sid] = []
            validation_errors[sid].append(err_msg)

    # Deterministic ordering by scenario_id ascending
    scenarios.sort(key=lambda s: s.scenario_id)

    summary = DatasetSummary(
        total_scenarios=len(scenarios),
        split_counts=split_counts,
        ambiguity_counts=ambiguity_counts,
        scenario_ids=sorted(scenario_ids),
        validation_errors=validation_errors,
        validation_warnings=validation_warnings
    )

    return scenarios, summary


def validate_dataset(base_dir: str | Path) -> DatasetSummary:
    """
    Convenience wrapper to run validation checks over a dataset directory.
    """
    _, summary = load_dataset(base_dir)
    return summary
