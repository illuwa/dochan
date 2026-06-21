# Releasing dochan

## Stable release checklist

1. Update version in:
   - `pyproject.toml`
   - `dochan/__init__.py`
2. Update `CHANGELOG.md`.
3. Run validation:
  - `uv run python -m pytest tests/`
   - `uv run --with build python -m build`
   - `uv run --with twine python -m twine check dist/*`
4. Commit changes and create tag:
   - `git tag v1.0.0`
   - `git push origin v1.0.0`
5. Pushes with `vX.Y.Z` tags trigger `.github/workflows/pypi-release.yml`.
