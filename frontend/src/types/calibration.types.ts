/**
 * Calibration-related types
 */

export type PatternType = 'chessboard' | 'charuco';

export interface CalibrationPatternConfig {
  pattern_type: PatternType;
  rows: number;
  cols: number;
  square_size_mm: number;
  marker_size_mm?: number; // For ChArUco only
  dictionary?: string; // For ChArUco only
}

export interface CalibrationSessionInfo {
  camera_id: number;
  camera_name: string;
  pattern_config: CalibrationPatternConfig;
  capture_count: number;
  min_captures: number;
}

export interface CalibrationResults {
  camera_matrix: number[][];
  dist_coeffs: number[];
  reprojection_error: number;
  capture_count: number;
}

export interface CaptureResponse {
  total_frames_captured: number;
  pattern_detected: boolean;
  success: boolean;
  message?: string;
}
