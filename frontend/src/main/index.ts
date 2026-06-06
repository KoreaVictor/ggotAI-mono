import { app, BrowserWindow, ipcMain, safeStorage } from 'electron';
import * as path from 'path';
import * as fs from 'fs';
import { exec } from 'child_process';

let mainWindow: BrowserWindow | null = null;
let isAppQuitting = false;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 768,
    title: 'ggotAIya - 주문 수집 상황판',
    icon: path.join(__dirname, '../../public/icon.ico'), // 프로덕션 빌드 후 경로 감안
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    // 다크 모드 윈도우 프레임 테두리 디자인 적용
    backgroundColor: '#0B0F17',
    show: false,
  });

  // 개발 모드와 프로덕션 모드 로드 타깃 정의
  const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../index.html'));
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow?.show();
  });

  // 닫기 버튼 클릭 시 앱을 종료하는 대신 숨김 처리 (윈도우 백그라운드 트레이 연동용)
  mainWindow.on('close', (event) => {
    // 윈도우 OS 트레이에서 더블 클릭 시 빠르게 창을 띄울 수 있게 Hide 시킴
    // 완전 종료는 app.quit()으로만 수행
    if (!isAppQuitting) {
      event.preventDefault();
      mainWindow?.hide();
    }
    return false;
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// 윈도우 단일 인스턴스 보장 (중복 실행 방지)
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    // 두 번째 인스턴스가 켜지려 하면 기존에 숨겨져 있던 창을 활성화하여 전면에 노출
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      if (!mainWindow.isVisible()) mainWindow.show();
      mainWindow.focus();
    }
  });

  app.whenReady().then(() => {
    createWindow();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });
}

app.on('before-quit', () => {
  isAppQuitting = true;
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// ==========================================
// IPC 통신 채널 등록 (Windows Service 제어)
// ==========================================

// 1. 서비스 시작
ipcMain.handle('service:start', async () => {
  return new Promise((resolve) => {
    exec('net start ggotAIorder', (error, stdout, stderr) => {
      if (error) {
        console.error('서비스 시작 실패:', error);
        resolve({ success: false, error: stderr || error.message });
      } else {
        console.log('서비스 시작 성공:', stdout);
        resolve({ success: true });
      }
    });
  });
});

// 2. 서비스 중지
ipcMain.handle('service:stop', async () => {
  return new Promise((resolve) => {
    exec('net stop ggotAIorder', (error, stdout, stderr) => {
      if (error) {
        console.error('서비스 중지 실패:', error);
        resolve({ success: false, error: stderr || error.message });
      } else {
        console.log('서비스 중지 성공:', stdout);
        resolve({ success: true });
      }
    });
  });
});

// 3. 서비스 상태 조회
ipcMain.handle('service:status', async () => {
  return new Promise((resolve) => {
    // SCM을 조회하여 ggotAIorder 상태 파악
    exec('sc query ggotAIorder', (error, stdout, stderr) => {
      if (error) {
        // 에러 코드 1060은 서비스가 설치되지 않았음을 의미
        if (stdout.includes('1060') || stderr.includes('1060')) {
          resolve({ status: 'NOT_INSTALLED' });
        } else {
          resolve({ status: 'STOPPED', error: stderr || error.message });
        }
        return;
      }

      const output = stdout.toUpperCase();
      if (output.includes('RUNNING')) {
        resolve({ status: 'RUNNING' });
      } else if (output.includes('STOPPED') || output.includes('STOP_PENDING') || output.includes('PAUSED')) {
        resolve({ status: 'STOPPED' });
      } else {
        resolve({ status: 'STOPPED' });
      }
    });
  });
});

// ==========================================
// IPC 통신 채널 등록 (remember_token 보안 저장)
// ==========================================

function tokenFilePath(): string {
  return path.join(app.getPath('userData'), 'remember.bin');
}

// 자동로그인 토큰 저장 (OS 암호화)
ipcMain.handle('auth:save', async (_e, payload: { userId: number; token: string }) => {
  try {
    if (!safeStorage.isEncryptionAvailable()) return { success: false, error: 'NO_ENCRYPTION' };
    const enc = safeStorage.encryptString(JSON.stringify(payload));
    fs.writeFileSync(tokenFilePath(), enc);
    return { success: true };
  } catch (err) {
    return { success: false, error: (err as Error).message };
  }
});

// 자동로그인 토큰 로드
ipcMain.handle('auth:load', async () => {
  try {
    const p = tokenFilePath();
    if (!fs.existsSync(p) || !safeStorage.isEncryptionAvailable()) return null;
    const dec = safeStorage.decryptString(fs.readFileSync(p));
    return JSON.parse(dec) as { userId: number; token: string };
  } catch {
    return null;
  }
});

// 자동로그인 토큰 삭제
ipcMain.handle('auth:clear', async () => {
  try {
    const p = tokenFilePath();
    if (fs.existsSync(p)) fs.unlinkSync(p);
    return { success: true };
  } catch (err) {
    return { success: false, error: (err as Error).message };
  }
});
