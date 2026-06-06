export {};

export type ServiceStatus = 'RUNNING' | 'STOPPED' | 'NOT_INSTALLED';

declare global {
  interface Window {
    electronAPI?: {
      startService(): Promise<{ success: boolean; error?: string }>;
      stopService(): Promise<{ success: boolean; error?: string }>;
      getServiceStatus(): Promise<{ status: ServiceStatus; error?: string }>;
    };
  }
}
