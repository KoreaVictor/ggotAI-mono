# ggotAIya (프론트엔드) - ggotAIorder (백엔드) 연동 규격서

본 문서는 웹 기반 데스크톱 애플리케이션인 `ggotAIya` (React + Electron)와 백그라운드 서비스 엔진인 `ggotAIorder` (Windows Service) 간의 제어 및 통신 인터페이스를 정의합니다.

---

## 1. 개요 및 아키텍처
프론트엔드와 백엔드는 동일한 로컬 윈도우 환경 상에서 실행되지만 서로 독립된 영역으로 동작합니다. 
두 애플리케이션의 결합도를 낮추고 동시 개발을 원활하게 하기 위해 다음 2가지 매커니즘을 사용합니다.

1. **상태 및 데이터 동기화**: **Supabase DB**를 매개로 동작합니다. 프론트엔드가 설정을 업데이트하면, 백엔드가 실시간(Realtime) 또는 주기적으로 변경 사항을 캐치하여 시스템에 반영합니다.
2. **프로세스 수명 주기 제어**: OS의 **Windows Service Control Manager (SCM)**를 통해 프론트엔드가 백엔드 백그라운드 프로세스를 직접 기동하거나 종료합니다.

---

## 2. Electron 내부 IPC (메인 ↔ 렌더러) 명세

React 렌더러(웹)는 보안상 로컬 쉘 명령을 내릴 수 없으므로, Electron의 메인 프로세스에 위임하여 처리합니다.

### 2-1. IPC 채널 목록

| 채널명 | 송신측 (Sender) | 수신측 (Receiver) | 설명 | 전달 파라미터 | 반환값 (Promise) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `service:start` | Renderer (React) | Main (Node.js) | 백엔드 윈도우 서비스 기동 요청 | 없음 | `{ success: boolean, error?: string }` |
| `service:stop` | Renderer (React) | Main (Node.js) | 백엔드 윈도우 서비스 중지 요청 | 없음 | `{ success: boolean, error?: string }` |
| `service:status` | Renderer (React) | Main (Node.js) | 백엔드 윈도우 서비스 상태 조회 | 없음 | `{ status: 'RUNNING' \| 'STOPPED' \| 'NOT_INSTALLED', error?: string }` |

### 2-2. Preload 브릿지 코드 구성 (`preload.ts`)
```typescript
import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  startService: () => ipcRenderer.invoke('service:start'),
  stopService: () => ipcRenderer.invoke('service:stop'),
  getServiceStatus: () => ipcRenderer.invoke('service:status'),
});
```

---

## 3. OS 명령어 기반 백엔드 제어 (Main 프로세스 동작)

Electron 메인 프로세스는 시스템 관리자 권한으로 실행되며, 다음 윈도우 OS 표준 쉘 명령어를 실행하여 서비스를 통제합니다.

### 3-1. 서비스 기동 (`service:start`)
```bash
net start ggotAIorder
# 또는 서비스 관리 명령
sc start ggotAIorder
```

### 3-2. 서비스 중지 (`service:stop`)
```bash
net stop ggotAIorder
# 또는 서비스 관리 명령
sc stop ggotAIorder
```

### 3-3. 서비스 상태 체크 (`service:status`)
```bash
sc query ggotAIorder
```
* **결과 파싱**:
  * Output에 `STATE : 4 RUNNING` 포함 시 ➔ `RUNNING` 반환
  * Output에 `STATE : 1 STOPPED` 포함 시 ➔ `STOPPED` 반환
  * 해당 서비스가 존재하지 않는다는 에러(1060) 발생 시 ➔ `NOT_INSTALLED` 반환

---

## 4. Supabase DB 연동을 통한 비동기 제어

프론트엔드와 백엔드가 직접 포트(Port) 통신을 하지 않는 대신, Supabase DB를 통해 데이터를 공유합니다.

### 4-1. 설정 정보 공유 (`setting_info`)
* **프론트엔드 (ggotAIya)**: 사장님이 UI 설정 화면에서 수집 주기 및 연동 정보를 수정하면 `setting_info` 테이블의 행을 UPDATE합니다. 이때 비밀번호는 암호화(AES-256)하여 저장합니다.
* **백엔드 (ggotAIorder)**: 주기적으로 `setting_info`를 로컬 메모리에 캐싱하거나 Supabase Realtime 구독을 통해 설정값이 바뀌는 순간을 감지(INSERT/UPDATE)하여 쇼핑몰/인트라넷 스크래핑 주기를 재설정합니다.

### 4-2. 암호화 프로토콜 (AES-256-CBC)
웹 단의 JavaScript 암호화 라이브러리와 파이썬 암호화 라이브러리 간 호환성을 보장하기 위해 아래 스펙을 사용합니다.

* **알고리즘**: `AES-256-CBC`
* **패딩(Padding)**: `PKCS7`
* **키(Key)**: 64자 16진수(hex) 문자열을 디코딩한 32바이트 (환경변수의 AES 키를 공유)
* **초기화 벡터(IV)**: 16바이트 랜덤 값 (암호화 결과물 맨 앞에 붙여서 Base64 인코딩하여 DB에 저장)

> 프론트엔드(crypto-js)와 백엔드(Python) 모두 키를 hex로 디코딩하여 사용해야 호환됩니다.

#### JavaScript 암호화 예시 (`crypto-js`)
```javascript
import CryptoJS from 'crypto-js';

const key = CryptoJS.enc.Hex.parse(process.env.VITE_AES_ENCRYPTION_KEY);
const iv = CryptoJS.lib.WordArray.random(16);

const encrypted = CryptoJS.AES.encrypt("plain_password", key, {
  iv: iv,
  mode: CryptoJS.mode.CBC,
  padding: CryptoJS.pad.Pkcs7
});

// DB 저장용 데이터 포맷: IV (Hex) + ":" + Encrypted Text (Base64)
const dbValue = iv.toString(CryptoJS.enc.Hex) + ":" + encrypted.toString();
```

#### Python 복호화 예시 (`cryptography`)
```python
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

db_value = "iv_hex:encrypted_base64"  # DB에서 조회한 값
iv_hex, encrypted_base64 = db_value.split(":")

key = bytes.fromhex(os.getenv("AES_ENCRYPTION_KEY"))
iv = bytes.fromhex(iv_hex)
encrypted_data = base64.b64decode(encrypted_base64)

cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
decryptor = cipher.decryptor()
padded_plain = decryptor.update(encrypted_data) + decryptor.finalize()

# PKCS7 언패딩
unpacker = padding.PKCS7(128).unpadder()
plain_password = (unpacker.update(padded_plain) + unpacker.finalize()).decode('utf-8')
```
