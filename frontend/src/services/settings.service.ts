/**
 * Settings management service
 * Handles application settings and device control
 */

import { get, post, downloadFile, uploadFile } from './api.client';
import type {
  GlobalSettings,
  // GenICamSettings, // TODO: Will be used when implementing GenICam settings retrieval
  AprilTagFieldsResponse,
  SuccessResponse,
} from '@/types';

/**
 * Update global settings (team number, hostname, IP mode)
 */
export async function updateGlobalSettings(settings: GlobalSettings): Promise<SuccessResponse> {
  return post<SuccessResponse>('/settings/global/update', settings);
}

/**
 * Update GenICam CTI file path
 */
export async function updateGenICamSettings(ctiPath: string): Promise<SuccessResponse> {
  return post<SuccessResponse>('/settings/genicam/update', { cti_path: ctiPath });
}

/**
 * Clear GenICam CTI file path
 */
export async function clearGenICamSettings(): Promise<SuccessResponse> {
  return post<SuccessResponse>('/settings/genicam/clear');
}

// ==================== AprilTag Field Layouts ====================

/**
 * Get AprilTag field layouts
 */
export async function getAprilTagFields(): Promise<AprilTagFieldsResponse> {
  return get<AprilTagFieldsResponse>('/settings/apriltag/fields');
}

/**
 * Select AprilTag field layout
 */
export async function selectAprilTagField(fieldName: string): Promise<SuccessResponse> {
  return post<SuccessResponse>('/settings/apriltag/select', { field_name: fieldName });
}

/**
 * Upload custom AprilTag field layout
 */
export async function uploadAprilTagField(
  file: File,
  onProgress?: (progress: number) => void
): Promise<SuccessResponse> {
  const formData = new FormData();
  formData.append('file', file);

  return uploadFile<SuccessResponse>('/settings/apriltag/upload', formData, (progressEvent) => {
    if (onProgress && progressEvent.total) {
      const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
      onProgress(percentCompleted);
    }
  });
}

/**
 * Delete custom AprilTag field layout
 */
export async function deleteAprilTagField(fieldName: string): Promise<SuccessResponse> {
  return post<SuccessResponse>('/settings/apriltag/delete', { field_name: fieldName });
}

// ==================== Device Control ====================

/**
 * Restart the application
 */
export async function restartApplication(): Promise<SuccessResponse> {
  return post<SuccessResponse>('/settings/control/restart-app');
}

/**
 * Reboot the device
 */
export async function rebootDevice(): Promise<SuccessResponse> {
  return post<SuccessResponse>('/settings/control/reboot');
}

/**
 * Export database
 */
export async function exportDatabase(): Promise<void> {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
  await downloadFile('/settings/control/export-db', `arcsight-backup-${timestamp}.db`);
}

/**
 * Import database
 */
export async function importDatabase(
  file: File,
  onProgress?: (progress: number) => void
): Promise<SuccessResponse> {
  const formData = new FormData();
  formData.append('file', file);

  return uploadFile<SuccessResponse>('/settings/control/import-db', formData, (progressEvent) => {
    if (onProgress && progressEvent.total) {
      const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
      onProgress(percentCompleted);
    }
  });
}

/**
 * Factory reset (clear all settings and data)
 */
export async function factoryReset(): Promise<SuccessResponse> {
  return post<SuccessResponse>('/settings/control/factory-reset');
}
