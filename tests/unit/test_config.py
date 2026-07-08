from app.config import settings

def test_settings_load():
    assert settings.WORKSPACE_DIR.exists()
    assert settings.SCENARIO_DIR.exists()
    assert settings.GENERATED_DATA_DIR.exists()
    assert settings.QDRANT_COLLECTION == "opsgraph_knowledge"
    assert settings.MAX_TOOL_CALLS == 8
    assert settings.MAX_GRAPH_DEPTH == 15
