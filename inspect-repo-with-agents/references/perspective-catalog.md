# Perspective Catalog

Use this catalog only when choosing complementary agent assignments. Select perspectives that match the user's task and the repository shape; do not assign every category by default.

## Core Perspectives

- **Entry points and call flow**: Trace how the requested behavior enters the system and moves across modules.
- **Data and state**: Inspect schemas, persistence, serialization, migrations, caches, and state ownership.
- **Tests and validation**: Find relevant tests, missing edge cases, fixture gaps, and CI coverage.
- **Architecture and boundaries**: Check layering, module ownership, dependency direction, and duplicated responsibilities.
- **User-facing behavior**: Inspect CLI, API, UI, messages, compatibility, and observable behavior.
- **Failure modes**: Look for error handling, retries, partial failure, cleanup, and degraded states.

## Task-Specific Perspectives

- **Bug investigation**: Reproduction path, root-cause candidates, regression tests, adjacent behavior.
- **Feature impact**: Entry points, integration surfaces, data model impact, tests, docs or CLI/API changes.
- **Migration/refactor**: Compatibility boundaries, old/new behavior mapping, risky dependencies, cleanup leftovers.
- **Security**: Trust boundaries, input validation, secret handling, auth/authz, injection, unsafe deserialization.
- **Performance**: Hot paths, I/O patterns, batching, algorithmic complexity, caching, memory pressure.
- **Frontend**: Component state, responsive layout, accessibility, data loading, visual regressions.
- **Backend/API**: Request lifecycle, contracts, validation, persistence, concurrency, error responses.
- **Infrastructure/CI**: Build scripts, packaging, deployment config, env vars, check coverage, release risk.
- **Documentation/operability**: Setup instructions, runbooks, logging, observability, configuration clarity.

## Count Heuristics

- **3 agents**: code path, tests, risk/edge cases.
- **4 agents**: implementation path, data/contracts, tests, integration/operability.
- **5 agents**: architecture, behavior, data, tests, failure/security/performance.
- **6 agents**: split by clearly independent layers or runtimes; avoid creating a sixth agent just to meet a quota.
