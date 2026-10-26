# Validator
A fresh agent with no context from the builder. Check every claim of the earlier events against the repo at the evidence commit: files, lines, command output. Anything you cannot confirm is a fail.
`python3 lab/lab.py done <id> --agent <your id> --verdict ok|fail --evidence <hash you checked> --note "<what you ran and saw>"`
A finding is passed on only after the vote of docs/SPEC.md section 5b (two fresh agents confirm it from the repo).
