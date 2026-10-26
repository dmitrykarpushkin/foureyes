# Changelog

All notable changes to this project. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- Renamed from agent-lab to foureyes; links point to the sibling repos stopline and needsyou.
- README rewritten for people, with a full Russian version (`README.ru.md`), a diagram and an honest comparison.
- Rules for coding agents moved to `AGENTS.md` (`CLAUDE.md` imports it); reference material moved to `docs/`.

### Added
- `bin/foureyes`, a short name for `python3 lab/lab.py`.
- CI workflow that runs the tests, the stored-file check and the walkthrough.

## [0.1.0] - 2026-10-26

First public release, extracted from a private monorepo (see "Before public release" for where the parts came from).

### Added
- The engine `lab/lab.py`, its rules `lab/RULES.md`, the chain `lab/chains.yaml`, the depths `lab/methods.yaml` and
  the role briefs `lab/roles/`.
- `checks/check_lab.py`, `lab/envelope.py`, `lab/evals/` (session-log miner and intake graders), `docs/SPEC.md`.
- `examples/walkthrough.sh` and four synthetic example ideas; 61 tests.

## Before public release

Milestones in the private monorepo, with the dates of the commits that made them. That history is not published.

- 2026-10-19: the engine. Ideas walk a chain of roles; the submitter and the triage agent may not judge their own idea;
  apply and validate need reachable, different commits; one lock per idea file; `rerun` and `stale` commands; the
  `ears-spec` and `speckit` depths.
- 2026-10-19: owner approvals bound by a hash to the exact idea and events they approved.
- 2026-10-19: untrusted text wrapped in an envelope with source, trust tier and a random nonce; `lab.py brief` uses it.
- 2026-10-19: intake gate (an idea needs an https link or a code location) and a per-submitter hourly limit.
- 2026-10-20: evidence commits must be newer than the idea and on `origin/main`; the check accepts HEAD ancestors.
- 2026-10-21: evals from agent logs: a mechanical session-log pass with tests and a first measurement of the filter's
  accuracy; deterministic graders for the intake eval.
- 2026-10-21: the orchestrator spec: first draft with every rule tied to a source or marked "our rule", two review rounds.
- 2026-10-26: review rules in the spec: a finding goes on only when two fresh agents confirm it; at most 3 rounds.

[Unreleased]: https://github.com/dmitrykarpushkin/foureyes/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/dmitrykarpushkin/foureyes/releases/tag/v0.1.0
