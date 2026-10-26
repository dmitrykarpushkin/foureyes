#!/usr/bin/env python3
"""Check lab-chain: every idea of the Lab follows lab/chains.yaml; the judge differs from the builder; the board data is current.

  python3 checks/check_lab.py [ROOT]     prints one line per problem, exit 1 when there is any

`lab.py done` refuses a bad step when it is taken; this check re-reads the stored files, so a hand edit of an idea file
(a changed agent id, a dropped event, a forged approval) is caught afterwards. Problems: unknown state, stage or verdict, a judge
that also worked on a stage it must differ from, apply or validate ok without a real commit, an unknown method, a parked
idea that is not waiting for a yes, events out of chain order or with earlier stages missing, a stage that does not match
the last event, an approval whose hash no longer matches, an unconfirmed idea passed by triage, malformed confirmation
fields, and lab/board.json that differs from what lab/lab.py export would write now.
The machine compares agent ids; it cannot prove an agent was fresh or that a note is true.
"""
import json, os, pathlib, sys
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lab"))
import lab  # noqa: E402

STATES = {"active", "parked", "dropped", "done"}
KEYS = ("id", "title", "module", "state", "stage", "events", "submitted_by", "submitted_at")


def check_order(name, idea, stages):
    """Events must walk lab/chains.yaml in order; a fail goes back to build; the idea stage must match the last event."""
    ids = [s["id"] for s in stages]
    if any(e.get("stage") not in ids for e in idea["events"]):
        return []  # the unknown stage is reported elsewhere
    out, expected = [], 0
    for n, e in enumerate(idea["events"], 1):
        k, v = ids.index(e["stage"]), e.get("verdict")
        if v == "reopen":
            if expected is None or k > expected:
                out.append(f"{name}: event {n} reopens {e['stage']}, which the chain has not reached")
                break
            expected = k
            continue
        if v == "approve":
            prev = idea["events"][n - 2] if n > 1 else {}
            if prev.get("stage") != "triage" or e.get("to_stage") not in ids:
                out.append(f"{name}: event {n} is an approval that does not follow triage or has no valid to_stage")
                break
            expected = ids.index(e["to_stage"])
            continue
        if expected is None:
            out.append(f"{name}: event {n} ({e['stage']}) comes after the chain ended")
            break
        if k != expected:
            out.append(f"{name}: event {n} is stage {e['stage']} but the chain expects {ids[expected]} (earlier stages missing or out of order)")
            break
        if e["stage"] == "triage":
            expected = 0 if v == "park" else (None if v == "drop" else 1)
        elif v == "fail":
            expected = ids.index("build")
        else:
            expected = k + 1 if k + 1 < len(ids) else None
    else:
        if idea["state"] in ("active", "parked"):
            want = ids[expected] if expected is not None else None
            if idea["stage"] != want:
                out.append(f"{name}: stage is {idea['stage']!r} but the events lead to {want!r}")
    return out


def check_idea(root, idea, stages, methods, is_commit, name="idea"):
    out = []
    miss = [k for k in KEYS if k not in idea]
    if miss:
        return [f"{name}: missing {', '.join(miss)}"]
    if idea["id"] != name:
        out.append(f"{name}: id {idea['id']!r} differs from the file name")
    if idea["state"] not in STATES:
        out.append(f"{name}: unknown state {idea['state']!r}")
    by_id = {s["id"]: s for s in stages}
    if idea["state"] in ("active", "parked") and idea["stage"] not in by_id:
        out.append(f"{name}: unknown stage {idea['stage']!r}")
    if idea["state"] in ("dropped", "done") and idea["stage"] is not None:
        out.append(f"{name}: a {idea['state']} idea has no stage")
    if idea["state"] == "parked" and not idea.get("needs_yes"):
        out.append(f"{name}: parked but needs_yes is false")
    if idea.get("method") is not None and idea["method"] not in methods:
        out.append(f"{name}: unknown method {idea['method']!r}")
    if "unconfirmed" in idea and not isinstance(idea["unconfirmed"], bool):
        out.append(f"{name}: unconfirmed must be true or false")
    if idea.get("confirmation") is not None and not (isinstance(idea["confirmation"], str) and idea["confirmation"].startswith(("https://", "code:"))):
        out.append(f"{name}: confirmation must be an https link or code:PATH[:LINE]")
    cons = idea.get("confirmations", [])
    if not isinstance(cons, list) or any(not (isinstance(c, dict) and c.get("by") and c.get("value") and c.get("ts")) for c in cons):
        out.append(f"{name}: confirmations must be a list of {{ts, by, value}}")
    seen = []
    for n, e in enumerate(idea["events"], 1):
        st = by_id.get(e.get("stage"))
        if not st:
            out.append(f"{name}: event {n} has unknown stage {e.get('stage')!r}")
            continue
        if e.get("verdict") not in st["verdicts"] + ["reopen", "approve"]:
            out.append(f"{name}: event {n} ({st['id']}) has verdict {e.get('verdict')!r}")
        if e.get("verdict") == "approve":
            if e.get("idea_hash") != lab.approval_hash(idea, seen):
                out.append(f"{name}: event {n} approval hash does not match the idea and events it approved")
            seen.append(e)
            continue
        if e.get("verdict") != "reopen" and e.get("agent") in lab.barred(idea, st, seen):
            out.append(f"{name}: event {n} ({st['id']}) is by {e.get('agent')}, who also worked on a stage it must differ from")
        if st.get("evidence") == "commit" and e.get("verdict") == "ok" and not (e.get("evidence") and is_commit(root, e["evidence"])):
            out.append(f"{name}: event {n} ({st['id']}) ok without a commit of this repo as evidence")
        if st.get("evidence") == "commit" and e.get("verdict") == "ok" and e.get("evidence") and is_commit(root, e["evidence"]):
            if not lab.is_reachable(root, e["evidence"], strict=False):
                out.append(f"{name}: event {n} ({st['id']}) evidence is not reachable from origin/main or the checked HEAD")
            elif not lab.is_new(root, idea, e["evidence"]):
                out.append(f"{name}: event {n} ({st['id']}) evidence is older than the idea")
            elif lab.evidence_clash(root, dict(idea, events=seen), st["id"], e["evidence"]):
                out.append(f"{name}: event {n} ({st['id']}) evidence is the same commit as the other of apply and validate")
        if st["id"] == "triage" and e.get("verdict") in ("go", "ok") and lab.is_unconfirmed(idea):
            out.append(f"{name}: event {n} (triage) passed an idea that is still unconfirmed")
        cost = e.get("cost_usd")
        if cost is not None and not (isinstance(cost, (int, float)) and cost >= 0):
            out.append(f"{name}: event {n} has a bad cost")
        seen.append(e)
    return out + check_order(name, idea, stages)


def run(root=ROOT):
    root = pathlib.Path(root)
    if not (root / "lab" / "chains.yaml").is_file():
        return [f"{root}: no lab/chains.yaml"]
    stages, methods = lab.chain(root), lab.methods(root)
    out = []
    d = root / "lab" / "ideas"
    for f in sorted(d.glob("*.yaml")) if d.is_dir() else []:
        try:
            idea = yaml.safe_load(f.read_text())
        except yaml.YAMLError as e:
            out.append(f"{f.name}: not valid yaml ({e})")
            continue
        if not isinstance(idea, dict):
            out.append(f"{f.name}: not a mapping")
            continue
        out += check_idea(root, idea, stages, methods, lab.is_commit, f.stem)
    page = root / "lab" / "board.json"
    want = json.dumps(lab.export_data(root), indent=1, ensure_ascii=False) + "\n"
    if not page.is_file() or page.read_text() != want:
        out.append("lab/board.json is not current: run python3 lab/lab.py export")
    return out


if __name__ == "__main__":
    problems = run(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LAB_ROOT") or ROOT)
    for p in problems:
        print(p)
    print(f"check_lab: {len(problems)} problem(s)")
    sys.exit(1 if problems else 0)
