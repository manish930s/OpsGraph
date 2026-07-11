import json
from pathlib import Path
from evals.schemas import DatasetEvaluationResult


def export_dataset_result_json(result: DatasetEvaluationResult, output_path: str | Path) -> None:
    """
    Exports a DatasetEvaluationResult object to a deterministic, formatted JSON file.
    Ensures stable sort keys and standardized 2-space indentation.
    """
    path = Path(output_path)
    # Ensure parent directories exist
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Safe model dump through Pydantic's JSON representation
    data_dict = json.loads(result.model_dump_json())
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data_dict, f, indent=2, sort_keys=True)
