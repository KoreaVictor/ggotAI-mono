"""RoseWeb(화원박사) 컨트롤 트리 정탐 도구 (1회용).

RoseWeb는 Delphi VCL + DevExpress 데스크톱 앱이라 컨트롤 식별자가 불안정하다
(Name 비어 있음, AutomationId=핸들). 필드 addressing 을 좌표/탭순서로 잡기 위한 조사용.

사용:
    python -X utf8 backend/scripts/roseweb_inspect.py tree  <창클래스 또는 이름일부>
    python -X utf8 backend/scripts/roseweb_inspect.py edits <창클래스 또는 이름일부>
    python -X utf8 backend/scripts/roseweb_inspect.py wins
"""

from __future__ import annotations

import sys

import uiautomation as auto

ROSEWEB_PROC = "roseweb"


def _roseweb_windows():
    root = auto.GetRootControl()
    out = []
    for w in root.GetChildren():
        try:
            exe = (w.ProcessId, w.Name or "", w.ClassName or "")
        except Exception:
            continue
        out.append(w)
    # ProcessId 로 거르지 않고 클래스 TFm* 로 식별(멀티 인스턴스 대비 호출측이 지정).
    return out


def _find(substr: str):
    for w in _roseweb_windows():
        if substr.lower() in (w.ClassName or "").lower() or substr.lower() in (w.Name or "").lower():
            return w
    return None


def cmd_wins() -> None:
    for w in _roseweb_windows():
        n = (w.Name or "").strip()
        if n:
            print(w.ProcessId, "|", w.ClassName, "|", repr(n), "|", w.BoundingRectangle)


def cmd_tree(substr: str, max_depth: int = 8, max_nodes: int = 400) -> None:
    win = _find(substr)
    if win is None:
        print(f"[!] '{substr}' 창을 못 찾음")
        return
    print(f"[창] {win.ControlTypeName} name={win.Name!r} class={win.ClassName} rect={win.BoundingRectangle}")
    cnt = [0]

    def walk(c, d):
        if d > max_depth or cnt[0] > max_nodes:
            return
        for ch in c.GetChildren():
            cnt[0] += 1
            print("  " * d, ch.ControlTypeName,
                  "| name=", repr((ch.Name or "")[:40]),
                  "| autoId=", repr(ch.AutomationId),
                  "| class=", ch.ClassName)
            walk(ch, d + 1)

    walk(win, 1)
    print("--- 노드 수:", cnt[0])


def cmd_edits(substr: str) -> None:
    """입력칸(Edit/Combo/*Edit*/Memo)을 상→하·좌→우로 정렬해 좌표·식별자 덤프."""
    win = _find(substr)
    if win is None:
        print(f"[!] '{substr}' 창을 못 찾음")
        return
    rows = []

    def walk(c):
        for ch in c.GetChildren():
            cls = ch.ClassName or ""
            if ch.ControlTypeName in ("EditControl", "ComboBoxControl") or "Edit" in cls or "Memo" in cls:
                r = ch.BoundingRectangle
                rows.append((r.top, r.left, cls, (ch.Name or "")[:24], ch.AutomationId))
            walk(ch)

    walk(win)
    rows.sort()
    for t, l, cls, nm, aid in rows:
        print(f"{t:4},{l:4} | {cls:16} | name={nm!r:26} | id={aid}")
    print("--- 입력칸 수:", len(rows))


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
    elif args[0] == "wins":
        cmd_wins()
    elif args[0] == "tree" and len(args) > 1:
        cmd_tree(args[1])
    elif args[0] == "edits" and len(args) > 1:
        cmd_edits(args[1])
    else:
        print(__doc__)
