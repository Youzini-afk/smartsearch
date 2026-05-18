# src/

## Responsibility

Python package source root. Contains the installable `smart_search` package that implements all application behavior behind the `smart-search` command.

## Design

- Uses setuptools `src` layout as configured by `pyproject.toml` (`[tool.setuptools.packages.find] where = ["src"]`).
- Keeps runtime logic under one top-level package, `smart_search`, with package data for bundled AI-agent skills.
- Exposes the CLI through `pyproject.toml` console script: `smart-search = "smart_search.cli:main"`.

## Flow

1. Python package installation discovers packages under `src/`.
2. Console script or npm wrapper imports `smart_search.cli`.
3. `cli.main()` dispatches into the core service/provider/config modules.

## Integration

- Parent packaging: `pyproject.toml` defines package discovery, dependencies, package data, and console script.
- npm wrapper: `npm/bin/smart-search.js` executes `python -m smart_search.cli`, relying on this package being installed into `.smart-search-python/`.
- Detailed package map: [`src/smart_search/codemap.md`](smart_search/codemap.md).
