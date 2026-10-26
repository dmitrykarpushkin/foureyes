# Builder
Do the change by the chosen method. Read the module's MODULE.md first. Run the repo's tests and checks before you stop. Commit only through the repo hooks (do not bypass them); if your sandbox cannot push, leave the diff on a branch and say so.
`python3 lab/lab.py done <id> --agent <your id> --verdict ok --note "<what changed, files>"` (verdict fail if you could not).
In a changes/<id>/ record (OpenSpec) every task line names its tests with `tests:`; the tests are written by a different agent id than the implementer.
