# Codex Spec Harness

`codex-spec-harness` is a small, reusable governance layer for specifications of complex software projects. It keeps decisions, traceability, task context and evidence in versioned files so a new Codex session can resume work without treating chat history as the source of truth.

## Recommended flow

```text
source → requirement → decision → contract → test → evidence → checkpoint
```

Each arrow is a versioned reference. The validator distinguishes an approved contract from a future contract, a planned test from an executed test, and documentary evidence from executed evidence. A requirement cannot claim `implemented` or `released` unless it references an approved contract, an executed test and executed evidence.

## Quick start

```bash
python -m pip install -r requirements.txt
python -m harness.spec_harness check --root examples/minimal
python -m harness.spec_harness context --root examples/minimal --task TASK-001
python -m harness.spec_harness dashboard --root examples/minimal --task TASK-001
python -m unittest discover -s tests -p "test_*.py"
```

`context` validates the selected packet before rendering it. It prints each selected source with its recorded SHA-256 and `updated: current`; a missing or changed source blocks rendering. The configured `context.max_words` budget is enforced with an error—content is never truncated silently.

`dashboard` renders a read-only end-of-round view with explicit progress bases, task counts, blockers, gates and resumption links. `close-round` validates and stores an immutable, idempotent snapshot in `rounds/`. See the [canonical round-dashboard rules](docs/dashboard-de-rodadas.md).

Use `hash` only after an owner has assessed a source change:

```bash
python -m harness.spec_harness hash --root examples/minimal
```

Refreshing a source manifest does not refresh evidence hashes or approve the change. UTF-8 source hashes normalize line endings so Windows and Linux checkouts do not create a false change; binary sources retain byte-for-byte hashes.

## Adopt in an existing project

Copy `templates/`, then create only the canonical artifacts needed for the first bounded scope: source manifest, decisions, contracts, tests, evidence, traceability and task packet. Start with future contracts and planned tests where implementation has not begun. Link task packets to those canonical files instead of pasting project history. Add `check` and unit tests to CI before merging documentation changes.

The included [synthetic example](examples/minimal/) has two dependent requirements and a [source-change scenario](examples/minimal/source-change-scenario.md).

For a beginner-friendly guide in Brazilian Portuguese, read the [user manual](docs/manual-do-usuario-pt-BR.md).

## What it enforces

- selective task context with an explicit word budget;
- unique IDs and references across decisions, requirements, contracts, tests and evidence;
- SHA-256 source manifests and evidence hashes for change detection;
- distinct gates for specification, implementation and release;
- evidence-based completion: metadata alone cannot mark work implemented or released;
- Markdown local-reference, empty-file and conservative secret-pattern checks;
- concise canonical documents instead of duplicate status reports.
- deterministic end-of-round dashboards and versioned, idempotent closure snapshots.

## Boundaries

This harness does not approve business decisions, security, implementation, real test execution or releases. A project owner must record business approval explicitly. Security, privacy, domain review, actual test runs and project governance remain human responsibilities.

## Layout

| Path | Purpose |
|---|---|
| `harness/` | CLI and validation rules |
| `templates/` | reusable starting files |
| `examples/minimal/` | runnable synthetic example |
| `docs/` | design, backlog and operating guidance |
| `tests/` | harness regression tests |

## License

MIT. See [LICENSE](LICENSE).
