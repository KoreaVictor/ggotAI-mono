/// <reference types="vite/client" />

interface ElectronAPI {
  startService: () => Promise<{ success: boolean; error?: string }>;
  stopService: () => Promise<{ success: boolean; error?: string }>;
  getServiceStatus: () => Promise<{ status: 'RUNNING' | 'STOPPED' | 'NOT_INSTALLED'; error?: string }>;
}

interface Window {
  electronAPI: ElectronAPI;
}
