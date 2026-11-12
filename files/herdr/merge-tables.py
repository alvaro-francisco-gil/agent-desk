"""Usage: merge-tables.py CONFIG SETTINGS --apply|--check

Sets every key of SETTINGS (TOML text: comments, [table] headers and one-line
`key = value` pairs) in the TOML file CONFIG. A table CONFIG already declares
gets the keys in place; a table it lacks is appended with its comments. Every
other line is kept. Drops the block earlier applies wrote with blockinfile.

Prints `changed` or `ok`; `--check` writes nothing. Exits 1, writing nothing,
unless the result parses to CONFIG's own values with SETTINGS' set over them
(it won't when CONFIG defines a table some other way, such as a dotted key, an
inline table or an array of tables, or is not valid TOML to begin with).
Inlined by tasks/agent_sessions.yml.
"""

import itertools
import re
import sys
import tomllib
from pathlib import Path

LEGACY_BLOCK = re.compile(
    r"^# BEGIN homelab agent-sessions\n.*?^# END homelab agent-sessions\n?", re.M | re.S
)
HEADER = re.compile(r"^\s*\[\s*([^\[\]]+?)\s*\]\s*(#.*)?$")
ANY_HEADER = re.compile(r"^\s*\[")
KEY = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=")


def table_name(line: str) -> str | None:
    match = HEADER.match(line)
    return re.sub(r"\s*\.\s*", ".", match.group(1)) if match else None


def parse_settings(text: str) -> list[tuple[str, list[str], dict[str, str]]]:
    """(table, the comment lines above its header, key -> its line), in file order."""
    tables: list[tuple[str, list[str], dict[str, str]]] = []
    comments: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            comments.append(line)
        elif name := table_name(line):
            tables.append((name, comments, {}))
            comments = []
        elif (key := KEY.match(line)) and tables:
            tables[-1][2][key.group(1)] = line.strip()
        else:
            sys.exit(f"merge-tables: unsupported settings line: {line!r}")
    return tables


def statement_starts(lines: list[str]) -> list[bool]:
    """Whether each line begins outside any string, array or inline table."""
    starts, quote, depth = [], "", 0
    for line in lines:
        starts.append(not quote and depth == 0)
        i = 0
        while i < len(line):
            if not quote:
                if line[i] == "#":
                    break
                for opener in ('"""', "'''", '"', "'"):
                    if line.startswith(opener, i):
                        quote = opener
                        i += len(opener) - 1
                        break
                else:
                    depth += {"[": 1, "{": 1, "]": -1, "}": -1}.get(line[i], 0)
            elif quote[0] == '"' and line[i] == "\\":
                i += 1
            elif line.startswith(quote, i):
                i += len(quote) - 1
                while len(quote) == 3 and line.startswith(quote[0], i + 1):
                    i += 1
                quote = ""
            i += 1
        if len(quote) == 1:
            quote = ""
    return starts


def section(lines: list[str], name: str) -> tuple[int, dict[str, tuple[int, int]]] | None:
    """The header line of table `name`, and each of its keys' (first, end) line span."""
    starts = statement_starts(lines)
    tops = [i for i in range(len(lines)) if starts[i]] + [len(lines)]
    header = next((i for i in tops[:-1] if table_name(lines[i]) == name), None)
    if header is None:
        return None
    keys = {}
    for at, nxt in itertools.pairwise(tops):
        if at <= header:
            continue
        if ANY_HEADER.match(lines[at]):
            break
        if key := KEY.match(lines[at]):
            keys[key[1]] = (at, nxt)
    return header, keys


def merge(config: str, tables: list[tuple[str, list[str], dict[str, str]]]) -> str:
    lines = LEGACY_BLOCK.sub("", config).splitlines()
    for name, comments, keys in tables:
        if section(lines, name) is None:
            while lines and not lines[-1].strip():
                lines.pop()
            lines += ([""] if lines else []) + comments + [f"[{name}]", *keys.values()]
            continue
        for key, wanted in keys.items():
            header, have = section(lines, name)
            if key in have:
                first, end = have[key]
                lines[first:end] = [wanted]
            else:
                # Right after the last key's value, so a comment above the next table stays there.
                lines.insert(max((end for _, end in have.values()), default=header + 1), wanted)
    return "\n".join(lines) + "\n"


def overlay(base: dict, top: dict) -> dict:
    out = dict(base)
    for key, value in top.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = overlay(out[key], value)
        else:
            out[key] = value
    return out


def main(config_path: str, settings_text: str, mode: str) -> None:
    if mode not in ("--apply", "--check"):
        sys.exit(__doc__)
    config = Path(config_path)
    before = config.read_text() if config.exists() else ""
    tables = parse_settings(settings_text)
    after = merge(before, tables)
    names = ", ".join(f"[{name}]" for name, _, _ in tables)
    try:
        own = tomllib.loads(LEGACY_BLOCK.sub("", before))
    except tomllib.TOMLDecodeError as err:
        sys.exit(f"merge-tables: {config} is not valid TOML ({err}); fix it, then re-run")
    try:
        merged = tomllib.loads(after)
    except tomllib.TOMLDecodeError as err:
        merged = err
    if merged != overlay(own, tomllib.loads(settings_text)):
        sys.exit(
            f"merge-tables: could not set {names} in {config} in place"
            f"{f' ({merged})' if isinstance(merged, Exception) else ''}: it defines one of them"
            " some other way (a dotted key, an inline table or an array of tables). Set those"
            " keys there by hand."
        )
    if after == before:
        print("ok")
        return
    if mode == "--apply":
        created = not config.exists()
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(after)
        if created:
            config.chmod(0o644)
    print("changed")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
