"""RoseWeb(화원박사 `TFmju1inp`) 주문폼 레이아웃 실측 상수.

컨트롤 식별자(AutomationId=핸들)는 폼을 다시 열 때마다 바뀌므로 쓸 수 없다. 대신 **폼
좌상단 기준 상대좌표**로 컨트롤을 찾는다(`locator` 참조). 값은 2026-07-24 라이브 실측
(build 208.5.1, 폼 1076x854). 폼 크기나 프로그램 버전이 바뀌면 재측정해야 한다.

실측 방법·근거는 `docs/superpowers/specs/2026-07-23-roseweb-spike-findings.md` 참조.
정탐 도구: `backend/scripts/roseweb_inspect.py dump TFmju1inp <out.json>`.

## 이 파일을 쓰는 쪽이 반드시 지켜야 할 두 가지

1. **그리드 유령 행을 걸러라.** 상품 그리드는 화면에 3줄만 보이는데 UIA 에는 화면 밖 행의
   편집 컨트롤까지 노출된다(실측 61개 중 42개). 그것들이 배달장소·경조사어 같은 아래쪽
   실제 칸과 위치가 겹친다. 판별법 = **부모(그리드 패널) 세로 영역을 벗어난 컨트롤은 버린다**
   (`IsOffscreen` 은 전부 False 라 쓸 수 없다).
2. **매칭 반경은 좁게.** 폼을 닫았다 열어도 좌표는 ±1px 안에서 재현되고(실측 71개 전부 동일,
   차이는 dy 1px 뿐), 목표 칸과 두 번째로 가까운 컨트롤 사이는 최소 26px 다. 그래서
   `FIELD_MATCH_RADIUS` 를 넉넉잡아 12px 로 둔다 — 넓게 잡으면 칸이 사라졌을 때 조용히
   옆 칸을 집는다.
"""

from __future__ import annotations

EXE_PATH = r"C:\Roseweb\prog\roseweb.exe"
WORKDIR = r"C:\Roseweb\prog"          # OCX/DLL 로드 때문에 이 폴더에서 실행해야 한다
PROC_NAME = "roseweb"

MAIN_CLASS = "TFmMain"                # 메인 창(자동 로그인 완료 시 제목에 '(관리자)')
LIST_CLASS = "TFmJumun"               # 주문판매관리 목록 창
FORM_CLASS = "TFmju1inp"              # 주문판매관리 세부내역 = 입력 폼

# 실측 폼 크기. 좌표는 이 크기 기준이라, 다르면 재측정이 필요하다는 신호다.
FORM_SIZE = (1076, 854)

# 신규 주문폼 열기 = 메인창에서 F2(목록 창) → 목록 창에서 Insert(입력 폼).
# 계획서에는 문자열 하나(OPEN_NEW_ORDER)로 잡았으나 실제로는 창을 갈아타는 2단계라
# 단계별 상수로 나눈다. OPEN_NEW_ORDER 는 사람이 읽는 설명으로만 남긴다.
OPEN_LIST_KEY = "{F2}"
OPEN_NEW_KEY = "{Insert}"
OPEN_NEW_ORDER = "TFmMain 에 포커스 → {F2} → TFmJumun 대기 → 포커스 → {Insert} → TFmju1inp 대기"

# 상품명 칸은 자유 입력이다(2026-07-24 실측으로 정정 — 스파이크 기록은 반대였다).
# '장미'·'동양란' 을 넣고 {Tab} 으로 확정해도 값이 그대로 남고 팝업도 뜨지 않는다.
# 따라서 상품 lookup 서브루틴 없이 상품명을 그대로 타이핑한다.
PRODUCT_DIRECT_TYPE = True

# ⚠️ 다만 **상품코드는 비워진 채로 남는다.** 정확한 마스터 상품명을 넣어도 코드가 자동으로
# 붙지 않는다(실측). 코드를 채우려면 상품코드 칸의 돋보기로 '상품코드선택'(TFmCodesel)
# 팝업에서 골라야 한다. 코드 없이 저장이 되는지는 **auto_submit=Y 저장 검증에서 확인할 것**.
LOOKUP_CLASS = "TFmCodesel"

# 필드키 → 폼 좌상단 기준 상대 (dx, dy) = 컨트롤 좌상단.
# 키 집합은 mapping.order_to_values 의 반환 키와 일치해야 한다.
FIELD_POSITIONS: dict[str, tuple[int, int]] = {
    # 발주자(주문한 사람)
    "orderer_name": (124, 143),        # TdxDBEdit 160x25
    "orderer_phone": (348, 147),       # TdxDBEdit 144x25 (라벨 '휴대폰')
    # 상품 그리드 1행
    "product_name": (172, 275),        # TdxDBEdit 278x25 (자유 입력)
    "unit_price": (504, 276),          # TRxDBCalcEdit 94x24 (단가)
    "quantity": (612, 275),            # TRxDBCalcEdit 46x24
    # 배달
    "delivery_date": (105, 402),       # TdxDBDateEdit 116x25
    "delivery_time": (503, 402),       # TdxDBPickEdit 321x25
    "delivery_place": (99, 430),       # TdxDBEdit 464x25
    "receiver_name": (790, 431),       # TdxDBEdit 199x25
    "receiver_phone": (640, 458),      # TdxDBEdit 151x25 (라벨 '핸드폰')
    # 리본·카드
    "ribbon_congrats": (99, 487),      # TdxDBPickEdit 561x25 (경조사어)
    "ribbon_sender": (99, 518),        # TdxDBPickEdit 781x25 (보내는이)
    "card": (99, 545),                 # TdxDBMemo 476x83 (카드내용)
}

# 상품코드 칸(그리드 1행 첫 열). 값을 넣는 칸이 아니라 상품 lookup 의 진입점이라
# FIELD_POSITIONS 와 분리해 둔다.
PRODUCT_CODE_POS: tuple[int, int] = (63, 275)   # TdxEdit 70x25

# 필드 매칭 허용 반경(px). 위 docstring 2번 참조.
FIELD_MATCH_RADIUS = 12

# 주문상태 라디오 '정상'(기본 선택 상태). RadioButtonControl 이라 UIA 로도 찾을 수 있다.
STATUS_NORMAL_POS: tuple[int, int] = (104, 770)   # TGroupButton 68x21

# ⚠️ 하단 저장/취소 버튼은 Delphi TSpeedButton(창 핸들 없음)이라 **UIA 에 아예 안 보인다**
# (라벨이 하나도 안 잡히는 것과 같은 이유). 컨트롤로 찾을 수 없으므로 좌표 클릭해야 한다.
# 값은 버튼 **중심**(다른 상수와 달리 좌상단이 아니다).
SAVE_BUTTON_POS: tuple[int, int] = (514, 820)     # '▶ 저장'  (x 480~548, y 809~831)
CANCEL_BUTTON_POS: tuple[int, int] = (757, 820)   # '▶ 취소'  (x 723~791, y 809~831)
