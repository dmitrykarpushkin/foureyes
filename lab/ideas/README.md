# Example ideas

The four ideas here are synthetic examples written for this public repo; they were produced by running `lab/lab.py`
commands, so the files are real engine output. The agent ids and notes are illustrative: the `--json` flag described by
the builder notes of the first idea was not implemented in this repo. They show four outcomes:

| idea | where it stopped | why |
|---|---|---|
| add a `--json` flag to `next` | `test` (second try) | the tester failed the first build, the idea went back to `build` |
| cap the length of `why` | `triage` | submitted by a scout without `--url` or `--code`: unconfirmed, triage cannot pass it |
| post a daily summary to the team chat | parked | a message to people needs the owner's yes |
| rewrite the engine in Rust | dropped | no measured number behind the claim |

A full chain through `apply` and `validate` needs real commits as evidence; `examples/walkthrough.sh` runs one in a
throwaway git repo.
