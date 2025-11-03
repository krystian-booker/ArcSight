/**
 * Camera management service
 * Handles all camera-related API calls
 */

import { get, post } from './api.client';
// import { put, del } from './api.client'; // TODO: Will be used for update/delete camera operations
import type {
  Camera,
  CameraStatus,
  CameraControls,
  DiscoveredCamera,
  GenICamNode,
  RealSenseResolutionsResponse,
  RealSenseConfig,
  SuccessResponse,
  PipelineResultsResponse,
} from '@/types';

/**
 * Get list of all cameras
 */
export async function listCameras(): Promise<Camera[]> {
  return get<Camera[]>('/api/cameras');
}

/**
 * Add a new camera
 */
export async function addCamera(data: {
  camera_type: string;
  identifier: string;
  name: string;
}): Promise<SuccessResponse> {
  return post<SuccessResponse>('/cameras/add', data);
}

/**
 * Update camera name
 */
export async function updateCamera(cameraId: number, name: string): Promise<SuccessResponse> {
  return post<SuccessResponse>(`/cameras/update/${cameraId}`, { name });
}

/**
 * Delete a camera
 */
export async function deleteCamera(cameraId: number): Promise<SuccessResponse> {
  return post<SuccessResponse>(`/cameras/delete/${cameraId}`);
}

/**
 * Get camera connection status
 */
export async function getCameraStatus(cameraId: number): Promise<CameraStatus> {
  return get<CameraStatus>(`/cameras/status/${cameraId}`);
}

/**
 * Get all camera statuses
 */
export async function getAllCameraStatus(): Promise<CameraStatus[]> {
  return get<CameraStatus[]>('/cameras/status');
}

/**
 * Start a camera
 */
export async function startCamera(cameraId: number): Promise<SuccessResponse> {
  return post<SuccessResponse>(`/cameras/start/${cameraId}`);
}

/**
 * Stop a camera
 */
export async function stopCamera(cameraId: number): Promise<SuccessResponse> {
  return post<SuccessResponse>(`/cameras/stop/${cameraId}`);
}

/**
 * Get camera controls (exposure, gain, orientation)
 */
export async function getCameraControls(cameraId: number): Promise<Camera> {
  return get<Camera>(`/cameras/controls/${cameraId}`);
}

/**
 * Update camera controls
 */
export async function updateCameraControls(
  cameraId: number,
  controls: Partial<CameraControls>
): Promise<SuccessResponse> {
  return post<SuccessResponse>(`/cameras/update_controls/${cameraId}`, controls);
}

/**
 * Get latest pipeline results for a camera
 */
export async function getCameraResults(cameraId: number): Promise<PipelineResultsResponse> {
  return get<PipelineResultsResponse>(`/cameras/results/${cameraId}`);
}

/**
 * Discover available cameras
 */
export async function discoverCameras(): Promise<{
  [cameraType: string]: DiscoveredCamera[];
}> {
  return get<{ [cameraType: string]: DiscoveredCamera[] }>('/cameras/discover');
}

/**
 * Get list of supported camera types
 */
export async function getCameraTypes(): Promise<string[]> {
  return get<string[]>('/cameras/types');
}

// ==================== GenICam-specific ====================

/**
 * Get GenICam node map for a camera
 */
export async function getGenICamNodes(
  cameraId: number,
  filter?: string
): Promise<{ nodes: GenICamNode[] }> {
  const url = filter
    ? `/cameras/genicam/nodes/${cameraId}?filter=${encodeURIComponent(filter)}`
    : `/cameras/genicam/nodes/${cameraId}`;
  return get<{ nodes: GenICamNode[] }>(url);
}

/**
 * Update a GenICam node value
 */
export async function updateGenICamNode(
  cameraId: number,
  nodeName: string,
  value: string | number | boolean
): Promise<GenICamNode> {
  return post<GenICamNode>(`/cameras/genicam/nodes/${cameraId}`, {
    node_name: nodeName,
    value,
  });
}

// ==================== RealSense-specific ====================

/**
 * Get available resolutions for RealSense camera
 */
export async function getRealSenseResolutions(
  cameraId: number
): Promise<RealSenseResolutionsResponse> {
  return get<RealSenseResolutionsResponse>(`/cameras/realsense/resolutions/${cameraId}`);
}

/**
 * Update RealSense camera configuration
 */
export async function updateRealSenseConfig(
  cameraId: number,
  config: RealSenseConfig
): Promise<SuccessResponse> {
  return post<SuccessResponse>(`/cameras/realsense/config/${cameraId}`, config);
}
