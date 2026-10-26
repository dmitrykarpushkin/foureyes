#!/usr/bin/env python3
"""Mechanical pass over agent session logs: per-session signals, no model, no message text in the output.

Usage:
  session_flags.py --codex DIR --claude DIR --out DIR [--phrases FILE] [--covered FILE] [--workers N] [--controls N] [--seed N]

Reads every *.jsonl under the two roots (Codex rollouts, Claude Code transcripts), streams each file once and writes
  sessions.csv   one row per session: id, path, project, counters and the flags list (counts only)
  summary.json   marked N of M (all and without sub-agent sessions), per flag, per source, per project
  marked.txt     the ids of the marked sessions
  controls.txt   random unmarked sessions for a control reading (id and path)
No message or command text is written. Signals: owner corrections (short user messages with phrases or profanity),
reverts, --no-verify, red tests after a done claim, the same first task repeated, long active work without a commit.
Phrase lists are English; --phrases FILE adds lists for other languages (see build_patterns).
"""
import argparse
import csv
import hashlib
import json
import multiprocessing
import os
import random
import re
import subprocess
import sys
from contextlib import contextmanager
from collections import Counter, defaultdict
from datetime import datetime

# Phrase lists are English by default. Logs in another language need their own lists: pass --phrases FILE, a JSON object
# with any of the keys "correction", "profanity", "done" (lists of lowercase phrases) that are added to the defaults.
CORR_EN = ["doesn't work", "does not work", "not working", "still broken", "i told you", "again", "not so fast",
           "that's wrong", "that is wrong", "i did not ask", "i didn't ask", "where is the report", "too long"]
# profanity stems, matched at a word start
PROF_EN = ["wtf", "fuck", "shit", "damn it", "bullshit"]
# done claims
DONE_EN = ["done", "all tests pass", "tests pass", "fixed", "complete", "completed", "works now", "ready"]


def build_patterns(extra=None):
    """Compile the correction, profanity and done patterns from the defaults plus the extra phrase lists."""
    global CORR_RE, PROF_RE, DONE_RE
    extra = extra or {}
    corr = CORR_EN + [p.lower() for p in extra.get("correction", [])]
    prof = PROF_EN + [p.lower() for p in extra.get("profanity", [])]
    done = DONE_EN + [p.lower() for p in extra.get("done", [])]
    CORR_RE = re.compile("|".join(r"\b" + re.escape(p) + r"\b" for p in corr), re.UNICODE)
    PROF_RE = re.compile("|".join(r"\b" + re.escape(p) for p in prof), re.UNICODE)
    DONE_RE = re.compile("|".join(r"\b" + re.escape(p) + r"\b" for p in done), re.UNICODE)


build_patterns()
TEST_RE = re.compile(r"pytest|unittest|npm (run )?test|pnpm (run )?test|yarn test|vitest|jest|go test|cargo test|run_all|make test|\btsc\b|eslint|ruff|mypy|bun test|playwright test")
REVERT_RE = re.compile(r"\bgit\s+revert\b|\bgit\s+reset\s+--hard\b")
DISCARD_RE = re.compile(r"\bgit\s+checkout\s+--\s|\bgit\s+restore\s|\bgit\s+stash\s+drop\b|\bgit\s+clean\s+-[a-z]*f")
NOVERIFY_RE = re.compile(r"--no-verify")
COMMIT_RE = re.compile(r"\bgit\s+commit\b(?!.*--dry-run)")
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
CORR_MAX_LEN = 400          # longer user messages are pasted logs or task prompts, not a correction
DONE_WINDOW = 12            # commands after a done claim in which a red test counts
LONG_MINUTES = 60           # active minutes (gaps over 15 minutes are not counted) without a commit
LONG_MIN_WRITES = 5
GAP_MINUTES = 15
AUTOMATED_MIN_GROUP = 5     # the same first task in this many sessions of one project is automation, not a repeated request


@contextmanager
def opener(path):
    """Lines of a log file; .zst files are streamed through the zstd binary."""
    if path.endswith(".zst"):
        proc = subprocess.Popen(["zstd", "-dc", path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            yield (b.decode("utf-8", "ignore") for b in proc.stdout)
        finally:
            proc.stdout.close()
            proc.wait()
    else:
        with open(path, errors="ignore") as fh:
            yield fh


def norm(text):
    return text.lower()


def parse_ts(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def text_of(content):
    """Plain text of a message content: a string, or a list of blocks with text/input_text."""
    if isinstance(content, str):
        return content
    out = []
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict):
                t = b.get("text")
                if isinstance(t, str):
                    out.append(t)
    return "\n".join(out)


def is_real_user_text(text):
    s = text.strip()
    return bool(s) and not s.startswith("<") and not s.startswith("[Request interrupted") and not s.startswith("Caveat:")


class Acc:
    """Event accumulator for one session; the same logic for both log formats."""

    def __init__(self):
        self.users = 0
        self.corr_msgs = 0
        self.corr_total = 0
        self.prof_msgs = 0
        self.reverts = 0
        self.discards = 0
        self.no_verify = 0
        self.commits = 0
        self.writes = 0
        self.commands = 0
        self.red_after_done = 0
        self.first_task = None
        self.times = []
        self.pending_done = []      # commands left in the window for each recent done claim

    def stamp(self, ts):
        if ts is not None:
            self.times.append(ts)

    def user(self, text):
        if not is_real_user_text(text):
            return
        self.users += 1
        if self.first_task is None:
            self.first_task = text
        if len(text) <= CORR_MAX_LEN:
            n = norm(text)
            hits = CORR_RE.findall(n)
            if hits:
                self.corr_msgs += 1
                self.corr_total += len(hits)
            if PROF_RE.search(n):
                self.prof_msgs += 1

    def assistant(self, text):
        if text and DONE_RE.search(norm(text)):
            self.pending_done.append(DONE_WINDOW)

    def command(self, cmd, failed):
        self.commands += 1
        if REVERT_RE.search(cmd):
            self.reverts += 1
        if DISCARD_RE.search(cmd):
            self.discards += 1
        if NOVERIFY_RE.search(cmd):
            self.no_verify += 1
        if COMMIT_RE.search(cmd):
            self.commits += 1
        keep = []
        red_hit = False
        for left in self.pending_done:
            if TEST_RE.search(cmd) and failed:
                red_hit = True
                continue            # this claim is spent
            if left > 1:
                keep.append(left - 1)
        if red_hit:
            self.red_after_done += 1
        self.pending_done = keep

    def active_minutes(self):
        t = sorted(self.times)
        total = 0.0
        for a, b in zip(t, t[1:]):
            if b - a <= GAP_MINUTES * 60:
                total += b - a
        return round(total / 60, 1)


def first_task_key(text):
    s = re.sub(r"[\d\W_]+", " ", norm(text or "")).strip()[:160]
    return hashlib.sha1(s.encode()).hexdigest()[:16] if len(s) >= 25 else ""


def cmd_str(c):
    if isinstance(c, list):
        return " ".join(str(x) for x in c)
    return c if isinstance(c, str) else ""


def read_codex(path):
    acc = Acc()
    meta = {}
    with opener(path) as fh:
        for line in fh:
            if '"session_meta"' in line[:200] and not meta:
                try:
                    d = json.loads(line)
                    meta = d.get("payload") or {}
                    acc.stamp(parse_ts(d.get("timestamp")))
                except ValueError:
                    pass
                continue
            if "item_completed" not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            p = d.get("payload") or {}
            item = p.get("item") or {}
            kind = item.get("type")
            acc.stamp(parse_ts(d.get("timestamp")))
            if kind == "UserMessage":
                acc.user(text_of(item.get("content")))
            elif kind == "AgentMessage":
                acc.assistant(text_of(item.get("content")))
            elif kind == "CommandExecution":
                code = item.get("exit_code")
                acc.command(cmd_str(item.get("command")), isinstance(code, int) and code != 0)
            elif kind == "FileChange":
                acc.writes += 1
    sid = meta.get("id") or os.path.basename(path)
    sub = bool(meta.get("parent_thread_id") or meta.get("agent_role") or "subagent" in json.dumps(meta.get("source", "")).lower())
    return "codex", sid, meta.get("cwd") or "", sub, acc


def read_claude(path):
    acc = Acc()
    tool_cmd = {}       # tool_use id -> command text
    sid = os.path.basename(path).replace(".jsonl.zst", "").replace(".jsonl", "")
    cwd = ""
    sub = "/subagents/" in path
    with opener(path) as fh:
        for line in fh:
            if '"type":"user"' not in line and '"type":"assistant"' not in line and '"type": "user"' not in line and '"type": "assistant"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            t = d.get("type")
            if t not in ("user", "assistant"):
                continue
            acc.stamp(parse_ts(d.get("timestamp")))
            cwd = cwd or d.get("cwd") or ""
            sub = sub or bool(d.get("isSidechain"))
            msg = d.get("message") or {}
            content = msg.get("content")
            if t == "user":
                if d.get("isMeta"):
                    continue
                if isinstance(content, str):
                    acc.user(content)
                elif isinstance(content, list):
                    acc.user(text_of(content)) if not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content) else None
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            cid = b.get("tool_use_id")
                            if cid in tool_cmd:
                                acc.command(tool_cmd.pop(cid), bool(b.get("is_error")))
            else:
                if isinstance(content, list):
                    acc.assistant(text_of(content))
                    for b in content:
                        if not isinstance(b, dict) or b.get("type") != "tool_use":
                            continue
                        if b.get("name") == "Bash":
                            tool_cmd[b.get("id")] = str((b.get("input") or {}).get("command", ""))
                        elif b.get("name") in WRITE_TOOLS:
                            acc.writes += 1
    return "claude", sid, cwd, sub, acc


def one(args):
    kind, path = args
    try:
        src, sid, cwd, sub, acc = (read_codex if kind == "codex" else read_claude)(path)
    except OSError:
        return None
    return {
        "source": src, "session": sid, "path": path, "project": cwd.replace(os.path.expanduser("~"), "~"),
        "subagent": int(sub), "active_min": acc.active_minutes(), "users": acc.users,
        "corr_msgs": acc.corr_msgs, "corr_total": acc.corr_total, "prof_msgs": acc.prof_msgs,
        "reverts": acc.reverts, "discards": acc.discards, "no_verify": acc.no_verify,
        "red_after_done": acc.red_after_done, "commits": acc.commits, "writes": acc.writes, "commands": acc.commands,
        "task_key": first_task_key(acc.first_task),
    }


def collect(root, kind):
    out = []
    for base, _dirs, names in os.walk(root):
        for n in names:
            if n.endswith(".jsonl") or n.endswith(".jsonl.zst"):
                out.append((kind, os.path.join(base, n)))
    return sorted(out)


def mark(rows):
    groups = defaultdict(list)
    for r in rows:
        if r["task_key"] and not r["subagent"]:
            groups[(r["source"], r["project"], r["task_key"])].append(r)
    for g in groups.values():
        for r in g:
            r["repeat_group"] = len(g) if len(g) > 1 else 0
            r["auto_repeat"] = int(len(g) >= AUTOMATED_MIN_GROUP)   # a scheduled or templated run, not a person asking again
    for r in rows:
        r.setdefault("repeat_group", 0)
        r.setdefault("auto_repeat", 0)
        flags = []
        if r["corr_msgs"]:
            flags.append("owner_correction")
        if r["prof_msgs"]:
            flags.append("profanity")
        if r["reverts"]:
            flags.append("revert")
        if r["no_verify"]:
            flags.append("no_verify")
        if r["red_after_done"]:
            flags.append("red_after_done")
        if r["repeat_group"] and not r["auto_repeat"]:
            flags.append("repeated_task")
        if r["active_min"] >= LONG_MINUTES and r["commits"] == 0 and r["writes"] >= LONG_MIN_WRITES:
            flags.append("long_no_commit")
        r["long_no_commit"] = int("long_no_commit" in flags)
        r["flags"] = ";".join(flags)
        r["marked"] = int(bool(flags))
    return rows


def summarize(rows):
    def block(sel):
        marked = [r for r in sel if r["marked"]]
        per = Counter()
        for r in marked:
            for f in r["flags"].split(";"):
                per[f] += 1
        return {"sessions": len(sel), "marked": len(marked), "per_flag": dict(per)}
    summary = {"all": block(rows), "without_subagents": block([r for r in rows if not r["subagent"]]),
               "by_source": {s: block([r for r in rows if r["source"] == s]) for s in sorted({r["source"] for r in rows})}}
    summary["automated_repeat_sessions"] = sum(r["auto_repeat"] for r in rows)
    summary["human_candidate_sessions"] = sum(1 for r in rows if not r["subagent"] and not r["auto_repeat"] and r["users"] > 0)
    proj = Counter(r["project"] for r in rows if r["marked"] and not r["subagent"])
    summary["top_projects_marked_without_subagents"] = proj.most_common(15)
    summary["thresholds"] = {"correction_max_len": CORR_MAX_LEN, "done_window_commands": DONE_WINDOW, "long_minutes": LONG_MINUTES,
                             "long_min_writes": LONG_MIN_WRITES, "gap_minutes": GAP_MINUTES}
    return summary


FIELDS = ["source", "session", "path", "project", "subagent", "active_min", "users", "corr_msgs", "corr_total", "prof_msgs",
          "reverts", "discards", "no_verify", "red_after_done", "repeat_group", "auto_repeat", "commits", "writes", "commands",
          "long_no_commit", "covered", "flags", "marked"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--codex", action="append", help="Codex sessions directory (may be given twice, e.g. archived_sessions)")
    ap.add_argument("--claude")
    ap.add_argument("--out", required=True)
    ap.add_argument("--phrases", help="JSON file with extra phrase lists: {\"correction\": [...], \"profanity\": [...], \"done\": [...]}")
    ap.add_argument("--covered", help="file with session ids already read by people or readers, one per line")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--controls", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    extra = None
    if a.phrases:
        with open(a.phrases, encoding="utf-8") as fh:
            extra = json.load(fh)
    build_patterns(extra)
    work = []
    for root in a.codex or []:
        work += collect(root, "codex")
    if a.claude:
        work += collect(a.claude, "claude")
    covered = set()
    if a.covered and os.path.exists(a.covered):
        covered = {l.strip() for l in open(a.covered) if l.strip()}
    rows = []
    if a.workers > 1 and len(work) > 8:
        with multiprocessing.Pool(a.workers, initializer=build_patterns, initargs=(extra,)) as pool:  # spawned workers re-import the module
            for i, r in enumerate(pool.imap_unordered(one, work, chunksize=8), 1):
                if r:
                    rows.append(r)
                if i % 1000 == 0:
                    print("read", i, "of", len(work), file=sys.stderr, flush=True)
    else:
        rows = [r for r in map(one, work) if r]
    rows.sort(key=lambda r: (r["source"], r["path"]))
    mark(rows)
    for r in rows:
        r["covered"] = int(r["session"] in covered)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "sessions.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    summary = summarize(rows)
    summary["covered"] = {"ids_given": len(covered), "sessions_covered": sum(r["covered"] for r in rows)}
    with open(os.path.join(a.out, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(a.out, "marked.txt"), "w") as fh:
        fh.write("".join("%s %s\n" % (r["session"], r["path"]) for r in rows if r["marked"]))
    rnd = random.Random(a.seed)
    pool_unmarked = [r for r in rows if not r["marked"] and not r["subagent"] and r["users"] > 0 and not r["auto_repeat"]]
    pick = rnd.sample(pool_unmarked, min(a.controls, len(pool_unmarked)))
    with open(os.path.join(a.out, "controls.txt"), "w") as fh:
        fh.write("".join("%s %s\n" % (r["session"], r["path"]) for r in pick))
    print(json.dumps({k: summary[k] for k in ("all", "without_subagents")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
