"""RoseWebAutomator — 화원박사 ROSEWeb(Delphi 데스크톱 앱)에 주문을 자동 입력한다.

FlowerNT 가 CDP 로 브라우저를 조종하는 것과 달리, 여기는 Windows UI Automation 으로
네이티브 창의 컨트롤을 찾아 `SetFocus()`+`SendKeys()` 로 넣는다. 즉 **입력하는 몇 초 동안
실제 키보드 포커스를 가져간다** — 사장님이 동시에 타이핑하면 충돌한다.

`uiautomation` 은 Windows 전용이자 `[roseweb]` extra 라, **모듈 최상단에서 import 하지
않는다**. factory 가 이 모듈을 import 하므로, 최상단에 두면 리눅스 CI 와 FlowerNT 전용
설치본에서 수집엔진이 아예 못 뜬다(FlowerNT 가 playwright 를 호출 시점에 import 하는 것과
같은 이유). 호출 시점 import 가 실패하면 singleton_macro 가 백업(manual) 경로로 흘린다.
"""

from __future__ import annotations

import logging
import subprocess
import time

from ggotaiorder.rpa.models import RpaOrder
from ggotaiorder.rpa.roseweb import keys, layout, locator, mapping, product

logger = logging.getLogger(__name__)

# 줄바꿈을 살려야 하는 칸(메모). 나머지는 한 줄로 눌러 넣는다 — 자세한 이유는 keys 참조.
_MULTILINE_FIELDS = frozenset({"card"})

# 폼 크기 허용 오차(px). 창틀 반올림으로 1px 정도는 흔들린다.
_FORM_SIZE_TOLERANCE = 2

# RoseWeb 의 확인·경고창. Delphi TMessageForm 이 주로 뜨고 표준 대화상자도 섞인다.
_DIALOG_CLASSES = ("TMessageForm", "#32770")


def _uia():
    """uiautomation 모듈(호출 시점 import). 미설치면 ImportError 가 그대로 올라간다."""
    import uiautomation

    return uiautomation


class RoseWebAutomator:
    """RoseWeb 자동입력. 계약은 `rpa.automator.ProgramAutomator`."""

    def __init__(self, url: str | None = None, login_id: str | None = None,
                 login_password: str | None = None, auto_submit: bool = False) -> None:
        # url/login_id/login_password 는 다른 어댑터와 시그니처를 맞추기 위한 것이다.
        # 화원박사는 실행하면 자동 로그인이라 자격증명을 쓰지 않는다.
        self._auto_submit = bool(auto_submit)
        # 창 전환·포커스 이동이 반영될 때까지의 짧은 대기. Delphi 폼은 SetFocus 직후
        # 바로 키를 보내면 놓치는 경우가 있다.
        self._ui_pause = 0.4
        self._key_wait = 0.03
        self._clip_pause = 0.15   # 클립보드 반영 대기
        self._lookup_pause = 1.2  # 팝업 검색·선택 반영 대기(DB 조회라 느리다)

    # --- 창 찾기 --------------------------------------------------------
    def _find_window(self, class_name: str):
        """최상위 창 중 클래스가 일치하는 첫 창. 없으면 None."""
        auto = _uia()
        for w in auto.GetRootControl().GetChildren():
            try:
                if (w.ClassName or "") == class_name:
                    return w
            except Exception:      # 창이 그새 닫히면 속성 접근이 터진다
                continue
        return None

    def _wait_window(self, class_name: str, timeout_s: float = 15.0, poll_s: float = 0.5):
        deadline = time.monotonic() + timeout_s
        while True:
            win = self._find_window(class_name)
            if win is not None:
                return win
            if time.monotonic() >= deadline:
                return None
            time.sleep(poll_s)

    def _main_window(self):
        """메인 창(TFmMain). 없으면 None."""
        return self._find_window(layout.MAIN_CLASS)

    def _process_running(self) -> bool:
        """roseweb.exe 가 이미 떠 있는가.

        창이 아직 안 뜬 기동 중(스플래시)에 또 실행하면 인스턴스가 둘이 된다.
        판정 실패는 '안 떠 있음'으로 본다 — 그러면 아래 로직이 기존대로 실행을 시도한다.
        """
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {layout.PROC_NAME}.exe", "/NH"],
                capture_output=True, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            logger.debug("RoseWeb 프로세스 확인 실패(%s)", type(exc).__name__)
            return False
        # 한국어 Windows 의 tasklist 는 CP949 로 출력한다. text=True 로 받으면 UTF-8
        # 디코딩이 터져(실측) 결과가 늘 비고, 그러면 이미 떠 있는 RoseWeb 을 또 실행하게
        # 된다. 찾는 문자열이 ASCII 라 디코딩하지 않고 바이트 그대로 뒤진다.
        needle = f"{layout.PROC_NAME}.exe".encode("ascii").lower()
        return needle in (proc.stdout or b"").lower()

    # --- 기동 -----------------------------------------------------------
    def _ensure_running(self, timeout_s: float = 25.0, poll_s: float = 1.0) -> bool:
        """RoseWeb 이 떠 있게 만든다. 이미 떠 있으면 즉시 True."""
        if self._main_window() is not None:
            return True

        if self._process_running():
            logger.info("RoseWeb 프로세스는 있으나 메인 창 미검출 — 기동 대기")
        else:
            logger.info("RoseWeb 미기동 — 실행: %s", layout.EXE_PATH)
            # OCX/DLL 을 상대경로로 찾으므로 반드시 설치 폴더에서 실행해야 한다.
            subprocess.Popen([layout.EXE_PATH], cwd=layout.WORKDIR)

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            time.sleep(poll_s)
            win = self._main_window()
            if win is not None:
                logger.info("RoseWeb 기동 확인: %s", (getattr(win, "Name", "") or "")[:60])
                return True
        logger.warning("RoseWeb 기동 확인 실패(%.0f초 대기)", timeout_s)
        return False

    # --- 주문폼 열기 -----------------------------------------------------
    def _open_new_order(self):
        """F2(주문관리 목록) → Insert(입력 폼). 열린 폼을 돌려준다."""
        auto = _uia()
        # 이미 폼이 있는데 Insert 를 또 누르면 같은 자리에 폼이 겹쳐 뜬다(실측). 그러면
        # 어느 쪽에 값이 들어갔는지 알 수 없다. is_program_running 이 먼저 막지만,
        # 직접 호출되는 경로를 위해 여기서도 막는다.
        if self._find_window(layout.FORM_CLASS) is not None:
            raise RuntimeError("RoseWeb 주문폼이 이미 열려 있다 — 겹쳐 열지 않는다")

        listw = self._find_window(layout.LIST_CLASS)
        if listw is None:
            main = self._main_window()
            if main is None:
                raise RuntimeError("RoseWeb 메인 창(TFmMain) 미검출")
            main.SetFocus()
            time.sleep(self._ui_pause)
            auto.SendKeys(layout.OPEN_LIST_KEY, waitTime=self._key_wait)
            listw = self._wait_window(layout.LIST_CLASS)
            if listw is None:
                raise RuntimeError(f"RoseWeb 주문관리 창({layout.LIST_CLASS}) 미검출")

        listw.SetFocus()
        time.sleep(self._ui_pause)
        auto.SendKeys(layout.OPEN_NEW_KEY, waitTime=self._key_wait)
        form = self._wait_window(layout.FORM_CLASS)
        if form is None:
            raise RuntimeError(f"RoseWeb 주문폼({layout.FORM_CLASS}) 미검출")
        return form

    def _collect_edits(self, form) -> list:
        """폼 안의 입력칸. 그리드 스크롤 밖 유령 행은 걸러낸다(locator 참조)."""
        found: list = []

        def walk(ctrl, depth=0):
            if depth > 12:
                return
            for child in ctrl.GetChildren():
                try:
                    cls = child.ClassName or ""
                    if (child.ControlTypeName in ("EditControl", "ComboBoxControl")
                            or "Edit" in cls or "Memo" in cls):
                        found.append(child)
                    walk(child, depth + 1)
                except Exception:
                    continue

        walk(form)
        return locator.visible_edits(found)

    def _type(self, ctrl, value: str, multiline: bool = False) -> None:
        """칸의 기존 값을 선택한 뒤 **클립보드로 붙여넣고** {Tab} 으로 확정한다.

        키를 하나씩 보내는 방식(SendKeys)은 쓰지 않는다 — 실측에서 한글이 깨졌다
        ('김발주'→'주癰償', '축 개업'→'내?개업'). DB 연동 칸의 자동완성과 IME 조합이
        엉키는 것으로 보인다. 날짜 칸도 타이핑하면 마스크가 어긋나는데('2026-  -07')
        붙여넣기는 정확하다.

        지우기는 Delete 없이 **선택 상태에서 그대로 덮어쓴다**. Ctrl+A 후 Delete 를
        먼저 하면 앞에 조합 잔여물('?김발주')이 남는 경우가 있었다.
        """
        auto = _uia()
        ctrl.SetFocus()
        time.sleep(self._ui_pause)
        auto.SendKeys("{Ctrl}a", waitTime=self._key_wait)
        auto.SetClipboardText(keys.prepare(value, multiline=multiline))
        time.sleep(self._clip_pause)
        auto.SendKeys("{Ctrl}v", waitTime=self._key_wait)
        # DB 연동 칸(날짜·금액)은 확정해야 값이 반영된다.
        auto.SendKeys("{Tab}", waitTime=self._key_wait)

    def _save(self, form) -> None:
        """'저장' 버튼 클릭. 버튼이 UIA 에 안 보여 좌표로 누른다(layout 참조)."""
        auto = _uia()
        r = form.BoundingRectangle
        x, y = layout.SAVE_BUTTON_POS
        logger.info("RoseWeb 저장 클릭 (%s,%s)", r.left + x, r.top + y)
        auto.Click(r.left + x, r.top + y)

    # --- ProgramAutomator 계약 -------------------------------------------
    def is_program_running(self) -> bool:
        try:
            if not self._ensure_running():
                return False
            # 사장님이 이미 주문폼을 열어두고 작업 중일 수 있다. 거기에 타이핑하면
            # 그분이 입력하던 내용을 덮어쓴다. 미구동과 같이 취급해 백업(manual)으로
            # 흘리면 재시도 스캐너가 나중에 다시 집는다.
            if self._find_window(layout.FORM_CLASS) is not None:
                logger.info("RoseWeb 주문폼이 이미 열려 있음 — 자동입력을 미룬다")
                return False
            return True
        except Exception:
            # 여기서 예외를 흘리면 주문이 백업 없이 사라진다(singleton_macro 참조).
            logger.exception("RoseWeb 구동 확인 실패")
            return False

    def input_order(self, order: RpaOrder) -> None:
        if not self._ensure_running():
            raise RuntimeError("RoseWeb 미기동 — 자동입력 불가")

        form = self._open_new_order()
        rect = form.BoundingRectangle
        width, height = rect.right - rect.left, rect.bottom - rect.top
        exp_w, exp_h = layout.FORM_SIZE
        if (abs(width - exp_w) > _FORM_SIZE_TOLERANCE
                or abs(height - exp_h) > _FORM_SIZE_TOLERANCE):
            # 좌표는 실측 크기 기준이다. 크기가 다르면 칸 위치가 통째로 어긋나
            # 엉뚱한 칸에 값이 들어간다(=오배송). 채우기 전에 멈춘다.
            raise RuntimeError(
                f"RoseWeb 폼 크기가 실측과 다르다({width}x{height}, 실측 {exp_w}x{exp_h}) "
                "— layout 재측정 필요"
            )

        edits = self._collect_edits(form)
        values = mapping.order_to_values(order)

        # 먼저 전부 찾아본다. 하나라도 없으면 레이아웃이 어긋난 것이라 나머지 칸도
        # 믿을 수 없다 — 부분 입력을 남기지 않고 통째로 중단한다(→ 백업/수동입력).
        targets = []
        missing = []
        for key, value in values.items():
            pos = layout.FIELD_POSITIONS.get(key)
            if pos is None:
                logger.warning("RoseWeb layout 에 없는 필드 — 건너뜀 key=%s", key)
                continue
            ctrl = locator.nearest_edit(edits, pos[0], pos[1], rect.left, rect.top)
            if ctrl is None:
                missing.append(key)
                continue
            targets.append((key, ctrl, value))
        if missing:
            raise RuntimeError(f"RoseWeb 입력칸 미검출: {', '.join(missing)}")

        # 붙여넣기로 입력하므로 클립보드를 잠깐 빌려 쓴다. 사장님이 복사해 둔 내용을
        # 말없이 날리지 않도록 끝나면 되돌린다.
        clipboard_backup = self._read_clipboard()
        try:
            # 상품코드부터. 코드가 없으면 그 행은 주문으로 성립하지 않아(금액 미계산·
            # 주문자료수 제외) 나머지를 채워봐야 소용없다. 코드를 고르면 상품명 칸에는
            # 마스터 이름이 들어오는데, 뒤이어 targets 의 product_name 이 원문으로 덮는다.
            product_name = values.get("product_name")
            if product_name:
                code_cell = locator.nearest_edit(
                    edits, layout.PRODUCT_CODE_POS[0], layout.PRODUCT_CODE_POS[1],
                    rect.left, rect.top,
                )
                if code_cell is None:
                    raise RuntimeError("RoseWeb 상품코드 칸 미검출")
                self._pick_product_code(code_cell, product_name)
                self._abort_on_dialog("상품코드 선택")

            for key, ctrl, value in targets:
                self._type(ctrl, value, multiline=key in _MULTILINE_FIELDS)
                # 대화상자가 뜨면 폼이 비활성이라 이후 입력이 전부 사라진다.
                self._abort_on_dialog(f"key={key}")
        finally:
            self._restore_clipboard(clipboard_backup)
        logger.info("RoseWeb 채우기 완료 id=%s 필드 %d개",
                    order.order_detail_id, len(targets))

        if self._auto_submit:
            self._save(form)
        else:
            logger.info("RoseWeb auto_submit=N — 채우기만 하고 저장하지 않는다")

    # --- 상품코드 선택 ---------------------------------------------------
    def _open_product_lookup(self, code_cell):
        """상품코드 칸에서 {F2} 로 상품코드선택 팝업을 연다."""
        auto = _uia()
        code_cell.SetFocus()
        time.sleep(self._ui_pause)
        auto.SendKeys(layout.OPEN_PRODUCT_LOOKUP_KEY, waitTime=self._key_wait)
        popup = self._wait_window(layout.LOOKUP_CLASS, timeout_s=10.0, poll_s=0.4)
        if popup is None:
            raise RuntimeError(f"RoseWeb 상품코드선택 팝업({layout.LOOKUP_CLASS}) 미검출")
        return popup

    def _search_and_pick(self, popup, term: str) -> bool:
        """팝업에서 term 으로 검색하고 '선택'을 누른다. 골라졌으면 True.

        결과가 없으면 '선택'을 눌러도 아무 일이 없고 팝업이 그대로 남는다(실측).
        그것으로 성공·실패를 가른다 — 목록의 행은 UIA 에 안 보여 직접 확인할 수 없다.
        """
        auto = _uia()
        rect = popup.BoundingRectangle
        search_box = self._lookup_search_box(popup)
        search_box.SetFocus()
        time.sleep(self._ui_pause)
        auto.SendKeys("{Ctrl}a", waitTime=self._key_wait)
        auto.SetClipboardText(keys.prepare(term))
        time.sleep(self._clip_pause)
        auto.SendKeys("{Ctrl}v", waitTime=self._key_wait)
        time.sleep(self._ui_pause)

        auto.Click(rect.left + layout.LOOKUP_SEARCH_BUTTON_POS[0],
                   rect.top + layout.LOOKUP_SEARCH_BUTTON_POS[1])
        time.sleep(self._lookup_pause)
        auto.Click(rect.left + layout.LOOKUP_PICK_BUTTON_POS[0],
                   rect.top + layout.LOOKUP_PICK_BUTTON_POS[1])
        time.sleep(self._lookup_pause)
        return self._find_window(layout.LOOKUP_CLASS) is None

    def _lookup_search_box(self, popup):
        """팝업의 검색 입력칸(콤보 안 Edit). 폼과 같이 좌표로 찾는다.

        '마지막으로 발견된 Edit' 같은 순서 의존은 못 쓴다 — 검색을 한 번 하고 나면
        목록 그리드가 편집 컨트롤을 더 노출해 순서가 바뀐다(실측: 두 번째 검색에서
        검색칸을 못 찾았다).
        """
        found = []

        def walk(ctrl, depth=0):
            if depth > 6:
                return
            for child in ctrl.GetChildren():
                try:
                    if child.ControlTypeName in ("EditControl", "ComboBoxControl"):
                        found.append(child)
                    walk(child, depth + 1)
                except Exception:
                    continue

        # 검색 직후에는 팝업이 잠깐 재구성돼 자식이 안 잡히는 순간이 있다(실측: 두 번째
        # 검색에서 미검출). 잠시 뒤 다시 보면 멀쩡하므로 몇 번 재시도한다.
        for attempt in range(5):
            found.clear()
            walk(popup)
            rect = popup.BoundingRectangle
            box = locator.nearest_edit(found, layout.LOOKUP_SEARCH_BOX_POS[0],
                                       layout.LOOKUP_SEARCH_BOX_POS[1], rect.left, rect.top)
            if box is not None:
                return box
            time.sleep(self._ui_pause)
        raise RuntimeError("RoseWeb 상품 검색칸 미검출")

    def _close_product_lookup(self, popup) -> None:
        auto = _uia()
        rect = popup.BoundingRectangle
        auto.Click(rect.left + layout.LOOKUP_CANCEL_BUTTON_POS[0],
                   rect.top + layout.LOOKUP_CANCEL_BUTTON_POS[1])
        time.sleep(self._lookup_pause)

    def _pick_product_code(self, code_cell, product_name: str) -> None:
        """상품명을 마스터 이름으로 바꿔 검색·선택해 상품코드를 채운다.

        상품코드가 비면 그 행은 주문으로 성립하지 않는다 — 금액·총합계금액이 계산되지
        않고 '주문자료수'에도 안 잡힌다(사장님 실측). 그래서 코드는 반드시 있어야 한다.

        ⚠️ **검색은 단 한 번만 한다.** 마스터에 없는 말로 검색한 뒤 '선택'을 누르면
        RoseWeb 이 죽고(`Access violation at address 00000000`) 그 뒤로는 팝업을 닫아도
        오류창이 따라붙는다(실측). 결과 목록은 UIA 에 안 보여 누르기 전에 확인할 수도
        없다. 그래서 `product.resolve_search_term` 이 **마스터에 있는 이름만** 내놓고,
        그래도 실패하면 재시도하지 않고 그만둔다(→ 백업/수동입력).
        """
        term = product.resolve_search_term(product_name)
        if term != product_name:
            logger.info("RoseWeb 상품 검색어 변환: %r → %r", product_name, term)

        popup = self._open_product_lookup(code_cell)
        if self._search_and_pick(popup, term):
            return

        # 여기 오면 마스터가 실측과 달라진 것이다(꽃집마다 다르다). 다른 말로 또
        # 눌러보면 프로그램을 죽이므로 그냥 닫고 물러난다.
        self._close_product_lookup(popup)
        raise RuntimeError(
            f"RoseWeb 상품코드를 고르지 못했다(상품명 {product_name!r} → 검색어 {term!r}) "
            "— 상품 마스터가 바뀌었는지 확인 필요"
        )

    # --- 대화상자 -------------------------------------------------------
    def _blocking_dialog(self):
        """떠 있는 모달 대화상자. 없으면 None.

        RoseWeb 의 확인·경고창은 Windows 표준(#32770)이 아니라 Delphi `TMessageForm`
        이다(실측). 이게 뜨면 주문폼이 통째로 비활성(IsEnabled=False)이 되어 이후
        입력이 전부 허공으로 간다 — 그래서 한 칸 넣을 때마다 확인한다.
        """
        for cls in _DIALOG_CLASSES:
            win = self._find_window(cls)
            if win is not None:
                return win
        return None

    def _describe_dialog(self, dlg) -> str:
        """로그에 남길 설명.

        ⚠️ 본문 텍스트('배달일자를 확인하세요' 등)는 Delphi 라벨이라 UIA 에 안 보인다.
        제목과 버튼 이름까지만 남길 수 있다.
        """
        try:
            buttons = [(c.Name or "").strip() for c in dlg.GetChildren()
                       if c.ControlTypeName == "ButtonControl"]
            return f"제목={(dlg.Name or '').strip()!r} 버튼={buttons}"
        except Exception:
            return "설명 실패"

    def _dismiss_dialog(self, dlg) -> bool:
        """버튼이 하나뿐인 안내 대화상자만 닫는다.

        선택지가 여럿이면(저장할까요? 등) 무엇을 누를지 우리가 정할 일이 아니라 손대지
        않는다. 모달을 남겨두면 사장님 화면이 막히지만, 임의로 눌러 주문을 잘못 확정하는
        것보다는 낫다.
        """
        try:
            buttons = [c for c in dlg.GetChildren() if c.ControlTypeName == "ButtonControl"]
            if len(buttons) != 1:
                return False
            buttons[0].Click()
            return True
        except Exception:
            return False

    def _abort_on_dialog(self, where: str) -> None:
        dlg = self._blocking_dialog()
        if dlg is None:
            return
        desc = self._describe_dialog(dlg)
        closed = self._dismiss_dialog(dlg)
        raise RuntimeError(
            f"RoseWeb 대화상자로 입력 중단({where}): {desc}"
            + ("" if closed else " — 버튼이 여럿이라 닫지 않음, 화면 확인 필요")
        )

    # --- 클립보드 -------------------------------------------------------
    def _read_clipboard(self) -> str | None:
        try:
            return _uia().GetClipboardText()
        except Exception:
            return None

    def _restore_clipboard(self, text: str | None) -> None:
        if text is None:
            return
        try:
            _uia().SetClipboardText(text)
        except Exception:
            logger.debug("클립보드 복원 실패")
