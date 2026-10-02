# Releasing dochan

## Stable release checklist

1. Set the intended release version and update it in every source location:
   ```bash
   export DOCHAN_VERSION=1.0.3  # replace with the intended release version
   ```
   - `pyproject.toml`
   - `dochan/__init__.py`
   - the stable-version label in `README.md` (`Current stable version: X.Y.Z`, checked by `tests/test_release_contracts.py`)
   - `uv.lock` (the `dochan` package entry). Re-lock with the uv version pinned in CI (`uv==0.12.3`):
     `uv lock` then `uv lock --check`. A stale lock makes `--locked` fail in CI.
2. Update `CHANGELOG.md` (move `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD`).
3. Run local validation:
   ```bash
   export DOCHAN_DIST_DIR="$(mktemp -d)"
   uv run --isolated --locked --extra dev ruff check dochan scripts tests
   uv run --isolated --locked --extra dev python -m pytest tests/
   # Maintainer-only: requires the local secaudit installation.
   uv run --isolated --locked --extra dev python \
     scripts/run_tracked_security_audit.py
   uv run --isolated --with build==1.5.0 python -m build \
     --outdir "${DOCHAN_DIST_DIR}"
   uv run --isolated --with twine==7.0.0 python -m twine check \
     "${DOCHAN_DIST_DIR}"/*
   uv run --isolated --locked --extra dev python \
     scripts/verify_release_version.py \
     --tag "v${DOCHAN_VERSION}" \
     --wheel "${DOCHAN_DIST_DIR}"/*.whl
   ```
4. Before the first release, configure the GitHub `pypi` environment:
   - restrict deployments to release tags;
   - require the desired reviewers;
   - store the scoped PyPI token as the environment secret `PYPI_API_TOKEN`.
5. Commit the release changes on the working branch, push it and confirm the pull request CI (Python 3.9–3.13 and the
   security gates) is green. Fast-forward `main` to the branch (`git push origin HEAD:main`), then create and push the
   matching tag:
   ```bash
   git tag -a "v${DOCHAN_VERSION}" -m "Release ${DOCHAN_VERSION}"
   git push origin "v${DOCHAN_VERSION}"
   ```
6. `vX.Y.Z` tags trigger `.github/workflows/pypi-release.yml`. Publishing waits for the full Python matrix and all security gates, then re-validates the tag, source versions, and wheel `METADATA` before upload.
