import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  startService: () => ipcRenderer.invoke('service:start'),
  stopService: () => ipcRenderer.invoke('service:stop'),
  getServiceStatus: () => ipcRenderer.invoke('service:status'),
  saveRememberToken: (userId: number, token: string) =>
    ipcRenderer.invoke('auth:save', { userId, token }),
  loadRememberToken: () => ipcRenderer.invoke('auth:load'),
  clearRememberToken: () => ipcRenderer.invoke('auth:clear'),
});
