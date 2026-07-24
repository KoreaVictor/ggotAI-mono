"""RoseWeb(화원박사) 컨트롤 트리 정탐 도구 (1회용).

RoseWeb는 Delphi VCL + DevExpress 데스크톱 앱이라 컨트롤 식별자가 불안정하다
(Name 비어 있음, AutomationId=핸들). 필드 addressing 을 좌표/탭순서로 잡기 위한 조사용.

사용:
    python -X utf8 backend/scripts/roseweb_inspect.py tree  <창클래스 또는 이름일부>
    python -X utf8 backend/scripts/roseweb_inspect.py edits <창클래스 또는 이름일부>
    python -X utf8 backend/scripts/roseweb_inspect.py dump  <창클래스> <출력.json>
    python -X utf8 backend/scripts/roseweb_inspect.py wins

`dump` 는 입력칸과 **라벨(정적 텍스트)** 을 폼 기준 상대좌표로 함께 뽑아 JSON 으로 남긴다.
칸에 값을 넣어보지 않고 라벨-칸 짝으로 필드를 식별하기 위한 것이다 — lookup 칸에 블라인드로
타이핑하면 검색 팝업·'고객Error' 대화상자가 연쇄로 뜨기 때문에 읽기만으로 매핑해야 한다.
"""

from __future__ import annotations

import json
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


def _is_input(ctrl) -> bool:
    cls = ctrl.ClassName or ""
    return (
        ctrl.ControlTypeName in ("EditControl", "ComboBoxControl")
        or "Edit" in cls
        or "Memo" in cls
    )


def _is_label(ctrl) -> bool:
    """정적 텍스트(라벨). Delphi 는 TLabel/TStaticText, DevExpress 는 그룹 헤더 등."""
    name = (ctrl.Name or "").strip()
    if not name:
        return False
    if _is_input(ctrl):
        return False
    return ctrl.ControlTypeName in ("TextControl", "GroupControl", "HeaderItemControl")


def cmd_dump(substr: str, out_path: str) -> None:
    """입력칸·라벨·버튼·라디오를 폼 기준 상대좌표로 JSON 덤프한다(읽기 전용)."""
    win = _find(substr)
    if win is None:
        print(f"[!] '{substr}' 창을 못 찾음")
        return
    wr = win.BoundingRectangle
    ox, oy = wr.left, wr.top

    inputs, labels, others = [], [], []

    def rec(ch, path, parent):
        r = ch.BoundingRectangle
        pr = parent.BoundingRectangle
        return {
            # 조상 클래스 체인 + 부모 사각형. 그리드 밑 편집 컨트롤은 화면에 안 보이는 행까지
            # 노출되는데, 그것들은 부모(그리드) 영역 밖으로 삐져나온다 — 그 점으로 거른다.
            "path": path,
            "p_dx": pr.left - ox,
            "p_dy": pr.top - oy,
            "p_w": pr.right - pr.left,
            "p_h": pr.bottom - pr.top,
            "cls": ch.ClassName or "",
            "type": ch.ControlTypeName,
            "name": (ch.Name or "")[:60],
            "auto_id": ch.AutomationId,
            # 폼 좌상단 기준 상대좌표. 절대좌표는 창을 옮기면 바뀐다.
            "dx": r.left - ox,
            "dy": r.top - oy,
            "w": r.right - r.left,
            "h": r.bottom - r.top,
            # 그리드는 화면에 안 보이는 행의 편집 컨트롤까지 UIA 에 노출한다. 그것들이
            # 아래쪽 실제 입력칸과 위치가 겹치므로 반드시 걸러야 한다.
            "offscreen": bool(ch.IsOffscreen),
            "enabled": bool(ch.IsEnabled),
        }

    def walk(c, depth=0, path=""):
        if depth > 12:
            return
        for ch in c.GetChildren():
            try:
                cls = ch.ClassName or "?"
                child_path = f"{path}/{cls}" if path else cls
                if _is_input(ch):
                    inputs.append(rec(ch, path, c))
                elif _is_label(ch):
                    labels.append(rec(ch, path, c))
                elif ch.ControlTypeName in ("ButtonControl", "RadioButtonControl", "CheckBoxControl"):
                    others.append(rec(ch, path, c))
                walk(ch, depth + 1, child_path)
            except Exception:
                pass

    walk(win)
    inputs.sort(key=lambda d: (d["dy"], d["dx"]))
    labels.sort(key=lambda d: (d["dy"], d["dx"]))
    others.sort(key=lambda d: (d["dy"], d["dx"]))

    data = {
        "window": {
            "name": win.Name, "cls": win.ClassName,
            "left": ox, "top": oy,
            "w": wr.right - ox, "h": wr.bottom - oy,
        },
        "inputs": inputs, "labels": labels, "others": others,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"창 {win.ClassName} {wr.right - ox}x{wr.bottom - oy} @ ({ox},{oy})")
    print(f"입력칸 {len(inputs)} · 라벨 {len(labels)} · 버튼/라디오 {len(others)} → {out_path}")


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
    elif args[0] == "dump" and len(args) > 2:
        cmd_dump(args[1], args[2])
    else:
        print(__doc__)
