#!/usr/bin/env python3
"""Trigger-body management for the ABV dashboard — same discipline as the FY26
dashboard's send_trigger.py: never hand-retype the prompt, always verify the echo.

  python3 abv_send_trigger.py create  > /tmp/abv_create.json   # body for RemoteTrigger create
  python3 abv_send_trigger.py update  > /tmp/abv_update.json   # body for RemoteTrigger update
  python3 abv_send_trigger.py verify  /tmp/abv_echo.json       # diff echo + assert invariants

Resends are documented to drop fields silently — one lost mcp_config type/url, one
typo'd artifact UUID. verify() is the checklist that caught those, grown per incident.
"""
import difflib
import json
import re
import sys

PROMPT = "abv_trigger_prompt.md"
CONFIG = "abv_trigger_config.json"


def load():
    with open(CONFIG) as f:
        cfg = json.load(f)
    with open(PROMPT) as f:
        prompt = f.read()
    return cfg, prompt


def _ccr(cfg, prompt):
    return {
        "environment_id": cfg["environment_id"],
        "events": [
            cfg["permission_event"],
            {"data": {"message": {"content": prompt, "role": "user"},
                      "parent_tool_use_id": None, "session_id": "",
                      "type": "user", "uuid": cfg["prompt_event_uuid"]}},
        ],
        "session_context": cfg["session_context"],
    }


def create():
    cfg, prompt = load()
    return {
        "name": cfg["name"],
        "cron_expression": cfg["cron_expression"],
        "chat_project_id": cfg["chat_project_id"],
        "enabled": True,
        # Monday reaches a scheduled session through mcp_connections, NOT mcp_config.
        # The FY26 trigger's mcp_config holds only the remote-devices bridge, which is
        # not mounted in scheduled sessions — copying it verbatim would ship a trigger
        # with no board access at all.
        "mcp_connections": cfg["mcp_connections"],
        "job_config": {"ccr": _ccr(cfg, prompt)},
    }


def update():
    cfg, prompt = load()
    return {"job_config": {"ccr": _ccr(cfg, prompt)},
            "mcp_connections": cfg["mcp_connections"]}


def verify(echo_path):
    cfg, prompt = load()
    raw = open(echo_path).read()
    ok = True

    content = None
    try:
        j = json.loads(raw)
        content = j["trigger"]["job_config"]["ccr"]["events"][1]["data"]["message"]["content"]
    except Exception:
        m = re.search(r'"content":"(.*?)","role":"user"', raw, re.S)
        if m:
            content = m.group(1).encode().decode("unicode_escape")
    if content is None:
        print("✗ cannot locate the echoed prompt in", echo_path)
        return 1

    diff = list(difflib.unified_diff(prompt.splitlines(), content.splitlines(),
                                     PROMPT, "echo", lineterm=""))
    if diff:
        ok = False
        print("✗ prompt drift — %d changed lines:"
              % (sum(1 for l in diff if l[:1] in "+-") - 2))
        for line in diff[:40]:
            print("  ", line)
    else:
        print("✓ echoed prompt is byte-identical to", PROMPT)

    missing = [i for i in cfg["invariants"]
               if i not in raw and i.replace('"', '\\"') not in raw]
    if missing:
        ok = False
        for i in missing:
            print("✗ invariant MISSING from echo:", i)
    else:
        print("✓ all %d invariants present" % len(cfg["invariants"]))

    for key, want in (("cron_expression", cfg["cron_expression"]),
                      ("chat_project_id", cfg["chat_project_id"]),
                      ("environment_id", cfg["environment_id"])):
        if want not in raw:
            ok = False
            print("✗ %s missing or changed — expected %s" % (key, want))
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("create", "update", "verify"):
        print(__doc__)
        sys.exit(2)
    if sys.argv[1] == "verify":
        sys.exit(verify(sys.argv[2]))
    print(json.dumps(create() if sys.argv[1] == "create" else update(), ensure_ascii=False))
