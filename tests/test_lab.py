import gitenv  # noqa: F401  (must come first: isolates fixture repos from the enclosing repo and git config)
import json, os, pathlib, shutil, subprocess, sys, tempfile, unittest
import yaml

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "lab"))
sys.path.insert(0, str(REPO / "checks"))
import lab
import check_lab


class LabCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = r = pathlib.Path(self.tmp.name)
        for f in ("chains.yaml", "methods.yaml"):
            (r / "lab").mkdir(exist_ok=True)
            shutil.copy(REPO / "lab" / f, r / "lab" / f)
        (r / "mod").mkdir()
        (r / "mod/MODULE.md").write_text("x")
        subprocess.run(["git", "init", "-q"], cwd=r, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i"], cwd=r, check=True)
        self.head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=r, capture_output=True, text=True).stdout.strip()

    def idea(self):
        iid = lab.submit(self.root, "Make the thing faster", "mod", "scout-1", why="It is slow.", url="https://example.com/x")
        self.set_submitted(iid, "2000-01-01T00:00:00Z")  # fixture commits are made before the idea; only the newness test cares
        return iid

    def set_submitted(self, iid, ts):
        i = yaml.safe_load(lab.idea_path(self.root, iid).read_text())
        i["submitted_at"] = ts
        lab.save(self.root, i)

    def d(self, iid, agent, verdict, **kw):
        return lab.done(self.root, iid, agent, verdict, **kw)

    def load(self, iid):
        return yaml.safe_load(lab.idea_path(self.root, iid).read_text())

    def to_build(self, iid):
        self.d(iid, "t1", "go", value=4, cost_pct=1.5, note="checked")
        self.d(iid, "m1", "ok", method="plain")



class ChainTest(LabCase):
    def test_full_chain(self):
        iid = self.idea()
        self.d(iid, "t1", "go", value=4, cost_pct=1.5)
        self.d(iid, "m1", "ok", method="openspec")
        self.d(iid, "b1", "ok")
        self.d(iid, "x1", "ok")
        self.d(iid, "a1", "ok", evidence=self.head)
        self.git("commit", "-q", "--allow-empty", "-m", "validate")
        self.d(iid, "v1", "ok", evidence=self.git("rev-parse", "HEAD"))
        self.d(iid, "r1", "worked")
        i = self.load(iid)
        self.assertEqual((i["state"], i["stage"]), ("done", None))
        self.assertEqual(lab.export_data(self.root)["methods"]["openspec"]["worked"], 1)
        self.assertEqual(CheckTest.problems_of(self.root, i, iid), [])

    def test_title_with_colon_gives_a_clean_id(self):
        iid = lab.submit(self.root, "Fix it: now, for real", "mod", "scout-1", url="https://example.com/x")
        self.assertTrue(iid.endswith("-fix-it-now-for-real"), iid)

    def test_judge_must_differ(self):
        iid = self.idea()
        self.to_build(iid)
        self.d(iid, "b1", "ok")
        with self.assertRaises(SystemExit):
            self.d(iid, "b1", "ok")  # tester is the builder

    def test_submitter_cannot_triage_and_triage_cannot_test(self):
        iid = self.idea()
        with self.assertRaises(SystemExit):
            self.d(iid, "scout-1", "go", value=4, cost_pct=1)  # the submitter
        self.to_build(iid)  # triage agent is t1
        self.d(iid, "b1", "ok")
        for bad in ("t1", "scout-1"):
            with self.assertRaises(SystemExit):
                self.d(iid, bad, "ok")
        self.d(iid, "x1", "ok")

    def test_apply_needs_real_commit(self):
        iid = self.idea()
        self.to_build(iid)
        self.d(iid, "b1", "ok")
        self.d(iid, "x1", "ok")
        for ev in (None, "deadbeef"):
            with self.assertRaises(SystemExit):
                self.d(iid, "a1", "ok", evidence=ev)

    def git(self, *a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=self.root, capture_output=True, text=True, check=True).stdout.strip()

    def test_evidence_must_be_reachable_and_distinct(self):
        branch = self.git("rev-parse", "--abbrev-ref", "HEAD")
        self.git("checkout", "-q", "-b", "side")
        self.git("commit", "-q", "--allow-empty", "-m", "side")
        side = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", branch)
        self.git("commit", "-q", "--allow-empty", "-m", "second")
        second = self.git("rev-parse", "HEAD")
        iid = self.idea()
        self.to_build(iid)
        self.d(iid, "b1", "ok")
        self.d(iid, "x1", "ok")
        with self.assertRaises(SystemExit):
            self.d(iid, "a1", "ok", evidence=side)  # exists but is on neither HEAD nor origin/main
        self.d(iid, "a1", "ok", evidence=self.head)
        with self.assertRaises(SystemExit):
            self.d(iid, "v1", "ok", evidence=self.head[:10])  # same commit as apply
        self.d(iid, "v1", "ok", evidence=second)
        i = self.load(iid)
        self.assertEqual(CheckTest.problems_of(self.root, i, iid), [])
        i["events"][-1]["evidence"] = self.head
        self.assertTrue(any("same commit" in p for p in CheckTest.problems_of(self.root, i, iid)))
        i["events"][-1]["evidence"] = side
        self.assertTrue(any("not reachable" in p for p in CheckTest.problems_of(self.root, i, iid)))

    def test_evidence_must_be_newer_than_the_idea(self):
        iid = self.idea()
        self.to_build(iid)
        self.d(iid, "b1", "ok")
        self.d(iid, "x1", "ok")
        self.set_submitted(iid, "2999-01-01T00:00:00Z")
        with self.assertRaises(SystemExit) as cm:
            self.d(iid, "a1", "ok", evidence=self.head)
        self.assertIn("older than the idea", str(cm.exception))
        self.set_submitted(iid, "2000-01-01T00:00:00Z")
        self.d(iid, "a1", "ok", evidence=self.head)
        i = self.load(iid)
        self.assertEqual(CheckTest.problems_of(self.root, i, iid), [])
        i["submitted_at"] = "2999-01-01T00:00:00Z"
        self.assertTrue(any("older than the idea" in p for p in CheckTest.problems_of(self.root, i, iid)))

    def test_with_origin_main_a_local_only_commit_is_not_enough(self):
        self.git("update-ref", "refs/remotes/origin/main", self.head)  # origin/main now exists and lags HEAD
        self.git("commit", "-q", "--allow-empty", "-m", "local only")
        local = self.git("rev-parse", "HEAD")
        iid = self.idea()
        self.to_build(iid)
        self.d(iid, "b1", "ok")
        self.d(iid, "x1", "ok")
        with self.assertRaises(SystemExit) as cm:
            self.d(iid, "a1", "ok", evidence=local)  # on HEAD but not on origin/main
        self.assertIn("origin/main", str(cm.exception))
        self.d(iid, "a1", "ok", evidence=self.head)

    def test_check_accepts_head_ancestor_when_origin_main_is_stale(self):
        iid = self.idea()
        self.to_build(iid)
        self.d(iid, "b1", "ok")
        self.d(iid, "x1", "ok")
        self.git("update-ref", "refs/remotes/origin/main", self.head)  # a clone whose origin/main is stale
        self.git("commit", "-q", "--allow-empty", "-m", "newer than origin/main")
        newer = self.git("rev-parse", "HEAD")
        i = self.load(iid)
        i["events"].append({"ts": "2026-01-01T00:00:00Z", "stage": "apply", "role": "applier", "agent": "a1", "model": "m", "verdict": "ok", "note": "n", "evidence": newer, "cost_usd": None})
        i["stage"] = "validate"
        self.assertEqual(CheckTest.problems_of(self.root, i, iid), [])
        self.git("checkout", "-q", "-b", "side", self.head)
        self.git("commit", "-q", "--allow-empty", "-m", "side")
        side = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "-")
        i["events"][-1]["evidence"] = side
        self.assertTrue(any("not reachable" in p for p in CheckTest.problems_of(self.root, i, iid)))

    def test_two_processes_finishing_one_stage_do_not_lose_an_update(self):
        import time
        iid = self.idea()
        code = ("import sys, pathlib; sys.path.insert(0, %r); import lab; "
                "lab.done(pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], 'go', value=4, cost_pct=1)" % str(REPO / "lab"))
        with lab.idea_lock(self.root, iid):
            procs = [subprocess.Popen([sys.executable, "-c", code, str(self.root), iid, a], stderr=subprocess.PIPE, text=True) for a in ("t1", "t2")]
            time.sleep(1.0)
            self.assertTrue(all(p.poll() is None for p in procs), "both must wait for the lock")
        codes = sorted((p.communicate(timeout=60), p.returncode)[1] for p in procs)
        self.assertEqual(codes[0], 0)
        self.assertNotEqual(codes[1], 0)  # the second sees the stage already closed
        i = self.load(iid)
        self.assertEqual([e["stage"] for e in i["events"]], ["triage"])
        self.assertEqual(i["stage"], "method")

    def test_rerun_appends_a_reopen_event_and_stale_lists_idle_ideas(self):
        iid = self.idea()
        self.to_build(iid)
        self.d(iid, "b1", "ok")
        before = self.load(iid)["events"]
        with self.assertRaises(SystemExit):
            lab.rerun(self.root, iid, "validate", "r1", "skip ahead")  # cannot move forward
        with self.assertRaises(SystemExit):
            lab.rerun(self.root, iid, "build", "r1", "")  # a reason is required
        self.assertEqual(lab.rerun(self.root, iid, "build", "r1", "spike result attached"), "reopened at build")
        i = self.load(iid)
        self.assertEqual(i["events"][:len(before)], before)  # history untouched
        self.assertEqual((i["events"][-1]["verdict"], i["events"][-1]["stage"], i["stage"]), ("reopen", "build", "build"))
        self.d(iid, "b2", "ok")
        self.d(iid, "r1", "ok")  # the reopening agent is not barred from the next stage
        self.assertEqual(CheckTest.problems_of(self.root, self.load(iid), iid), [])
        # stale
        import datetime as dt
        later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=30)
        self.assertEqual([r[0] for r in lab.stale(self.root, 24, later)], [iid])
        self.assertEqual(lab.stale(self.root, 24), [])
        lab.main(["rerun", iid, "--stage", "test", "--by", "r2", "--why", "again"], root=self.root)
        self.assertEqual(self.load(iid)["stage"], "test")

    def test_fail_returns_to_build_then_drops(self):
        iid = self.idea()
        self.to_build(iid)
        self.d(iid, "b1", "ok")
        self.assertEqual(self.d(iid, "x1", "fail"), "back to build")
        self.assertEqual(self.load(iid)["stage"], "build")
        self.d(iid, "b2", "fail")
        self.assertIn("dropped", self.d(iid, "b3", "fail"))
        self.assertEqual(self.load(iid)["state"], "dropped")

    def test_park_and_approve(self):
        iid = self.idea()
        self.d(iid, "t1", "park")
        with self.assertRaises(SystemExit):
            self.d(iid, "m1", "ok", method="plain")
        with self.assertRaises(SystemExit):
            lab.approve(self.root, iid, "yes")
        lab.approve(self.root, iid, 'msg-2041 "yes do it today"')
        self.assertEqual(self.load(iid)["stage"], "triage")  # parked without a go: value is still unknown

    def test_approve_after_go_with_needs_yes_goes_to_method(self):
        iid = self.idea()
        self.d(iid, "t1", "go", value=4, cost_pct=1.5, needs_yes=True)
        self.assertEqual(self.load(iid)["state"], "parked")
        with self.assertRaises(SystemExit):
            lab.approve(self.root, iid, 'msg-2041 "ok"')  # fewer than three owner words
        lab.approve(self.root, iid, 'msg-2041 "yes do it today"')
        i = self.load(iid)
        self.assertEqual((i["state"], i["stage"]), ("active", "method"))

    def test_unknown_method_and_verdict_refused(self):
        iid = self.idea()
        self.d(iid, "t1", "go", value=2, cost_pct=1)
        with self.assertRaises(SystemExit):
            self.d(iid, "m1", "ok", method="vibes")
        with self.assertRaises(SystemExit):
            self.d(iid, "m1", "worked", method="plain")


class IntakeTest(LabCase):
    def test_url_and_code_are_recorded_and_checked(self):
        (self.root / "mod/a.py").write_text("one\ntwo\n")
        i = lab.submit(self.root, "From a link", "mod", "scout-1", url="https://example.com/a")
        self.assertEqual((self.load(i)["confirmation"], self.load(i)["unconfirmed"]), ("https://example.com/a", False))
        i = lab.submit(self.root, "From code", "mod", "scout-1", code="mod/a.py:2")
        self.assertEqual((self.load(i)["confirmation"], self.load(i)["unconfirmed"]), ("code:mod/a.py:2", False))
        for bad in ({"url": "http://example.com"}, {"code": "mod/missing.py"}, {"code": "mod/a.py:3"}, {"code": "mod/a.py:x"},
                    {"code": "../etc/passwd"}, {"code": "mod/a.py", "url": "https://example.com"}):
            with self.assertRaises(SystemExit, msg=str(bad)):
                lab.submit(self.root, "Bad one", "mod", "scout-1", **bad)

    def test_gate_refuses_unconfirmed_until_confirmed(self):
        i = lab.submit(self.root, "No source", "mod", "scout-1")
        self.assertTrue(self.load(i)["unconfirmed"])
        with self.assertRaises(SystemExit) as c:
            self.d(i, "t1", "go", value=4, cost_pct=1)
        self.assertIn("unconfirmed", str(c.exception))
        self.assertEqual(self.load(i)["stage"], "triage")
        self.d_check = check_lab.check_idea(self.root, self.load(i), lab.chain(self.root), lab.methods(self.root), lab.is_commit, i)
        self.assertEqual(self.d_check, [])
        before = self.load(i)
        with self.assertRaises(SystemExit):
            lab.confirm(self.root, i, "t1", url="ftp://x")
        lab.confirm(self.root, i, "t1", url="https://example.com/proof")
        after = self.load(i)
        self.assertEqual(after["events"], before["events"])
        self.assertEqual(after["confirmations"][0]["by"], "t1")
        self.d(i, "t1", "go", value=4, cost_pct=1)
        self.assertEqual(self.load(i)["stage"], "method")
        self.assertEqual(check_lab.check_idea(self.root, self.load(i), lab.chain(self.root), lab.methods(self.root), lab.is_commit, i), [])

    def test_unconfirmed_idea_can_still_be_dropped(self):
        i = lab.submit(self.root, "No source either", "mod", "scout-1")
        self.d(i, "t1", "drop", note="no source")
        self.assertEqual(self.load(i)["state"], "dropped")

    def test_owner_needs_no_confirmation(self):
        os.environ["LAB_OWNERS"] = "alice"
        self.addCleanup(os.environ.pop, "LAB_OWNERS", None)
        for who in ("alice", "owner"):
            i = lab.submit(self.root, f"Owner idea {who}", "mod", who)
            self.assertFalse(self.load(i)["unconfirmed"])
            self.d(i, "t1", "go", value=2, cost_pct=1)
            self.assertEqual(self.load(i)["stage"], "method")

    def test_owner_match_ignores_case(self):
        i = lab.submit(self.root, "Owner idea cased", "mod", " Owner ")
        self.assertFalse(self.load(i)["unconfirmed"])

    def test_check_finds_hand_edited_pass_of_unconfirmed_idea(self):
        i = lab.submit(self.root, "No source again", "mod", "scout-1")
        data = self.load(i)
        data["events"].append({"ts": "2026-01-01T00:00:00Z", "stage": "triage", "role": "triage", "agent": "t1", "model": None, "verdict": "go",
                               "note": "", "evidence": None, "cost_usd": None})
        data["stage"], data["unconfirmed"] = "method", "yes"
        out = check_lab.check_idea(self.root, data, lab.chain(self.root), lab.methods(self.root), lab.is_commit, i)
        self.assertTrue(any("still unconfirmed" in o for o in out) and any("true or false" in o for o in out), out)

    def test_submit_limit_per_submitter_per_hour(self):
        os.environ["LAB_SUBMIT_LIMIT"] = "2"
        self.addCleanup(os.environ.pop, "LAB_SUBMIT_LIMIT", None)
        for n in range(2):
            lab.submit(self.root, f"Idea number {n}", "mod", "scout-1", url="https://example.com/x")
        with self.assertRaises(SystemExit) as c:
            lab.submit(self.root, "Idea number 3", "mod", "scout-1", url="https://example.com/x")
        self.assertIn("limit 2", str(c.exception))
        lab.submit(self.root, "Other submitter", "mod", "scout-2", url="https://example.com/x")  # another --by is not counted
        old = self.load(lab.submit(self.root, "Other hour", "mod", "scout-3", url="https://example.com/x"))
        for n in range(2):  # earlier-hour submissions of scout-4 do not count
            j = self.load(lab.submit(self.root, f"Early {n}", "mod", "scout-4", url="https://example.com/x"))
            j["submitted_at"] = "2026-01-01T00:00:00Z"
            lab.save(self.root, j)
        lab.submit(self.root, "Late one", "mod", "scout-4", url="https://example.com/x")

    def test_default_limit_is_ten(self):
        for n in range(10):
            lab.submit(self.root, f"Bulk idea {n}", "mod", "scout-1", url="https://example.com/x")
        with self.assertRaises(SystemExit):
            lab.submit(self.root, "Bulk idea eleven", "mod", "scout-1", url="https://example.com/x")


class CheckTest(LabCase):
    @staticmethod
    def problems_of(root, idea, iid):
        return check_lab.check_idea(root, idea, lab.chain(root), lab.methods(root), lab.is_commit, iid)

    def problems(self, iid):
        return self.problems_of(self.root, self.load(iid), iid)

    YES = 'msg-2041 "yes do it today"'

    def test_approve_appends_an_event_bound_to_the_idea_and_its_events(self):
        iid = self.idea()
        self.d(iid, "t1", "go", value=4, cost_pct=1.5, needs_yes=True)
        lab.approve(self.root, iid, self.YES)
        i = self.load(iid)
        ev = i["events"][-1]
        self.assertEqual((ev["verdict"], ev["to_stage"], ev["stage"]), ("approve", "method", "triage"))
        self.assertEqual(ev["idea_hash"], lab.approval_hash(i, i["events"][:-1]))
        self.assertEqual(self.problems_of(self.root, i, iid), [])
        self.d(iid, "m1", "ok", method="plain")  # the chain goes on after the approval
        self.assertEqual(self.problems_of(self.root, self.load(iid), iid), [])

    def test_parked_without_go_approve_returns_to_triage_and_triage_may_follow(self):
        iid = self.idea()
        self.d(iid, "t1", "park")
        lab.approve(self.root, iid, self.YES)
        self.assertEqual(self.problems_of(self.root, self.load(iid), iid), [])
        self.d(iid, "t2", "go", value=4, cost_pct=1)  # the approval event does not bar the next triage agent
        self.assertEqual(self.problems_of(self.root, self.load(iid), iid), [])

    def test_changed_idea_after_approval_is_refused_and_flagged(self):
        iid = self.idea()
        self.d(iid, "t1", "go", value=4, cost_pct=1.5, needs_yes=True)
        lab.approve(self.root, iid, self.YES)
        i = self.load(iid)
        i["title"] = "Make the thing slower and pay for it"
        lab.save(self.root, i)
        with self.assertRaises(SystemExit) as c:
            self.d(iid, "m1", "ok", method="plain")
        self.assertIn("approval hash differs", str(c.exception))
        self.assertTrue(any("approval hash does not match" in p for p in self.problems_of(self.root, self.load(iid), iid)))

    def test_edited_earlier_event_after_approval_is_flagged(self):
        iid = self.idea()
        self.d(iid, "t1", "go", value=4, cost_pct=1.5, needs_yes=True, note="ok to do")
        lab.approve(self.root, iid, self.YES)
        i = self.load(iid)
        i["events"][0]["note"] = "something else"
        self.assertTrue(any("approval hash does not match" in p for p in self.problems_of(self.root, i, iid)))

    def test_approve_event_must_follow_triage(self):
        iid = self.idea()
        self.d(iid, "t1", "go", value=4, cost_pct=1.5, needs_yes=True)
        lab.approve(self.root, iid, self.YES)
        i = self.load(iid)
        i["events"][-1]["to_stage"] = "nowhere"
        self.assertTrue(any("approval that does not follow triage" in p for p in self.problems_of(self.root, i, iid)))

    def test_clean_idea_has_no_problems(self):
        iid = self.idea()
        self.assertEqual(self.problems(iid), [])

    def test_hand_edited_clash_is_found(self):
        iid = self.idea()
        self.to_build(iid)
        self.d(iid, "b1", "ok")
        self.d(iid, "x1", "ok")
        i = self.load(iid)
        i["events"][-1]["agent"] = "b1"
        lab.save(self.root, i)
        self.assertTrue(any("must differ" in p for p in self.problems(iid)))

    def test_hand_edited_submitter_triage_is_found(self):
        iid = self.idea()
        self.to_build(iid)
        i = self.load(iid)
        i["events"][0]["agent"] = "scout-1"
        lab.save(self.root, i)
        self.assertTrue(any("must differ" in p for p in self.problems(iid)))

    def test_lone_validate_event_and_wrong_stage_are_found(self):
        iid = self.idea()
        i = self.load(iid)
        i["events"].append({"ts": "t", "stage": "validate", "role": "validator", "agent": "v1", "verdict": "ok", "evidence": self.head, "cost_usd": None})
        self.assertTrue(any("chain expects triage" in p for p in self.problems_of(self.root, i, iid)))
        j = self.load(iid)
        j["stage"] = "validate"
        self.assertTrue(any("events lead to" in p for p in self.problems_of(self.root, j, iid)))

    def test_separation_refusal_names_the_submitter(self):
        iid = self.idea()
        with self.assertRaises(SystemExit) as c:
            self.d(iid, "scout-1", "go", value=4, cost_pct=1)
        self.assertIn("is the submitter", str(c.exception))

    def test_fail_loop_is_in_order(self):
        iid = self.idea()
        self.to_build(iid)
        self.d(iid, "b1", "ok")
        self.d(iid, "x1", "fail")
        self.d(iid, "b2", "ok")
        self.d(iid, "x2", "ok")
        self.assertEqual(self.problems(iid), [])

    def test_export_is_deterministic(self):
        self.idea()
        a = json.dumps(lab.export_data(self.root))
        self.assertEqual(a, json.dumps(lab.export_data(self.root)))


if __name__ == "__main__":
    unittest.main()
