/**
 * Metrics and monitoring types
 */

export interface PipelineMetrics {
  pipeline_id: number;
  pipeline_name: string;
  pipeline_type: string;
  camera_name: string;
  fps: number;
  latency_avg_ms: number;
  latency_p95_ms: number;
  latency_max_ms: number;
  queue_depth: number;
  queue_max_size: number;
  queue_utilization_pct: number;
  drops_total: number;
  drops_per_sec: number;
  frames_dropped: number;
  status: 'Nominal' | 'Slow frames' | 'Queue saturated' | 'Drops observed';
}

export interface SystemMetrics {
  cpu_percent: number;
  ram_percent: number;
  ram_used_mb: number;
  ram_total_mb: number;
  temperature_celsius: number | null;
  temperature_c: number | null; // Alias for temperature_celsius
  platform: string;
}

export interface PerformanceThresholds {
  queue_high_utilization_pct: number;
  latency_warn_ms: number;
  window_seconds: number;
  fps_window_seconds: number;
}

export interface PipelineActivitySummary {
  active_pipeline_count: number;
  total_drops_per_sec: number;
  process_rss_mb: number;
  latency_alerts: number;
}

export interface CameraMetrics {
  camera_id: number;
  camera_name: string;
  camera_type: string;
  is_active: boolean;
  fps?: number;
}

export interface MetricsSummary {
  pipelines: PipelineMetrics[];
  cameras: CameraMetrics[];
  activity: PipelineActivitySummary;
  thresholds: PerformanceThresholds;
  generated_at: string;
}
