# Rules of the Lab

The Lab is a small harness of its own. These rules are enforced by `lab/lab.py` when a stage is closed and re-checked over
the stored files by `checks/check_lab.py`, not by good intentions.

1. One idea is one file `lab/ideas/<id>.yaml`. Anyone (the owner, an orchestrator thread, a scout agent) may submit one; nobody is asked first.
2. An idea walks the stages of `lab/chains.yaml` in order. A stage is closed with `lab.py done`; the event is appended to the idea and never edited. A stage is reopened only with `lab.py rerun`, which appends a reopen event.
3. Writer and judge differ: the agent that tests, applies or validates is not the agent that built (validate also differs from test and apply); the submitter does not triage, and the triage agent does not test, apply or validate. The machine compares agent ids; it cannot prove an agent is fresh.
4. `apply` and `validate` need a real commit of this repo as evidence, reachable from origin/main (HEAD only where no origin/main exists) and committed after the idea was submitted; the two commits of one idea must differ. A test or validate that fails sends the idea back to `build`; the third failure drops it.
5. Anything that needs the owner's yes (services, money, messages, production, deletion) is parked at triage with `needs_yes`; the chain stops there until the yes is recorded in the idea (`approved_by_user`, a reference to the owner's message plus the owner's words). `lab.py approve` also appends an `approve` event holding a hash of the idea text and its earlier events; if the idea or those events change afterwards, `done` refuses and the check fails until the owner approves again.
6. The method role states the size S/M/L (`docs/SPEC.md` section 2) and picks the depth from `lab/methods.yaml` by section 8 of that spec; OpenSpec is the depth of size L. Retro scores how the depth worked at its size; `lab.py methods` prints the score per method.
7. Costs are written only when measured (`--cost`); unknown is not zero.
8. Intake gate: every idea needs a confirmation, either `--url` (an https link) or `--code PATH[:LINE]` (a file, and line, that exist in this repo). The owner (`--by owner`, or a name listed in env `LAB_OWNERS`) is exempt; any other submitter without one is stored with `unconfirmed: true`, and triage cannot pass it (`go`) until someone adds a confirmation with `lab.py confirm` (appended to `confirmations`, history is never edited). One `--by` may submit at most 10 ideas per UTC hour (env `LAB_SUBMIT_LIMIT`), counted from `submitted_at`.
9. Text an agent reads from an idea file is untrusted: `lab.py brief` hands it to the role inside a nonce envelope (`lab/envelope.py`), after the rules.
10. The Lab changes the repo only through commits to main that pass the repo hooks; it never bypasses them.
