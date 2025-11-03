/**
 * Pipeline-related types and interfaces
 */

export type PipelineType = 'apriltag' | 'coloured_shape' | 'object_detection_ml';

export interface Pipeline {
  id: number;
  name: string;
  pipeline_type: PipelineType;
  config: string; // JSON string
  camera_id: number;
  is_active: boolean;
}

// ==================== AprilTag Configuration ====================
export type AprilTagFamily = 'tag36h11' | 'tag25h9' | 'tag16h5' | 'tagCircle21h7' | 'tagCircle49h12' | 'tagStandard41h12' | 'tagStandard52h13' | 'tagCustom48h12';

export interface AprilTagConfig {
  tag_family: AprilTagFamily;
  tag_size_mm: number;
  decimation: number;
  threads: number;
  refine_edges: boolean;
  max_hamming_distance: number;
  decision_margin_cutoff: number;
  enable_multi_tag_localization: boolean;
  selected_tag_ids?: number[];
}

// ==================== Coloured Shape Configuration ====================
export interface HSVRange {
  h_min: number;
  h_max: number;
  s_min: number;
  s_max: number;
  v_min: number;
  v_max: number;
}

export interface ColouredShapeConfig {
  hsv_ranges: HSVRange[];
  min_area: number;
  max_area: number;
  min_aspect_ratio: number;
  max_aspect_ratio: number;
  shape_filter?: 'circle' | 'rectangle' | 'any';
}

// ==================== ML Object Detection Configuration ====================
export interface ObjectDetectionMLConfig {
  model_path: string;
  labels_path: string;
  confidence_threshold: number;
  nms_threshold: number;
  selected_classes?: number[];
  input_size: number;
}

// ==================== Pipeline Results ====================
export interface AprilTagDetection {
  tag_id: number;
  family: string;
  hamming: number;
  decision_margin: number;
  center: [number, number];
  corners: [[number, number], [number, number], [number, number], [number, number]];
  pose?: {
    rotation: number[][];
    translation: number[];
    distance_mm?: number;
  };
}

export interface MultiTagTransform {
  rotation: number[][];
  translation: number[];
  tag_ids: number[];
  error: number;
}

export interface AprilTagResult {
  detections: AprilTagDetection[];
  multi_tag_transform?: MultiTagTransform;
  processing_time_ms: number;
}

export interface ColouredShapeDetection {
  center: [number, number];
  area: number;
  contour: number[][];
  bounding_box: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  aspect_ratio: number;
  shape?: string;
}

export interface ColouredShapeResult {
  detections: ColouredShapeDetection[];
  processing_time_ms: number;
}

export interface ObjectDetection {
  class_id: number;
  class_name: string;
  confidence: number;
  bbox: [number, number, number, number]; // [x, y, width, height]
  center: [number, number];
}

export interface ObjectDetectionMLResult {
  detections: ObjectDetection[];
  processing_time_ms: number;
}

export type PipelineResult = AprilTagResult | ColouredShapeResult | ObjectDetectionMLResult;

export interface PipelineResultsResponse {
  [pipelineId: number]: PipelineResult;
}

// ==================== ML Availability ====================
export interface MLAvailability {
  onnx_available: boolean;
  openvino_available: boolean;
  cuda_available: boolean;
  default_provider: string;
}

// ==================== File Upload ====================
export interface PipelineFile {
  filename: string;
  size: number;
  path: string;
}

export interface FileUploadResponse {
  file_info: PipelineFile;
  updated_config: ObjectDetectionMLConfig;
}
