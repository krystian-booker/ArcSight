/**
 * Calibration service
 * Handles camera calibration workflow
 */

import { post, downloadFile } from './api.client';
import type {
  // CalibrationSessionInfo, // TODO: Will be used when implementing calibration session info endpoint
  CalibrationResults,
  CaptureResponse,
  SuccessResponse,
  PatternType,
} from '@/types';

/**
 * Generate chessboard calibration pattern PDF
 */
export async function generateChessboardPattern(params: {
  rows: number;
  cols: number;
  square_size_mm: number;
}): Promise<void> {
  const queryString = new URLSearchParams({
    rows: params.rows.toString(),
    cols: params.cols.toString(),
    square_size: params.square_size_mm.toString(),
  }).toString();

  await downloadFile(
    `/calibration/generate_pattern?${queryString}`,
    `chessboard_${params.rows}x${params.cols}.pdf`
  );
}

/**
 * Generate ChArUco calibration pattern PDF
 */
export async function generateCharucoPattern(params: {
  rows: number;
  cols: number;
  square_size_mm: number;
  marker_size_mm: number;
  dictionary: string;
}): Promise<void> {
  const queryString = new URLSearchParams({
    rows: params.rows.toString(),
    cols: params.cols.toString(),
    square_size: params.square_size_mm.toString(),
    marker_size: params.marker_size_mm.toString(),
    dictionary: params.dictionary,
  }).toString();

  await downloadFile(
    `/calibration/generate_charuco_pattern?${queryString}`,
    `charuco_${params.rows}x${params.cols}.pdf`
  );
}

/**
 * Start calibration session
 */
export async function startCalibration(params: {
  camera_id: number;
  pattern_type: PatternType;
  rows: number;
  cols: number;
  square_size_mm: number;
  marker_size_mm?: number;
  dictionary?: string;
}): Promise<SuccessResponse> {
  return post<SuccessResponse>('/calibration/start', params);
}

/**
 * Capture a calibration frame
 */
export async function captureCalibrationFrame(cameraId: number): Promise<CaptureResponse> {
  return post<CaptureResponse>('/calibration/capture', { camera_id: cameraId });
}

/**
 * Calculate calibration from captured frames
 */
export async function calculateCalibration(cameraId: number): Promise<CalibrationResults> {
  return post<CalibrationResults>('/calibration/calculate', { camera_id: cameraId });
}

/**
 * Save calibration to camera
 */
export async function saveCalibration(cameraId: number): Promise<SuccessResponse> {
  return post<SuccessResponse>('/calibration/save', { camera_id: cameraId });
}
