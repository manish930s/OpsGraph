import os
import pytest

def pytest_collection_modifyitems(config, items):
    """
    Skip all live_api marked tests unless RUN_LIVE_TESTS=true is set.
    This runs at collection time after all modules are imported, so it
    correctly reads the environment variable set before pytest was launched.
    """
    run_live = os.environ.get("RUN_LIVE_TESTS", "").lower() in ("true", "1", "yes")
    if not run_live:
        skip_live = pytest.mark.skip(reason="Live API tests not enabled. Set RUN_LIVE_TESTS=true to run them.")
        for item in items:
            if item.get_closest_marker("live_api"):
                item.add_marker(skip_live)
