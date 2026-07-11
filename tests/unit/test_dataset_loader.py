import json
import pytest
from pathlib import Path
from evals.schemas import (
    GoldenScenario,
    DatasetSplit,
    ScenarioAmbiguity,
    ExpectedTerminalOutcome,
    MetricStatus
)
from evals.dataset_loader import (
    discover_scenarios,
    load_scenario,
    load_dataset,
    validate_dataset,
    DatasetSummary
)
from evals.runner import evaluate_mock_graph


# --- Helpers ---

def create_mock_scenario_json(
    scenario_id="SCN-001",
    incident_id="INC-001",
    extra_fields=None
) -> dict:
    base = {
        "schema_version": "1.0",
        "scenario_id": scenario_id,
        "incident_id": incident_id,
        "split": "dev",
        "ambiguity": "unambiguous",
        "expected_terminal_outcome": "finalize_rca",
        "acceptable_terminal_outcomes": ["finalize_rca"],
        "labels": {
            "affected_service": "checkout-service",
            "fault_category": "database_connection_pool",
            "root_cause_code": "DB_POOL_MAX_CONNECTIONS_REGRESSION",
            "root_cause_summary": "Invalid pool settings."
        },
        "required_evidence_ids": ["EV-1"],
        "required_tools": ["log_pattern_search"],
        "acceptable_tools": ["metric_window_analysis"],
        "forbidden_tools": ["forbidden_tool_a"]
    }
    if extra_fields:
        base.update(extra_fields)
    return base


# --- 1. SINGLE SCENARIO LOADING ---

def test_load_scenario_file(tmp_path):
    file_path = tmp_path / "SCN-001.json"
    data = create_mock_scenario_json("SCN-001")
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    scenario, errors, warnings = load_scenario(file_path)
    assert errors == []
    assert warnings == []
    assert scenario is not None
    assert scenario.scenario_id == "SCN-001"
    assert scenario.split == DatasetSplit.DEV


def test_load_scenario_directory(tmp_path):
    dir_path = tmp_path / "SCN-001"
    dir_path.mkdir()
    
    # Write golden.json
    data = create_mock_scenario_json("SCN-001", extra_fields={"required_evidence_ids": ["EV-1"]})
    with open(dir_path / "golden.json", "w", encoding="utf-8") as f:
        json.dump(data, f)

    # Write evidence.json
    evidence = [
        {"evidence_id": "EV-1", "source_type": "log", "observation": "error logs found"}
    ]
    with open(dir_path / "evidence.json", "w", encoding="utf-8") as f:
        json.dump(evidence, f)

    scenario, errors, warnings = load_scenario(dir_path)
    assert errors == []
    assert warnings == []
    assert scenario is not None
    assert scenario.scenario_id == "SCN-001"


# --- 2. BACKWARD COMPATIBILITY MAPPING ---

def test_load_scenario_legacy_mapping(tmp_path):
    file_path = tmp_path / "SCN-LEGACY.json"
    
    # Use expected_tools instead of required_tools and ground_truth instead of labels
    legacy_data = {
        "schema_version": "1.0",
        "scenario_id": "SCN-LEGACY",
        "incident_id": "INC-042",
        "ground_truth": {
            "affected_service": "checkout-service",
            "fault_category": "database_connection_pool",
            "root_cause_code": "DB_POOL_MAX_CONNECTIONS_REGRESSION",
            "root_cause_summary": "Legacy summary"
        },
        "expected_tools": ["log_pattern_search"],
        "forbidden_unsupported_causes": ["REDIS_OUTAGE"]
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(legacy_data, f)

    scenario, errors, warnings = load_scenario(file_path)
    assert errors == []
    assert scenario is not None
    assert scenario.required_tools == ["log_pattern_search"]
    assert scenario.labels.affected_service == "checkout-service"
    assert scenario.labels.forbidden_unsupported_cause_codes == ["REDIS_OUTAGE"]
    # Ensure fallbacks
    assert scenario.split == DatasetSplit.DEV
    assert scenario.ambiguity == ScenarioAmbiguity.UNAMBIGUOUS


# --- 3. VALIDATION FLOW AND ERRORS ---

def test_load_scenario_validation_errors(tmp_path):
    # Case A: Missing required fields
    file_path = tmp_path / "SCN-MISSING.json"
    data = {"schema_version": "1.0"} # missing scenario_id, incident_id
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
        
    scenario, errors, warnings = load_scenario(file_path)
    assert scenario is None
    assert any("Missing required field" in err for err in errors)

    # Case B: Pydantic Schema Violation
    file_path_invalid = tmp_path / "SCN-INVALID.json"
    invalid_data = create_mock_scenario_json("SCN-INVALID")
    invalid_data["split"] = "invalid_split_enum"
    with open(file_path_invalid, "w", encoding="utf-8") as f:
        json.dump(invalid_data, f)

    scenario, errors, warnings = load_scenario(file_path_invalid)
    assert scenario is None
    assert any("Schema validation failed" in err for err in errors)

    # Case C: Missing Evidence References
    dir_path = tmp_path / "SCN-REF-ERR"
    dir_path.mkdir()
    data = create_mock_scenario_json("SCN-REF-ERR", extra_fields={"required_evidence_ids": ["EV-999"]})
    with open(dir_path / "golden.json", "w", encoding="utf-8") as f:
        json.dump(data, f)
        
    # evidence.json exists but missing EV-999
    with open(dir_path / "evidence.json", "w", encoding="utf-8") as f:
        json.dump([{"evidence_id": "EV-1"}], f)

    scenario, errors, warnings = load_scenario(dir_path)
    assert scenario is not None  # it loaded, but validation caught the reference error
    assert any("Required evidence ID 'EV-999' not found" in err for err in errors)


# --- 4. DATASET DISCOVERY, ORDERING AND SUMMARIZATION ---

def test_load_dataset(tmp_path):
    # Create two scenarios: SCN-002 (as file) and SCN-001 (as directory)
    # They should be returned sorted deterministically: SCN-001, then SCN-002.
    
    # SCN-002 as file
    file_path = tmp_path / "SCN-002.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(create_mock_scenario_json("SCN-002"), f)

    # SCN-001 as directory
    dir_path = tmp_path / "SCN-001"
    dir_path.mkdir()
    with open(dir_path / "golden.json", "w", encoding="utf-8") as f:
        json.dump(create_mock_scenario_json("SCN-001"), f)

    scenarios, summary = load_dataset(tmp_path)
    
    assert summary.total_scenarios == 2
    assert summary.scenario_ids == ["SCN-001", "SCN-002"]
    
    # Ordering verification: SCN-001 must be first
    assert scenarios[0].scenario_id == "SCN-001"
    assert scenarios[1].scenario_id == "SCN-002"

    assert summary.split_counts == {"dev": 2}
    assert summary.ambiguity_counts == {"unambiguous": 2}


def test_empty_dataset(tmp_path):
    scenarios, summary = load_dataset(tmp_path)
    assert scenarios == []
    assert summary.total_scenarios == 0
    assert summary.scenario_ids == []


def test_duplicate_scenario_ids(tmp_path):
    # Write two different files declaring the same scenario_id SCN-DUP
    with open(tmp_path / "file1.json", "w", encoding="utf-8") as f:
        json.dump(create_mock_scenario_json("SCN-DUP"), f)
    with open(tmp_path / "file2.json", "w", encoding="utf-8") as f:
        json.dump(create_mock_scenario_json("SCN-DUP"), f)

    scenarios, summary = load_dataset(tmp_path)
    assert "SCN-DUP" in summary.validation_errors
    assert any("Duplicate scenario ID found" in err for err in summary.validation_errors["SCN-DUP"])


# --- 5. RUNNER INTEGRATION (ITERABLE SUPPORT) ---

def test_runner_evaluates_dataset_iterable():
    scenario1 = make_scenario_model("SCN-001")
    scenario2 = make_scenario_model("SCN-002")
    
    dataset = [scenario1, scenario2]
    
    # Evaluate list of scenarios
    results = evaluate_mock_graph(
        scenario=dataset,
        trace=None,
        predicted_rca=None
    )
    
    assert isinstance(results, list)
    assert len(results) == 2
    assert results[0].scenario_id == "SCN-001"
    assert results[1].scenario_id == "SCN-002"
    assert "EvaluationTrace is missing." in results[0].warnings
    assert "Predicted RCA is missing." in results[0].warnings


def make_scenario_model(scenario_id):
    from evals.schemas import GoldenRCALabels
    labels = GoldenRCALabels(
        affected_service="checkout-service",
        fault_category="database_connection_pool",
        root_cause_code="DB_POOL_MAX_CONNECTIONS_REGRESSION",
        root_cause_summary="Invalid pool limits."
    )
    return GoldenScenario(
        schema_version="1.0",
        scenario_id=scenario_id,
        incident_id="INC-001",
        split=DatasetSplit.DEV,
        ambiguity=ScenarioAmbiguity.UNAMBIGUOUS,
        expected_terminal_outcome=ExpectedTerminalOutcome.FINALIZE_RCA,
        acceptable_terminal_outcomes=[ExpectedTerminalOutcome.FINALIZE_RCA],
        labels=labels
    )
