/**
 * Camera-related types and interfaces
 */

export type CameraType = 'USB' | 'GenICam' | 'OAK-D' | 'RealSense';
export type Orientation = 0 | 90 | 180 | 270;
export type ExposureMode = 'auto' | 'manual';
export type GainMode = 'auto' | 'manual';

export interface CameraResolution {
  width: number;
  height: number;
}

export interface CameraDeviceInfo {
  vid?: string;
  pid?: string;
  serial?: string;
  manufacturer?: string;
  product?: string;
}

export interface Camera {
  id: number;
  name: string;
  camera_type: CameraType;
  identifier: string;
  orientation: Orientation;
  exposure_value: number;
  gain_value: number;
  exposure_mode: ExposureMode;
  gain_mode: GainMode;
  camera_matrix_json: string | null;
  dist_coeffs_json: string | null;
  reprojection_error: number | null;
  device_info_json: string | null;
  resolution_json: string | null;
  framerate: number | null;
  depth_enabled: boolean;
}

export interface CameraStatus {
  id: number;
  connected: boolean;
  is_active: boolean;
  error?: string;
  fps?: number;
  resolution?: CameraResolution;
}

export interface CameraControls {
  orientation: Orientation;
  exposure_mode: ExposureMode;
  exposure_value: number;
  gain_mode: GainMode;
  gain_value: number;
}

export interface DiscoveredCamera {
  type: CameraType;
  identifier: string;
  name: string;
  device_info?: CameraDeviceInfo;
}

export interface GenICamNode {
  name: string;
  type: 'Integer' | 'Float' | 'Boolean' | 'String' | 'Enumeration' | 'Command';
  value: string | number | boolean;
  min?: number;
  max?: number;
  writable: boolean;
  description?: string;
  enum_entries?: string[];
}

export interface RealSenseResolution {
  width: number;
  height: number;
  fps: number[];
}

export interface RealSenseConfig {
  resolution: CameraResolution;
  framerate: number;
  depth_enabled: boolean;
}

export interface RealSenseResolutionsResponse {
  current_resolution: CameraResolution;
  current_framerate: number;
  available_resolutions: RealSenseResolution[];
}
