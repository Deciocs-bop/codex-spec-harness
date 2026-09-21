# Codex Spec Harness

`codex-spec-harness` is a small, reusable governance layer for specifications of complex software projects. It keeps decisions, traceability, task context and evidence in versioned files so a new Codex session can resume work without treating chat history as the source of truth.

## What it enforces

- selective task context with an explicit word budget;
- unique decision IDs and explicit decision status;
- traceability from a source through a requirement, decision, contract and planned test;
- SHA-256 source manifests for change detection;
- distinct gates for specification, implementation and release;
- evidence-based completion: metadata alone cannot mark work implemented or released;
- concise canonical documents instead of duplicate status reports.

The harness is project-agnostic. The included example uses fictional data only.

## Quick start

```bash
python -m pip install -r requirements.txt
python -m harness.spec_harness validate --root examples/minimal
python -m harness.spec_harness context --root examples/minimal --task TASK-001
python -m harness.spec_harness hash --root examples/minimal
python -m unittest discover -s tests -p "test_*.py"
```

Copy `templates/` into a project, adapt `project-profile.yaml`, then create sources, decisions, traceability and task packets. Run validation in CI before merging documentation changes.

## Boundaries

This repository does not approve business decisions, implementation, tests or releases. A project owner records business approval in its decision log. Security, privacy and domain review remain project responsibilities.

## Layout

| Path | Purpose |
|---|---|
| `harness/` | CLI and validation rules |
| `templates/` | reusable starting files |
| `examples/minimal/` | a runnable synthetic example |
| `docs/` | design and operating guidance |
| `tests/` | harness regression tests |

## License

MIT. See [LICENSE](LICENSE).
