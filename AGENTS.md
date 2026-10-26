# Rules for an AI agent working in this repo

This file is for coding agents (Claude Code reads it through `CLAUDE.md`, Codex and others read it directly).
The human-facing description is `README.md` (English) and `README.ru.md` (Russian).

## What this repo is

foureyes: an orchestration spec for LLM coding agents (`docs/SPEC.md`) plus a small engine (`lab/lab.py`) that refuses
any step where an agent judges its own work. Python stdlib plus PyYAML, Unix only (`fcntl`). No model calls inside.

## Layout

- `lab/lab.py`: the engine (CLI). `bin/foureyes` is a wrapper with the same arguments.
- `lab/chains.yaml`: stages and who may not judge whom. `lab/methods.yaml`: depths of the spec by task size.
- `lab/roles/*.md`: the brief each role gets. `lab/RULES.md`: the rules the engine enforces.
- `lab/envelope.py`: nonce envelope for untrusted text. `lab/evals/`: session-log miner and intake graders.
- `lab/ideas/`: four synthetic example ideas; `lab/board.json` is generated from them (`lab.py export`).
- `checks/check_lab.py`: re-validates stored idea files. `examples/walkthrough.sh`: one idea through the whole chain.
- `docs/`: the spec, how it works, the full walkthrough output, the diagram and social preview.

## Before you stop

Run all three; all must be green:

```
python3 -m unittest discover -s tests
python3 checks/check_lab.py
sh examples/walkthrough.sh > /dev/null
```

## Rules

1. Do not weaken a refusal in `lab.py done` or a finding in `check_lab.py` to make a test pass. A change to a rule goes into
   `lab/chains.yaml` or `lab/RULES.md` first, with a test that shows the new refusal.
2. `tests/test_examples.py` asserts exact refusal strings from the walkthrough. If you change a message, update the test,
   `docs/walkthrough.md` (paste the real new output) and the short transcript in both READMEs.
3. After you edit anything in `lab/ideas/`, run `python3 lab/lab.py export` so `lab/board.json` stays current.
4. Idea files are append-only history: never rewrite an earlier event; reopen a stage with `lab.py rerun`.
5. Keep the engine free of model calls and of dependencies beyond PyYAML.
6. Claims in the READMEs must match the code. Numbers from the private project the code was extracted from are labelled
   as such; do not add numbers that were not measured.
7. `README.md` and `README.ru.md` say the same thing. Change both, or say in your report that one is behind.
8. No hosts, IPs, private paths, personal or employer names, secret names or chat ids in any file.
