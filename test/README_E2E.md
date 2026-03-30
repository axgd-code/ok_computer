# E2E Test Suites

This repository now includes two complementary E2E BDD suites:

1. UI Browser E2E (Playwright):
- Feature: test/features/ui_playwright.feature
- Steps: test/test_ui_playwright_bdd.py
- Scope: tabs navigation + core UI actions (settings, system settings, search, extensions)

2. Full API Matrix BDD:
- Feature: test/features/api_complete_coverage.feature
- Steps: test/test_api_complete_bdd.py
- Scope: end-to-end route coverage by endpoint group with isolated filesystem and mocked externals

## Run

```bash
source .venv/bin/activate
pytest -q test/test_api_complete_bdd.py
pytest -q test/test_ui_playwright_bdd.py
```

Notes:
- UI Playwright tests auto-skip when Playwright or browser binaries are unavailable.
- API BDD suite is deterministic and does not execute system-modifying scripts.
