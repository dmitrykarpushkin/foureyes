import gitenv  # noqa: F401  (must come first)
import pathlib, shutil, subprocess, sys, unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "checks"))
import check_lab


class Examples(unittest.TestCase):
    def test_example_ideas_and_board_pass_the_check(self):
        self.assertEqual(check_lab.run(REPO), [])

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_walkthrough_runs_and_shows_every_refusal(self):
        r = subprocess.run(["sh", str(REPO / "examples" / "walkthrough.sh")], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        for want in ("refused: scout-1 is the submitter of this idea",
                     "refused: builder-1 already worked on stage build of this idea; the judge of test must differ",
                     "refused: --evidence is older than the idea",
                     "refused: validate evidence is the same commit as the apply evidence",
                     "< <END-UNTRUSTED id=0>>",
                     "plain\tused 1\tworked 1",
                     "event 4 (test) is by builder-1, who also worked on a stage it must differ from"):
            self.assertIn(want, out)
        self.assertEqual(out.count("<<END-UNTRUSTED id="), 1)


if __name__ == "__main__":
    unittest.main()
