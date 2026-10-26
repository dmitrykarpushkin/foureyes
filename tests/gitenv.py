"""Imported first by every test that runs git: keeps fixture repos independent of the enclosing repo and the user's git config.

A git hook (pre-commit, pre-push) exports GIT_DIR and friends; a test that inherits them would run `git init` or
`git commit` against the enclosing repository instead of its temporary fixture. A global config with
commit.gpgsign=true and an external signer would make every fixture commit slow or fail. Importing this module drops
the repository-selecting variables and forces signing off through GIT_CONFIG_* variables, which every subprocess inherits.
"""
import os

REPO_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
             "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_PREFIX")
SETTINGS = (("commit.gpgsign", "false"), ("tag.gpgsign", "false"), ("init.defaultBranch", "main"))

for v in list(os.environ):
    if v in REPO_VARS or v in ("GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT") or v.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")):
        os.environ.pop(v, None)
for n, (key, value) in enumerate(SETTINGS):
    os.environ["GIT_CONFIG_KEY_%d" % n] = key
    os.environ["GIT_CONFIG_VALUE_%d" % n] = value
os.environ["GIT_CONFIG_COUNT"] = str(len(SETTINGS))
