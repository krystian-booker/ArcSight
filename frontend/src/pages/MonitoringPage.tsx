/**
 * MonitoringPage - System metrics and performance monitoring
 */

import { useQuery } from '@tanstack/react-query';
import { metricsService } from '@/services';
import { Panel, Badge, Spinner } from '@/components/common';

export default function MonitoringPage() {
  // Fetch metrics summary
  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['metrics', 'summary'],
    queryFn: metricsService.getMetricsSummary,
    refetchInterval: 2000, // Update every 2 seconds
  });

  // Fetch system metrics
  const { data: system, isLoading: systemLoading } = useQuery({
    queryKey: ['metrics', 'system'],
    queryFn: metricsService.getSystemMetrics,
    refetchInterval: 2000, // Update every 2 seconds
  });

  const isLoading = summaryLoading || systemLoading;

  return (
    <div className="p-lg max-w-arc mx-auto space-y-lg">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-arc-text">System Monitoring</h1>
          <p className="text-sm text-arc-muted mt-2xs">
            Real-time performance metrics and system health
          </p>
        </div>
        {isLoading && <Spinner />}
      </div>

      {/* System Metrics */}
      <Panel title="System Resources">
        {systemLoading ? (
          <div className="flex items-center justify-center py-xl">
            <Spinner size="lg" />
          </div>
        ) : system ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-lg">
            {/* CPU Usage */}
            <div>
              <div className="flex items-center justify-between mb-xs">
                <span className="text-sm text-arc-muted">CPU Usage</span>
                <Badge variant={system.cpu_percent > 80 ? 'danger' : system.cpu_percent > 60 ? 'warning' : 'success'}>
                  {system.cpu_percent.toFixed(1)}%
                </Badge>
              </div>
              <div className="w-full bg-arc-surface h-2 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-arc ${
                    system.cpu_percent > 80
                      ? 'bg-arc-danger'
                      : system.cpu_percent > 60
                      ? 'bg-arc-warning'
                      : 'bg-arc-success'
                  }`}
                  style={{ width: `${system.cpu_percent}%` }}
                />
              </div>
            </div>

            {/* RAM Usage */}
            <div>
              <div className="flex items-center justify-between mb-xs">
                <span className="text-sm text-arc-muted">RAM Usage</span>
                <Badge variant={system.ram_percent > 80 ? 'danger' : system.ram_percent > 60 ? 'warning' : 'success'}>
                  {system.ram_percent.toFixed(1)}%
                </Badge>
              </div>
              <div className="w-full bg-arc-surface h-2 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-arc ${
                    system.ram_percent > 80
                      ? 'bg-arc-danger'
                      : system.ram_percent > 60
                      ? 'bg-arc-warning'
                      : 'bg-arc-success'
                  }`}
                  style={{ width: `${system.ram_percent}%` }}
                />
              </div>
              <p className="text-xs text-arc-subtle mt-2xs">
                {(system.ram_used_mb / 1024).toFixed(1)} GB / {(system.ram_total_mb / 1024).toFixed(1)} GB
              </p>
            </div>

            {/* Temperature (if available) */}
            {system.temperature_c !== null && (
              <div>
                <div className="flex items-center justify-between mb-xs">
                  <span className="text-sm text-arc-muted">Temperature</span>
                  <Badge variant={system.temperature_c > 75 ? 'danger' : system.temperature_c > 60 ? 'warning' : 'success'}>
                    {system.temperature_c.toFixed(1)}°C
                  </Badge>
                </div>
                <div className="w-full bg-arc-surface h-2 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-arc ${
                      system.temperature_c > 75
                        ? 'bg-arc-danger'
                        : system.temperature_c > 60
                        ? 'bg-arc-warning'
                        : 'bg-arc-success'
                    }`}
                    style={{ width: `${Math.min((system.temperature_c / 85) * 100, 100)}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-arc-subtle text-center py-lg">No system metrics available</p>
        )}
      </Panel>

      {/* Pipeline Metrics */}
      <Panel title="Pipeline Performance">
        {summaryLoading ? (
          <div className="flex items-center justify-center py-xl">
            <Spinner size="lg" />
          </div>
        ) : summary && summary.pipelines && summary.pipelines.length > 0 ? (
          <div className="space-y-md">
            {summary.pipelines.map((pipeline) => (
              <div key={pipeline.pipeline_id} className="border-b border-arc-border last:border-0 pb-md last:pb-0">
                <div className="flex items-center justify-between mb-sm">
                  <h3 className="font-medium text-arc-text">{pipeline.pipeline_name}</h3>
                  <Badge variant="info">{pipeline.pipeline_type}</Badge>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-md">
                  {/* FPS */}
                  <div>
                    <p className="text-xs text-arc-muted mb-3xs">FPS</p>
                    <p className="text-lg font-semibold text-arc-text">
                      {pipeline.fps?.toFixed(1) || '0.0'}
                    </p>
                  </div>

                  {/* Latency */}
                  <div>
                    <p className="text-xs text-arc-muted mb-3xs">Avg Latency</p>
                    <p className="text-lg font-semibold text-arc-text">
                      {pipeline.latency_avg_ms?.toFixed(0) || '0'} ms
                    </p>
                  </div>

                  {/* Queue Depth */}
                  <div>
                    <p className="text-xs text-arc-muted mb-3xs">Queue Depth</p>
                    <p className="text-lg font-semibold text-arc-text">
                      {pipeline.queue_depth || 0}
                    </p>
                  </div>

                  {/* Dropped Frames */}
                  <div>
                    <p className="text-xs text-arc-muted mb-3xs">Dropped Frames</p>
                    <p className="text-lg font-semibold text-arc-text">
                      {pipeline.frames_dropped || 0}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-arc-subtle text-center py-lg">No active pipelines</p>
        )}
      </Panel>

      {/* Camera Status */}
      {summary && summary.cameras && summary.cameras.length > 0 && (
        <Panel title="Camera Status">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-md">
            {summary.cameras.map((camera) => (
              <div
                key={camera.camera_id}
                className="p-md bg-arc-surface rounded-arc-sm border border-arc-border"
              >
                <div className="flex items-center justify-between mb-sm">
                  <h3 className="font-medium text-arc-text">{camera.camera_name}</h3>
                  <Badge variant={camera.is_active ? 'success' : 'default'} dot>
                    {camera.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </div>
                <p className="text-sm text-arc-subtle">{camera.camera_type}</p>
                {camera.is_active && camera.fps && (
                  <p className="text-xs text-arc-muted mt-xs">{camera.fps.toFixed(1)} FPS</p>
                )}
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}
