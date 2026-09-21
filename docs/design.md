# Design

The validator is deliberately small. YAML holds structured facts, Markdown holds narrative decisions, and hashes make a source change visible. The validator rejects a requirement that claims implementation or release without executed evidence. It does not attempt to determine business truth.

Task packets are compact, owned by a single task and rendered on demand. They should link to canonical sources instead of embedding the full project history.
