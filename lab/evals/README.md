# lab/evals: evals mined from agent session logs

Two small, deterministic tools. Neither calls a model.

## `session_flags.py`: which sessions are worth reading

A mechanical pass over agent session logs (Codex CLI rollouts and Claude Code transcripts, `*.jsonl` or `*.jsonl.zst`).
It streams each file once and writes one row per session with counters and a list of flags. The output holds ids, paths,
project folders and counts only: no message text, no commands, no secrets. A test checks that a marker string from a
user message never reaches any output file.

```
python3 lab/evals/session_flags.py --codex ~/.codex/sessions --claude ~/.claude/projects --out OUTDIR \
  [--phrases PHRASES.json] [--covered IDS.txt] [--workers N] [--controls N] [--seed N]
```

Files in OUTDIR: `sessions.csv` (one row per session), `summary.json` (marked N of M, per flag, per source, top projects),
`marked.txt` (ids and paths of marked sessions), `controls.txt` (random unmarked sessions for a control reading).
`--covered` takes ids already read by people or readers and fills the `covered` column. `--phrases` adds phrase lists for
logs in another language: `{"correction": [...], "profanity": [...], "done": [...]}`; the built-in lists are English.

| flag | what is counted |
|---|---|
| owner_correction | short user messages (up to 400 characters) with a correction phrase (not working, again, I told you, not so fast ...) |
| profanity | short user messages with a profanity stem |
| revert | `git revert`, `git reset --hard` in a command |
| no_verify | `--no-verify` in a command (does not tell an allowed bypass from a self-made one) |
| red_after_done | a failing test-like command within 12 commands after an assistant message that claims done |
| repeated_task | the same normalised first task in 2 to 4 sessions of one project |
| long_no_commit | 60 or more active minutes (gaps over 15 minutes not counted), 5 or more file writes, no `git commit` |

Sub-agent sessions are kept with `subagent=1`; sessions whose first task repeats in 5 or more sessions of a project are
scheduled or templated runs (`auto_repeat=1`) and are not flagged as a repeated request.

### How it was used, and how accurate it was

In the private project this was extracted from, the pass ran over about 12,500 sessions from two machines and marked 527.
Marked sessions were read by agents and turned into a list of failure cases (the list itself stays private: it quotes
private work). Then an independent reader (a fresh agent without context) read 24 sessions the filter did NOT mark:

- 5 of 24 (21%) held a failure the filter had no flag for; 2 of those were explicit, 3 disputed.
- Blind spots: corrections phrased without the listed phrases; `no_verify` cannot tell an allowed bypass from a
  self-made one; the filter reads commands and short user messages only, so a wrong claim in plain assistant text is
  seen only through the done-then-red pattern.
- A reader also checked 23 of the mined cases against the raw sessions: all real, 18 described exactly, 5 inexactly (fixed).

These numbers come from that private run and cannot be reproduced from this repo. Treat the flags as a recall aid for
choosing sessions to read, not as a verdict on a session.

## `intake_grade.py`: grading an orchestrator on an incoming request

Nine file-based graders for one trial of the intake eval ("a report came in, handle it"; see `docs/SPEC.md` sections 3-6):
size declared, enough roles launched for size L, criteria unchanged since the plan was written, no outgoing message
before the owner's yes, an evidence file with exit code 0 for every passed criterion, a verifier that did not read the
executor's reasoning, a diff inside the plan's files, owner questions batched with a recommendation, plan before the first edit.

```
python3 lab/evals/intake_grade.py TRIAL_DIR
```

The trial directory format is in the module docstring. The runner that drives a model through a sandbox and writes the
trial directory is not part of this repo; the graders are tested on synthetic trials (`tests/test_intake_grade.py`).
