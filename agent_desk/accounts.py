"""Which Claude accounts `cs` can start a session on: [accounts] in ~/.config/agent-desk/config.toml.

    [accounts.second]
    token_file = "~/.config/agent-desk/second.json"   # {"token": "..."} from `claude setup-token`

The account Claude is logged into with /login is always offered first, as "login". Any other
account is a `claude setup-token` token, passed to that one session as CLAUDE_CODE_OAUTH_TOKEN,
so settings, history, memory and plugins stay shared; only who pays changes. The token is read
from its file when the session starts and never written into a command line.
"""
from __future__ import annotations

import shlex
import tomllib
from pathlib import Path

from agent_desk.repos import CONFIG, ConfigError

LOGIN = "login"


def load(config: Path = CONFIG) -> dict[str, Path | None]:
    """Account name → its token file, "login" first (None: the /login account)."""
    config = config.expanduser()
    found: dict[str, Path | None] = {LOGIN: None}
    if not config.is_file():
        return found
    try:
        table = tomllib.loads(config.read_text(encoding="utf-8")).get("accounts", {})
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{config} is not valid TOML: {e}") from e
    for name, entry in table.items():
        if name == LOGIN:
            raise ConfigError(f"{config}: accounts.{LOGIN} is reserved for the /login account")
        token_file = entry.get("token_file") if isinstance(entry, dict) else None
        if not token_file:
            raise ConfigError(f"{config}: accounts.{name} needs a token_file")
        found[name] = Path(token_file).expanduser()
    return found


def command(name: str, token_file: Path | None, base: str = "claude") -> str:
    """The line typed into the pane to start `base` on this account."""
    if token_file is None:
        return base
    if not token_file.is_file():
        raise ConfigError(f"account {name!r}: {token_file} is missing; store its `claude setup-token` token there")
    read = f"jq -r .token {shlex.quote(str(token_file))}"
    return f'CLAUDE_ACCOUNT={shlex.quote(name)} CLAUDE_CODE_OAUTH_TOKEN="$({read})" {base}'
