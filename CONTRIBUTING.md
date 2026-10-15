# Contributing

Use a focused issue and pull request. Explain the concrete failure and the supported behavior. Include a minimal synthetic fixture rather than private experimental data.

```
python -m venv .venv
# Activate the environment with your shell's usual command.
python -m pip install -e '.[dev]'
ruff check .
pytest -q
python -m build
python -m twine check dist/*
```

The required `quality` check aggregates the operating-system/Python matrix. Main requires a pull request, resolved conversations, and passing checks. Independent agent reviews used during initial development are recorded as such, not represented as human customer validation or separate GitHub approvals.

A new dependency mechanism must define its path-resolution semantics, root/symlink boundary, failure behavior and post-relocation acceptance test. Preserve `schema_version` compatibility or introduce an explicit new version. Never change an existing HDF5 input to make an audit pass.
