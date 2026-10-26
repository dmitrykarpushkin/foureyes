# lab

```yaml
id: "lab"
purpose: "The Lab: one idea starts a chain of roles (triage, method, build, test, apply, validate, retro) where the author and the judge differ."
owner: "agents of the orchestrator (writer and verifier differ)"
lives: "repo only; agents pull work with lab.py next and report with lab.py done; nothing runs as a service"
may_touch: ["lab.py", "envelope.py", "chains.yaml", "methods.yaml", "RULES.md", "roles/", "ideas/", "board.json", "evals/"]
must_not_touch: ["services, money, messages to people, production without the owner's yes"]
health:
  state: warn
  note: "engine, check and tests pass; no chain has been run end to end by independent agents at scale"
```

Entry points are in the docstring of `lab.py`; the rules in `RULES.md`; the stages and who may judge whom in `chains.yaml`;
the depths of the spec in `methods.yaml`. `evals/` mines agent session logs for eval cases and grades intake trials.
