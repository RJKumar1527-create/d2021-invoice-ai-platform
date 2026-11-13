# Automated Test Suite

Copy the `tests` folder, `pytest.ini`, and `requirements-test.txt` into the project root.

Run:

```powershell
python -m pip install -r requirements-test.txt
python -m pytest
```

The suite verifies SQLite persistence, audit history, required project files, Python syntax, knowledge-base schema, holdout evaluation markers, masking controls, and `.gitignore` protections.
