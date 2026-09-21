# Source-change scenario

The source manifest and each documentary evidence record bind `sources/source.md` to its SHA-256 digest. Change the source without updating those records, then run `python -m harness.spec_harness validate --root examples/minimal`.

Validation reports `source_changed` and `evidence_source_changed`. Refreshing the manifest with `hash` is intentionally insufficient: an owner must assess the affected requirements and refresh or replace the evidence deliberately.
