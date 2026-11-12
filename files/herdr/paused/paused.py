#!/usr/bin/env python3
"""Alt+S in herdr: move the focused agent between the active list and a paused list below it.
Alt+W closes the focused tab and lands on the next active agent, never on a paused one.

herdr's agents panel is one list, so the two are one sorted view: every pane
carries a `list` token that places it, and the agent above the paused list
carries the heading as an extra row (see the rows in agent-sessions.toml). A
paused agent keeps running. Tokens and the view die with the server, so which agents are
paused is kept in a file, by Claude session id so it survives a restart.
"""

import fcntl
import json
import os
import socket
import sys
from pathlib import Path

SOURCE = "plugin:" + os.environ["HERDR_PLUGIN_ID"]
STATE = Path(os.environ["HERDR_PLUGIN_STATE_DIR"]) / "paused.json"
HEADING = "── paused ──"


def call(method: str, **params) -> dict:
    with socket.socket(socket.AF_UNIX) as client:
        client.connect(os.environ["HERDR_SOCKET_PATH"])
        request = {"id": "paused", "method": method, "params": params}
        client.sendall(json.dumps(request).encode() + b"\n")
        reply = b""
        while not reply.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            reply += chunk
    reply = json.loads(reply)
    if "result" not in reply:
        raise SystemExit(f"herdr {method}: {reply.get('error', reply)}")
    return reply["result"]


def load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"sessions": [], "terminals": []}


def session_of(agent: dict) -> str | None:
    return (agent.get("agent_session") or {}).get("value")


def is_paused(agent: dict, state: dict) -> bool:
    """A new session in a paused pane is active: only the session that was paused stays paused."""
    session = session_of(agent)
    return session in state["sessions"] if session else agent["terminal_id"] in state["terminals"]


def sync(state: dict) -> list[str]:
    """Place every pane in its list. Returns the active agents' pane ids, in panel order."""
    agents = {a["pane_id"]: a for a in call("agent.list")["agents"]}
    panes = [p["pane_id"] for p in call("pane.list")["panes"]]
    paused = [p for p in panes if p in agents and is_paused(agents[p], state)]
    active = [p for p in panes if p in agents and p not in paused]
    # herdr indents every row after an agent's first, so the heading hangs under the
    # last active agent to keep the paused rows flush. With none, it tops the list.
    below = active[-1] if paused and active else None
    above = paused[0] if paused and not active else None
    for rank, pane in enumerate(panes):
        bucket = 1 if pane in paused else 0
        tokens = {
            "list": f"{bucket}{rank:04d}",
            "heading_below": HEADING if pane == below else None,
            "heading_above": HEADING if pane == above else None,
        }
        current = agents.get(pane, {}).get("tokens") or {}
        if any(current.get(name) != value for name, value in tokens.items()):
            call("pane.report_metadata", pane_id=pane, source=SOURCE, tokens=tokens)
    call("agent.view.set", source=SOURCE, label="grouped", sort=[{"field": {"token": "list"}}])
    return active


def toggle(state: dict) -> None:
    pane = os.environ.get("HERDR_PANE_ID")
    agent = next((a for a in call("agent.list")["agents"] if a["pane_id"] == pane), None)
    if agent is None:
        return
    session = session_of(agent)
    entries = state["sessions"] if session else state["terminals"]
    key = session or agent["terminal_id"]
    pausing = key not in entries
    if pausing:
        entries.append(key)
    else:
        entries.remove(key)
    scratch = STATE.with_suffix(".tmp")
    scratch.write_text(json.dumps(state))
    scratch.replace(STATE)
    active = sync(state)
    if pausing:
        # Only within the workspace: pausing must not pull you out of the repo you're in.
        panes = call("pane.list")["panes"]
        workspace = next(p["workspace_id"] for p in panes if p["pane_id"] == pane)
        same = [p["pane_id"] for p in panes if p["workspace_id"] == workspace]
        here = same.index(pane)
        target = next((p for p in same[here + 1 :] + same[:here] if p in active), None)
        if target:
            call("agent.focus", target=target)


def next_active(order: list[str], active: list[str], gone: set[str], start: str) -> str | None:
    """The first active pane after start in panel order, else the nearest one before it."""
    here = order.index(start) if start in order else len(order)
    after = [p for p in order[here + 1 :] if p in active and p not in gone]
    before = [p for p in reversed(order[:here]) if p in active and p not in gone]
    return (after or before or [None])[0]


def close(state: dict) -> None:
    """Close the focused tab; focus the next active agent below it in the panel."""
    pane = os.environ.get("HERDR_PANE_ID")
    panes = call("pane.list")["panes"]
    mine = next((p for p in panes if p["pane_id"] == pane), None)
    if mine is None:
        return
    gone = {p["pane_id"] for p in panes if p["tab_id"] == mine["tab_id"]}
    active = sync(state)
    agents = {a["pane_id"] for a in call("agent.list")["agents"]}
    order = active + [
        p["pane_id"] for p in panes if p["pane_id"] in agents and p["pane_id"] not in active
    ]
    target = next_active(order, active, gone, pane)
    call("tab.close", tab_id=mine["tab_id"])
    if target:
        call("agent.focus", target=target)


def main() -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with (STATE.parent / "lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = load_state()
        if sys.argv[1:] == ["toggle"]:
            toggle(state)
        elif sys.argv[1:] == ["close"]:
            close(state)
        else:
            sync(state)


if __name__ == "__main__":
    main()
