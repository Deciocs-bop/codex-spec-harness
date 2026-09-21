# Agent rules

1. Read the project profile, current status and only the decisions relevant to the task before editing.
2. Edit the canonical artifact; link to an existing rule instead of copying it.
3. Record scope, owner, dependencies, acceptance criteria, blockers, autonomy limits and open decisions in the task packet.
4. Keep source, requirement, decision, contract, test and evidence references explicit and versioned.
5. Never infer business approval, implementation, test execution or release from a document label or metadata field. An `implemented` or `released` requirement needs an approved contract, executed test and executed evidence.
6. Keep task context within the configured budget. If a source changes, assess its impact before refreshing a hash or evidence record.
7. Run `python -m harness.spec_harness check --root <project-root>` before declaring a task complete.
8. Do not store secrets, credentials, personal data or production payloads in examples, logs or fixtures.

Specification approval, implementation readiness and release readiness are separate gates.
