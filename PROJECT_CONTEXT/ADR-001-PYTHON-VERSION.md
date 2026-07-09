# Architecture Decision Record (ADR-001) — Python Runtime Version
**Status:** Decided / Pending Phase 7 Standardization  
**Execution Date:** 2026-07-08  
**Author:** Antigravity (AI Coding Assistant)  

---

## 1. Current State
The local development and testing environment is currently running Python 3.14.0 on Windows. 
The production container configuration (as specified in the `Dockerfile`) is pinned to `python:3.11-slim-bookworm` (Python 3.11).

---

## 2. Risk & Impact Analysis
As we transition from telemetry repositories and knowledge layers to integration with LLM Gateway, NeMo Guardrails, and evaluation frameworks (e.g. `deepeval`, `ragas`), running Python 3.14 introduces several critical compatibility risks:
1.  **Library Compatibility**: Heavy dependency packages such as `nemoguardrails`, `ragas`, `deepeval`, `torch`, and native libraries (like `pyppeteer` or `pydantic` extensions) do not yet have stable, pre-compiled wheels or compatibility support for Python 3.14.
2.  **Windows Sandbox Compilation Issues**: Attempting to compile native C++ extensions for uncompiled Python 3.14 wheels on Windows causes installation timeouts and failures in sandbox environments.
3.  **Environment Mismatches**: Local execution on Python 3.14 might hide bugs or runtime behavior differences that would fail inside the production Python 3.11 container.

---

## 3. Decision & Guidelines
We will maintain the current dual-setup for the remainder of Phase 5 closeout:
*   Local development is allowed on Python 3.14 using offline mocks for incompatible libraries.
*   Production target remains Python 3.11.

### Mandatory Action Before Phase 7 Implementation:
1.  **Standardize Python Runtime**: The engineering team must select and standardize a single supported Python runtime (recommended: **Python 3.11** or **Python 3.10**) for both local development and production.
2.  **CI/CD Alignment**: Configure CI workflows (such as GitHub Actions) to run tests under the selected python runtime version.
3.  **Environment Synchronization**: Re-create local virtual environments using the chosen Python version to ensure all packages (including NeMo Guardrails and evaluation frameworks) install natively and run without compilation issues.
