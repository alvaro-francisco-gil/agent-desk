"""Agents in every repo under ~/githubs cannot read secret files without a human.

files/claude-secret-denies.json is merged into the user-level
~/.claude/settings.json by tasks/agent_sessions.yml. Matching here
follows Claude Code's rule syntax:

- Bash rules: `*` matches any run of characters over the whole command.
- Read rules use gitignore patterns. `//` anchors at the filesystem root and
  `~/` at the home directory; a pattern with no `/` is relative to the
  session's directory and matches a file name at any depth. A `!` rule carves
  its matches out of the earlier unanchored rules from the same file only:
  Claude Code's permissions docs, "Special characters and `!` negation", say a
  `!` pattern can't reach a rule anchored with `/`, `~/` or `//`. That differs
  from git, where a `!` re-includes after any pattern.
- Deny wins over allow, so the example files stay readable only because no deny
  rule is left matching them.
"""

import json
import re
from fnmatch import fnmatchcase
from pathlib import Path

import pytest

DENY = json.loads(
    (Path(__file__).resolve().parents[1] / "files" / "claude-secret-denies.json").read_text()
)
HOME = "/home/u"
GITHUBS = f"{HOME}/githubs"


def _rules(tool: str) -> list[str]:
    prefix = f"{tool}("
    return [r[len(prefix) : -1] for r in DENY if r.startswith(prefix)]


def _glob_regex(pattern: str) -> re.Pattern[str]:
    out = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out)


def _read_denied(cwd: str, path: str) -> bool:
    relative_hit = False
    for rule in _rules("Read"):
        anchored = rule.replace("~/", HOME.lstrip("/") + "/", 1) if rule.startswith("~/") else ""
        if rule.startswith("//"):
            anchored = rule[2:]
        if anchored:
            if _glob_regex(anchored).fullmatch(path.lstrip("/")):
                return True
            continue
        negated = rule.startswith("!")
        pattern = rule.lstrip("!")
        assert "/" not in pattern, f"unanchored rule with a path is not modelled: {rule}"
        if path.startswith(cwd + "/") and _glob_regex(pattern).fullmatch(path.rsplit("/", 1)[1]):
            relative_hit = not negated
    return relative_hit


def _bash_denied(command: str) -> bool:
    return any(fnmatchcase(command, rule) for rule in _rules("Bash"))


# (session directory, secret file), both under ~/githubs, as found on 2026-11-10.
SECRET_FILES = [
    ("acme/acme-apps", ".env.local"),
    ("acme/acme-apps", ".envrc"),
    ("acme/acme-apps", "functions/.env.acme-prod"),
    ("acme/acme-apps", "functions/image-rendering/.env.acme-beta"),
    ("acme/acme-apps", ".deploy-functions/.env.proj-1234"),
    ("acme/acme-apps", "function-kits/firestore-bigquery-export/config-bq-users/.env"),
    ("blog", ".envrc"),
    ("blog", ".env.local"),
    ("blog", "web/.env.local"),
    ("blog", "web/.env.production.local"),
    ("client/app", ".envrc"),
    ("client/app", "apps/mobile/.env"),
    ("infra", "secrets/secrets.prod.yml"),
    ("infra", "keys/tls.pem"),
    ("acme/acme-apps", "deploy/acme-prod-sa.json"),
    ("acme/acme-apps", "firebase-service-account.json"),
]

EXAMPLE_FILES = [
    ("acme/acme-apps", ".env.local.example"),
    ("acme/acme-apps", "apps/acme-web/.env.example"),
    ("blog", "web/.env.example"),
    ("blog", "functions/.env.example"),
    ("client/app", "apps/mobile/.env.example"),
]

ORDINARY_FILES = [
    ("infra", "secrets/secrets.example.yml"),
    ("acme/acme-apps", "functions/src/env.ts"),
    ("Social-Energy-Lab", "studies/dsa-2026/analyses/id_repair_benchmark.py"),
    ("blog", "README.md"),
]


@pytest.mark.parametrize(("repo", "path"), SECRET_FILES)
def test_read_tool_is_denied_on_secret_files(repo: str, path: str) -> None:
    cwd = f"{GITHUBS}/{repo}"
    assert _read_denied(cwd, f"{cwd}/{path}")


@pytest.mark.parametrize(("repo", "path"), SECRET_FILES)
def test_read_tool_is_denied_on_secret_files_from_the_workspace_root(repo: str, path: str) -> None:
    assert _read_denied(GITHUBS, f"{GITHUBS}/{repo}/{path}")


@pytest.mark.parametrize(
    "path",
    [
        "/home/u/.ssh/id_ed25519",
        "/home/u/.ssh/id_rsa",
        "/home/u/githubs/blog/.envrc",
        "/home/u/.config/sops/age/keys.txt",
    ],
)
def test_anchored_rules_hold_outside_the_session_directory(path: str) -> None:
    assert _read_denied(f"{GITHUBS}/infra", path)


@pytest.mark.parametrize(("repo", "path"), EXAMPLE_FILES + ORDINARY_FILES)
def test_read_tool_still_reads_examples_and_ordinary_files(repo: str, path: str) -> None:
    cwd = f"{GITHUBS}/{repo}"
    assert not _read_denied(cwd, f"{cwd}/{path}")
    assert not _read_denied(GITHUBS, f"{cwd}/{path}")


@pytest.mark.parametrize(
    "command",
    [
        "cat .env.local",
        "cat ./.env",
        "head -5 .envrc",
        "tail /home/u/githubs/blog/.env.local",
        "less .deploy-functions/.env.proj-1234",
        "grep KEY functions/.env.acme-prod",
        "rg -n TOKEN functions/image-rendering/.env.acme-beta",
        "sed -n 1,5p client/app/apps/mobile/.env",
        "awk 1 web/.env.production.local",
        "xxd .env",
        "node --env-file=.env scripts/x.js",
        "cat secrets/secrets.prod.yml",
        "cat ~/.ssh/id_ed25519",
        "cat certs/tls.pem",
        "cat certs/tls.pem;ls",
        "cat certs/tls.pem>/tmp/x",
        "cat certs/tls.pem|base64",
        'cat ".env.local"',
        "grep KEY '.env'",
        "cat ~/.config/sops/age/keys.txt",
        "cat deploy/acme-prod-sa.json",
        "jq . firebase-service-account.json",
        "sops -d secrets/secrets.enc.yml",
        "sops decrypt secrets/secrets.enc.yml",
        "sops --decrypt secrets/secrets.enc.yml",
        "sops --input-type yaml -d secrets/secrets.enc.yml",
        "sops exec-env secrets/secrets.enc.yml env",
        "sops exec-file secrets/secrets.enc.yml 'cat {}'",
    ],
)
def test_bash_readers_are_denied_on_secret_files(command: str) -> None:
    assert _bash_denied(command), command


@pytest.mark.parametrize(
    "command",
    [
        "grep -rn process.env src/",
        "rg 'import.meta.env' apps/",
        'grep -rn "process.env.API_URL" src/',
        "cat README.md",
        "python studies/dsa-2026/analyses/id_repair_benchmark.py",
        "sops -e -i secrets/secrets.enc.yml",
        "git status",
    ],
)
def test_ordinary_commands_stay_allowed(command: str) -> None:
    assert not _bash_denied(command), command


def test_the_example_carve_out_follows_the_rule_it_carves() -> None:
    reads = _rules("Read")
    assert reads.index("!*.example") > reads.index(".env.*")
