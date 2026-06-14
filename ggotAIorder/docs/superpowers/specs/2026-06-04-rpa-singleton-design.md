# RPA 싱글턴 엔진 실구현 설계서

작성일: 2026-06-04
범위: `rpa/singleton_macro.py` 스텁을 싱글턴 순차 오케스트레이션 실구현으로 — 주문 조회 → 관리 프로그램 구동 감지 → (추상화된) GUI 입력 또는 백업 생성 → `rpa_status` 마킹 → 주문별 알림. 실제 GUI 창 탐색·키 시퀀스는 연기(라이브).
기준 브랜치: master (PR #6 머지 예정), 작업 브랜치 `feature/rpa-singleton`.

---

## 1. 목표와 범위

PRD 6-5/8-4(싱글턴 순차 RPA 입력)의 **오케스트레이션**을 구현한다. 실제 관리 프로그램 GUI 입력은 `ProgramAutomator`(Protocol) 뒤로 추상화한다.

- **포함(실로직, 오프라인 테스트)**: 싱글턴 락 순차 처리, 주문 조회(order_details + server_call_history 채널 조인), 프로그램 구동 감지 분기, 백업(.xlsx + .txt 영수증) 실생성, `rpa_status='success'/'fail'` 마킹, 주문별 알림(count=1), 방어적 에러 처리.
- **연기(라이브/체크리스트)**: 실제 관리 프로그램 창 탐색·클립보드/키 시퀀스 입력 매크로(대상 프로그램 UI 필요).
- **비범위**: 집계 배치 알림, 알림 이력 테이블, 전용 알림 문구.

## 2. 아키텍처

`enqueue(order_detail_id)`는 모듈 수준 `asyncio.Lock()` 하에 **순차 오케스트레이션**만 담당한다. 이미 `pipeline.engine`·`scraper.crawler` 두 곳에서 `await enqueue(order_id)`로 호출되므로 **시그니처 하위호환**(모든 신규 인자 기본값)을 유지한다.

GUI 입력은 `ProgramAutomator` Protocol, DB는 `RpaRepository` Protocol로 추상화 → 오프라인 테스트는 fake 주입. 백업은 결정적이라 실구현(`tmp_path` 테스트).

## 3. 파일 구조

```
backend/src/ggotaiorder/rpa/
├─ models.py          # RpaOrder (order_details 행 + channel)
├─ repository.py      # RpaRepository(Protocol) + SupabaseRpaRepository
├─ automator.py       # ProgramAutomator(Protocol) + WindowsProgramAutomator(골격)
├─ backup.py          # BackupWriter (openpyxl .xlsx + .txt 영수증) — 실구현
└─ singleton_macro.py # enqueue 오케스트레이션 + _rpa_lock (기존 파일 교체)
```

### 3.1 models.py
```python
@dataclass
class RpaOrder:
    order_detail_id: int
    shop_key: int
    shop_name: str
    channel: str                # server_call_history.channel_order (전화/쇼핑몰/인터라넷)
    customer_name: str
    customer_phone_number: str
    product_name: str
    quantity: int
    price: int
    delivery_at: str | None
    delivery_place: str | None
    receiver_name: str | None
    receiver_phone_number: str | None
    ribbon_sender: str | None
    ribbon_congratulations: str | None
    card_message: str | None
```

### 3.2 repository.py
```python
class RpaRepository(Protocol):
    def get_order(self, order_detail_id: int) -> RpaOrder | None: ...
    def set_rpa_status(self, order_detail_id: int, status: str) -> None: ...
```
`SupabaseRpaRepository`:
- `get_order`: order_details에서 id=order_detail_id 행 조회 → call_history_id로 server_call_history.channel_order 조회(없으면 채널 빈문자) → RpaOrder 매핑. 없으면 None.
- `set_rpa_status`: order_details.update({rpa_status: status}).eq(id, order_detail_id).

### 3.3 automator.py
```python
class ProgramAutomator(Protocol):
    def is_program_running(self) -> bool: ...
    def input_order(self, order: RpaOrder) -> None: ...

class WindowsProgramAutomator:
    def is_program_running(self) -> bool:
        # TODO(라이브): pygetwindow로 관리 프로그램 창 탐색. 라이브 전엔 안전하게 False(→백업).
        return False
    def input_order(self, order: RpaOrder) -> None:
        # TODO(라이브): pyperclip 클립보드 + Tab 키 시퀀스 입력. 실 프로그램 UI 확보 후.
        raise NotImplementedError("관리 프로그램 GUI 입력은 대상 프로그램 확보 후 구현")
```
실제 구현은 라이브 영역(단위테스트 안 함).

### 3.4 backup.py
```python
class BackupWriter:
    def __init__(self, backup_dir: Path): ...
    def write(self, order: RpaOrder) -> tuple[Path, Path]:
        # .xlsx: openpyxl 워크북 "주문" 시트에 헤더행 + 값행(11필드 + id/shop)
        # .txt : 사람이 읽는 영수증(상품/수량/가격/배송일시/배송지/받는분/리본/카드메시지)
        # 파일명: {shop_key}_{order_detail_id}_{YYYYMMDD-HHMMSS}.{xlsx,txt}
        # backup_dir 미존재 시 생성. (xlsx_path, txt_path) 반환.
```

## 4. singleton_macro.py — enqueue 오케스트레이션

```python
_rpa_lock = asyncio.Lock()   # 다중 채널 충돌 방지 싱글턴 (PRD 8-4)

async def enqueue(order_detail_id, *, repo=None, automator=None, backup=None, notify=None):
    repo = repo or SupabaseRpaRepository()
    automator = automator or WindowsProgramAutomator()
    backup = backup or BackupWriter(load_config().rpa_backup_dir)
    notify = notify or _default_notify
    try:
        async with _rpa_lock:
            order = await to_thread(repo.get_order, order_detail_id)
            if order is None:
                logger.warning("RPA 대상 주문 없음 id=%s", order_detail_id); return
            success = False
            if await to_thread(automator.is_program_running):
                try:
                    await to_thread(automator.input_order, order)
                    success = True
                except Exception:
                    logger.exception("관리 프로그램 입력 실패 id=%s", order_detail_id)
                    await to_thread(backup.write, order)
            else:
                logger.info("관리 프로그램 미구동 — 백업 생성 id=%s", order_detail_id)
                await to_thread(backup.write, order)
            status = "success" if success else "fail"
            await to_thread(repo.set_rpa_status, order_detail_id, status)
            await notify(order, success)
    except Exception:
        logger.exception("RPA enqueue 처리 실패 id=%s", order_detail_id)  # 호출자 보호
```

- `_default_notify(order, success)`: `await notifier.send(order.shop_key, channel=order.channel, count=1, success=success)` 래퍼. 주입 가능(테스트 spy).
- 비동기: 블로킹(repo·automator·backup)은 `asyncio.to_thread` 오프로드. 락 하에 순차.

## 5. config 확장

`Config`에 선택 필드 `rpa_backup_dir: Path` 추가. `load_config`에서 `RPA_BACKUP_DIR` 환경변수 읽되 **선택**(누락 시 기본 `backend/backups`). `_REQUIRED_KEYS` 불변 → 기존 config 테스트 회귀 없음.

```python
backup_dir = env.get("RPA_BACKUP_DIR")
rpa_backup_dir = Path(backup_dir) if backup_dir else Path(__file__).resolve().parents[2] / "backups"
```

## 6. 에러 처리

- `enqueue` 전체 try/except로 방어 — get_order/set_rpa_status/notify 예외도 로깅 후 흡수해 **호출자(engine·crawler)를 막지 않음**.
- 프로그램 미구동·입력 실패 → 백업 생성 + `rpa_status='fail'` + 실패 경고 알림. 입력 성공 → `'success'` + 성공 알림(백업 없음).
- 락은 `async with`로 항상 해제.

## 7. 테스트 (오프라인 결정적)

`test_rpa_backup.py` — BackupWriter:
- `tmp_path`로 write → xlsx 존재·openpyxl 재독으로 product_name 등 값 확인, txt 존재·상품명/받는분 포함. backup_dir 자동 생성 확인.

`test_rpa_singleton.py` — enqueue (fake repo/automator/backup + spy notify):
- 구동 중 + 입력 성공 → set_rpa_status('success'), notify(success=True), backup.write 미호출.
- 구동 중 + 입력 예외 → backup.write 호출, status 'fail', notify(success=False).
- 미구동 → backup.write 호출, status 'fail', notify(success=False).
- order None → set_rpa_status·notify·backup 미호출.
- 싱글턴 락: 동시 2건 `asyncio.gather` → 직렬 처리(겹침 없음) 확인.
- 기존 67 회귀. 비동기 테스트는 `asyncio_mode="auto"`.

`SupabaseRpaRepository`·`WindowsProgramAutomator`는 통합/라이브 영역(import 확인만, 단위테스트 안 함).

## 8. 라이브 구동 체크리스트

1. 대상 꽃집 관리 프로그램 창 제목·입력 폼 필드 순서(Tab 이동 순서) 확보.
2. `WindowsProgramAutomator.is_program_running` 창 탐색(pygetwindow) 구현.
3. `WindowsProgramAutomator.input_order` 클립보드(pyperclip)+키 시퀀스 입력 구현.
4. `.env`에 `RPA_BACKUP_DIR`(선택) 설정 또는 기본 `backend/backups` 사용.
5. enqueue 실행 → 구동 시 자동 입력·`success` 마킹·성공 알림 / 미구동 시 백업·`fail`·경고 알림 확인.

## 9. 비범위(후속)

- 실 GUI 창 탐색·키 시퀀스, 집계 배치 알림, 알림 이력 테이블, 재시도/대기열 영속화.
