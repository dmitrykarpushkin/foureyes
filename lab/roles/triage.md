# Triage
Read the idea file, then check it against the repo: is the problem real, is it already done, is it a duplicate, does it need the owner's yes.
An idea marked `unconfirmed: true` cannot get `go` until it has a confirmation: check the claim yourself and add it with `python3 lab/lab.py confirm <id> --by <your id> --url https://... | --code PATH[:LINE]`, or drop it.
Verdicts: go (set --value 1..5 and --cost-pct estimate), drop (say why), park (needs the owner's yes: add --needs-yes).
`python3 lab/lab.py done <id> --agent <your id> --verdict go --value 4 --cost-pct 1.5 --note "<evidence you checked>"`
