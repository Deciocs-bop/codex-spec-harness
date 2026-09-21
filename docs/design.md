# Design

The validator is deliberately small. YAML stores structured references and Markdown stores concise decision narratives. Source manifests and evidence hashes make a source change visible without treating a hash refresh as an approval. UTF-8 text hashes normalize line endings; binary sources use their original bytes.

A requirement references one source, approved decision, contract, test and evidence. Contracts are `approved` or `future`; tests are `planned` or `executed`; evidence is `documentary` or `executed`. `implemented` and `released` requirements need the approved/executed combination. These states describe evidence only and do not establish business truth.

Task packets are compact, owned by a single task and rendered on demand. Before rendering, the CLI validates the packet fields, source hashes, decision and requirement references, and the configured word budget. It renders no partial or truncated context.

`check` combines specification validation with simple content hygiene: non-empty text files, local Markdown file references and conservative secret patterns. It reports paths and issue types only; it never prints a suspected secret.
