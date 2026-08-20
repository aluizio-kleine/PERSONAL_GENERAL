#!/usr/bin/env python3
"""Apply an export from the dashboard back into tasks.yml.

    python3 study/sync_export.py atividades-mestrado.json

The page keeps the viewer's changes in device storage and exports them as JSON.
This folds them into the YAML, which stays the source of truth. Edits are made
as targeted text replacements rather than a YAML round-trip, so the comments and
formatting in tasks.yml survive.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks.yml"

FIELDS = ("title", "course", "type", "due", "due_time", "size", "weight", "status")
# Written unquoted, to match how tasks.yml is hand-written.
BARE = ("status", "size", "type", "course", "due", "weight")


def block_span(text: str, task_id: str) -> tuple[int, int] | None:
    """Character range of one task's block, from its `- id:` to the next one."""
    m = re.search(rf'^  - id: {re.escape(task_id)}\s*$', text, re.M)
    if not m:
        return None
    nxt = re.search(r'^  (?:- id:|# ---)', text[m.end():], re.M)
    return m.start(), (m.end() + nxt.start()) if nxt else len(text)


def set_field(block: str, field: str, value) -> str:
    if value is None or value == "":
        rendered = ""
    elif isinstance(value, (int, float)) or field in BARE:
        rendered = str(value)
    else:
        rendered = '"' + str(value).replace('"', '\\"') + '"'
    line = f"    {field}: {rendered}".rstrip()
    pat = rf'^    {field}:.*$'
    if re.search(pat, block, re.M):
        return re.sub(pat, line, block, count=1, flags=re.M)
    # insert after the id line if the field is not there yet
    return re.sub(r'^(  - id: .*)$', r'\1\n' + line, block, count=1, flags=re.M)


def render_new(task: dict) -> str:
    out = [f'  - id: {task.get("id")}']
    for f in ("course", "title", "type", "due", "due_time", "size", "weight", "status"):
        if f not in task:
            continue
        v = task[f]
        if v is None or v == "":
            out.append(f"    {f}:")
        elif isinstance(v, (int, float)) or f in BARE:
            out.append(f"    {f}: {v}")
        else:
            out.append(f'    {f}: "{str(v)}"')
    out.append('    notes: "Criada por você no painel."')
    return "\n".join(out) + "\n\n"


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("uso: python3 study/sync_export.py <arquivo.json>")
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    text = TASKS.read_text(encoding="utf-8")
    log: list[str] = []
    missing: list[str] = []

    def apply_status(ids, status):
        nonlocal text
        for tid in ids or []:
            span = block_span(text, tid)
            if not span:
                missing.append(tid)
                continue
            s, e = span
            block = set_field(text[s:e], "status", status)
            text = text[:s] + block + text[e:]
            log.append(f"  {status:5}  {tid}")

    apply_status(data.get("concluidas"), "done")
    apply_status(data.get("reabertas"), "todo")

    for tid, patch in (data.get("editadas") or {}).items():
        span = block_span(text, tid)
        if not span:
            missing.append(tid)
            continue
        s, e = span
        block = text[s:e]
        for f in FIELDS:
            if f in patch:
                block = set_field(block, f, patch[f])
        text = text[:s] + block + text[e:]
        log.append(f"  edit   {tid}: {', '.join(k for k in patch if k in FIELDS)}")

    novas = data.get("novas") or []
    if novas:
        text = text.rstrip("\n") + "\n\n" + "".join(render_new(t) for t in novas)
        log += [f"  nova   {t.get('id')}: {t.get('title','')}" for t in novas]

    TASKS.write_text(text, encoding="utf-8")

    print(f"exportado em {data.get('exported_at','?')}")
    print("\n".join(log) if log else "  (nada a aplicar)")
    if missing:
        print("\nIDs não encontrados em tasks.yml:", ", ".join(missing))
    if data.get("passos"):
        n = sum(len(v) for v in data["passos"].values())
        print(f"\nAtenção: {n} passo(s) marcados não foram gravados. O progresso da "
              f"checklist vive só no aparelho; o YAML guarda as atividades, não os passos.")


if __name__ == "__main__":
    main()
