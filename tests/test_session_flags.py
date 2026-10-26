import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lab", "evals"))
import session_flags as sf  # noqa: E402

AGAIN = "again not working"
READY = "fixed"
SWEAR = "wtf is this"


def write(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def codex_item(ts, kind, **kw):
    item = {"type": kind}
    item.update(kw)
    return {"timestamp": ts, "type": "event_msg", "payload": {"type": "item_completed", "item": item}}


def msg(text):
    return [{"type": "text", "text": text}]


class SessionFlags(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "out")

    def run_all(self, codex=None, claude=None, **kw):
        argv = ["--out", self.out, "--workers", "1"]
        if codex:
            argv += ["--codex", codex]
        if claude:
            argv += ["--claude", claude]
        for k, v in kw.items():
            argv += ["--" + k, str(v)]
        sf.main(argv)
        with open(os.path.join(self.out, "sessions.csv")) as fh:
            return {r["session"]: r for r in csv.DictReader(fh)}

    def test_codex_signals(self):
        d = os.path.join(self.tmp, "codex")
        recs = [{"timestamp": "2026-10-01T10:00:00Z", "type": "session_meta", "payload": {"id": "c1", "cwd": "/work/app"}},
                codex_item("2026-10-01T10:01:00Z", "UserMessage", content=msg("fix the build please, thanks a lot for it")),
                codex_item("2026-10-01T10:02:00Z", "AgentMessage", content=msg("all tests pass, done")),
                codex_item("2026-10-01T10:03:00Z", "CommandExecution", command=["bash", "-lc", "pytest -q"], exit_code=1),
                codex_item("2026-10-01T10:04:00Z", "CommandExecution", command=["git", "commit", "--no-verify", "-m", "x"], exit_code=0),
                codex_item("2026-10-01T10:05:00Z", "CommandExecution", command=["git", "revert", "HEAD"], exit_code=0),
                codex_item("2026-10-01T10:06:00Z", "UserMessage", content=msg(AGAIN)),
                codex_item("2026-10-01T10:07:00Z", "UserMessage", content=msg(SWEAR))]
        write(os.path.join(d, "2026", "10", "01", "rollout-c1.jsonl"), recs)
        rows = self.run_all(codex=d)
        r = rows["c1"]
        self.assertEqual(r["corr_msgs"], "1")
        self.assertEqual(r["prof_msgs"], "1")
        self.assertEqual(r["red_after_done"], "1")
        self.assertEqual(r["no_verify"], "1")
        self.assertEqual(r["reverts"], "1")
        self.assertEqual(r["commits"], "1")
        self.assertEqual(r["project"], "/work/app")
        self.assertEqual(r["marked"], "1")
        for f in ("owner_correction", "profanity", "revert", "no_verify", "red_after_done"):
            self.assertIn(f, r["flags"])
        self.assertNotIn("long_no_commit", r["flags"])

    def test_claude_signals_and_subagent(self):
        d = os.path.join(self.tmp, "claude", "-work-app")
        recs = [
            {"type": "user", "timestamp": "2026-10-02T10:00:00Z", "cwd": "/work/app", "message": {"role": "user", "content": "build the feature that parses the report"}},
            {"type": "assistant", "timestamp": "2026-10-02T10:01:00Z", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "Done, " + READY}, {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "npm test"}}]}},
            {"type": "user", "timestamp": "2026-10-02T10:02:00Z", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": "Exit code 1"}]}},
        ]
        write(os.path.join(d, "s1.jsonl"), recs)
        write(os.path.join(d, "s1", "subagents", "agent-a.jsonl"),
              [{"type": "user", "timestamp": "2026-10-02T10:00:00Z", "isSidechain": True, "message": {"role": "user", "content": "sub task text that is long enough here"}}])
        rows = self.run_all(claude=os.path.join(self.tmp, "claude"))
        self.assertEqual(rows["s1"]["red_after_done"], "1")
        self.assertEqual(rows["s1"]["subagent"], "0")
        self.assertEqual(rows["agent-a"]["subagent"], "1")
        self.assertEqual(rows["agent-a"]["marked"], "0")

    def test_long_session_without_commit_and_repeat(self):
        d = os.path.join(self.tmp, "claude", "-work-app")

        def long_session(sid, commit):
            recs = [{"type": "user", "timestamp": "2026-10-03T10:00:00Z", "cwd": "/work/app",
                     "message": {"role": "user", "content": "refactor the whole importer module step by step"}}]
            for i in range(8):
                ts = "2026-10-03T%02d:%02d:00Z" % (10 + (i * 10) // 60, (i * 10) % 60 + 5)
                recs.append({"type": "assistant", "timestamp": ts, "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "id": "w%d" % i, "name": "Edit", "input": {}}]}})
            if commit:
                recs.append({"type": "assistant", "timestamp": "2026-10-03T11:30:00Z", "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "id": "g", "name": "Bash", "input": {"command": "git commit -m x"}}]}})
                recs.append({"type": "user", "timestamp": "2026-10-03T11:31:00Z", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "g", "content": "ok"}]}})
            write(os.path.join(d, sid + ".jsonl"), recs)

        long_session("l1", False)
        long_session("l2", True)
        rows = self.run_all(claude=os.path.join(self.tmp, "claude"))
        self.assertIn("long_no_commit", rows["l1"]["flags"])
        self.assertNotIn("long_no_commit", rows["l2"]["flags"])
        self.assertEqual(rows["l1"]["repeat_group"], "2")       # the same first task twice in one project
        self.assertIn("repeated_task", rows["l2"]["flags"])

    def test_templated_runs_are_not_a_repeated_request(self):
        d = os.path.join(self.tmp, "claude", "-work-bot")
        for i in range(6):
            write(os.path.join(d, "a%d.jsonl" % i), [
                {"type": "user", "timestamp": "2026-10-04T10:00:00Z", "cwd": "/work/bot",
                 "message": {"role": "user", "content": "run the nightly digest for run number %d please" % i}}])
        rows = self.run_all(claude=os.path.join(self.tmp, "claude"))
        self.assertEqual(rows["a0"]["auto_repeat"], "1")
        self.assertNotIn("repeated_task", rows["a0"]["flags"])
        self.assertEqual(rows["a0"]["marked"], "0")

    def test_no_text_in_outputs_and_summary(self):
        d = os.path.join(self.tmp, "codex")
        marker = "unique-marker-text-xyz"
        recs = [{"timestamp": "2026-10-01T10:00:00Z", "type": "session_meta", "payload": {"id": "c9", "cwd": "/work/app"}},
                codex_item("2026-10-01T10:01:00Z", "UserMessage", content=msg(AGAIN + " " + marker))]
        write(os.path.join(d, "r.jsonl"), recs)
        self.run_all(codex=d, covered=os.path.join(self.tmp, "none"))
        for name in ("sessions.csv", "summary.json", "marked.txt", "controls.txt"):
            with open(os.path.join(self.out, name)) as fh:
                body = fh.read()
            self.assertNotIn(marker, body)
            self.assertNotIn(AGAIN, body)
        with open(os.path.join(self.out, "summary.json")) as fh:
            s = json.load(fh)
        self.assertEqual(s["all"]["sessions"], 1)
        self.assertEqual(s["all"]["marked"], 1)

    @unittest.skipUnless(shutil.which("zstd"), "zstd binary not installed")
    def test_compressed_codex_log(self):
        d = os.path.join(self.tmp, "codex")
        recs = [{"timestamp": "2026-10-01T10:00:00Z", "type": "session_meta", "payload": {"id": "z1", "cwd": "/w"}},
                codex_item("2026-10-01T10:01:00Z", "CommandExecution", command=["git", "commit", "--no-verify"], exit_code=0)]
        path = os.path.join(d, "rollout-z1.jsonl")
        write(path, recs)
        subprocess.run(["zstd", "-q", "--rm", path], check=True)
        rows = self.run_all(codex=d)
        self.assertEqual(rows["z1"]["no_verify"], "1")

    def test_long_user_prompt_is_not_a_correction(self):
        d = os.path.join(self.tmp, "codex")
        recs = [{"timestamp": "2026-10-01T10:00:00Z", "type": "session_meta", "payload": {"id": "c5", "cwd": "/w"}},
                codex_item("2026-10-01T10:01:00Z", "UserMessage", content=msg("task text " * 60 + AGAIN))]
        write(os.path.join(d, "r5.jsonl"), recs)
        rows = self.run_all(codex=d)
        self.assertEqual(rows["c5"]["corr_msgs"], "0")

    def test_extra_phrases_for_another_language(self):
        d = os.path.join(self.tmp, "codex")
        recs = [{"timestamp": "2026-10-01T10:00:00Z", "type": "session_meta", "payload": {"id": "g1", "cwd": "/w"}},
                codex_item("2026-10-01T10:01:00Z", "UserMessage", content=msg("das funktioniert nicht"))]
        write(os.path.join(d, "g1.jsonl"), recs)
        self.assertEqual(self.run_all(codex=d)["g1"]["corr_msgs"], "0")   # English defaults miss it
        phrases = os.path.join(self.tmp, "phrases.json")
        with open(phrases, "w") as fh:
            json.dump({"correction": ["funktioniert nicht"]}, fh)
        self.assertEqual(self.run_all(codex=d, phrases=phrases)["g1"]["corr_msgs"], "1")
        sf.build_patterns()


if __name__ == "__main__":
    unittest.main()
