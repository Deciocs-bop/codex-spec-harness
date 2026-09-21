# Scripts

Use the CLI instead of duplicating validation logic:

```bash
python -m harness.spec_harness check --root examples/minimal
python -m harness.spec_harness context --root examples/minimal --task TASK-001
python -m harness.spec_harness dashboard --root examples/minimal --task TASK-001
python -m harness.spec_harness dashboard --root examples/minimal --round-file examples/minimal/round-input.yaml
python -m harness.spec_harness close-round --root examples/minimal --round-file examples/minimal/round-input.yaml
python -m harness.spec_harness dashboard --root examples/minimal --round ROUND-001
python -m harness.spec_harness hash --root examples/minimal
```
