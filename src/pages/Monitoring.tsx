import { useState } from 'react'
import { Activity, Cpu, HardDrive, Thermometer, Zap, AlertCircle } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { api } from '@/lib/api'
import { usePolling } from '@/hooks/usePolling'
import type { MetricsSummary } from '@/types'

export default function Monitoring() {
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchMetrics = async () => {
    try {
      const data = await api.get<MetricsSummary>('/api/metrics/summary')
      setMetrics(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch metrics')
    } finally {
      setIsLoading(false)
    }
  }

  // Poll every 2 seconds
  usePolling(fetchMetrics, 2000)

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="flex items-center justify-center h-96">
          <div className="flex flex-col items-center gap-2">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-[var(--color-border-strong)] border-t-[var(--color-primary)]"></div>
            <p className="text-sm text-muted">Loading metrics...</p>
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="flex items-center justify-center h-96">
          <div className="text-center">
            <AlertCircle className="h-12 w-12 text-[var(--color-danger)] mx-auto mb-4" />
            <h2 className="text-xl font-semibold mb-2">Metrics Unavailable</h2>
            <p className="text-muted">{error}</p>
          </div>
        </div>
      </div>
    )
  }

  if (!metrics) {
    return null
  }

  const { system, pipelines, thresholds } = metrics

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-semibold mb-2">Monitoring</h1>
        <p className="text-muted">Real-time system and pipeline performance metrics</p>
      </div>

      {/* System Resources */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">CPU Usage</CardTitle>
            <Cpu className="h-4 w-4 text-muted" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{(system.cpu_percent ?? 0).toFixed(1)}%</div>
            <Progress value={system.cpu_percent ?? 0} className="mt-2" />
            <p className="text-xs text-muted mt-2">
              {(system.cpu_percent ?? 0) > 80 ? 'High usage' : 'Normal'}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">RAM Usage</CardTitle>
            <HardDrive className="h-4 w-4 text-muted" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{(system.ram_percent ?? 0).toFixed(1)}%</div>
            <Progress value={system.ram_percent ?? 0} className="mt-2" />
            <p className="text-xs text-muted mt-2">
              {(system.ram_used_mb ?? 0).toFixed(0)} / {(system.ram_total_mb ?? 0).toFixed(0)} MB
            </p>
          </CardContent>
        </Card>

        {system.cpu_temp_celsius !== null && system.cpu_temp_celsius !== undefined && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">CPU Temperature</CardTitle>
              <Thermometer className="h-4 w-4 text-muted" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{system.cpu_temp_celsius.toFixed(1)}°C</div>
              <Progress
                value={Math.min((system.cpu_temp_celsius / 85) * 100, 100)}
                className="mt-2"
              />
              <p className="text-xs text-muted mt-2">
                {system.cpu_temp_celsius > 70 ? 'Hot' : 'Normal'}
              </p>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Pipelines</CardTitle>
            <Activity className="h-4 w-4 text-muted" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{system.active_pipelines ?? 0}</div>
            <p className="text-xs text-muted mt-2">
              Process: {(system.process_rss_mb ?? 0).toFixed(0)} MB
            </p>
            <p className="text-xs text-muted">
              Drops/min: {(system.total_drops_per_minute ?? 0).toFixed(1)}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Performance Alert */}
      {system.latency_alert && (
        <Card className="border-[var(--color-warning)]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-[var(--color-warning)]">
              <Zap className="h-5 w-5" />
              Performance Alert
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm">
              High latency detected. Pipeline processing is slower than {thresholds.latency_warn_ms}ms.
              Consider reducing pipeline complexity or camera resolution.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Pipeline Metrics Table */}
      {pipelines.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Pipeline Performance</CardTitle>
            <CardDescription>
              Real-time metrics for active vision pipelines
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Pipeline</TableHead>
                  <TableHead>FPS</TableHead>
                  <TableHead>Latency (avg)</TableHead>
                  <TableHead>Latency (p95)</TableHead>
                  <TableHead>Latency (max)</TableHead>
                  <TableHead>Queue Depth</TableHead>
                  <TableHead>Drops</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pipelines.map((pipeline) => (
                  <TableRow key={pipeline.pipeline_id}>
                    <TableCell className="font-medium">{pipeline.pipeline_name}</TableCell>
                    <TableCell>{pipeline.fps.toFixed(1)}</TableCell>
                    <TableCell>{pipeline.latency_avg_ms.toFixed(1)}ms</TableCell>
                    <TableCell>{pipeline.latency_p95_ms.toFixed(1)}ms</TableCell>
                    <TableCell>{pipeline.latency_max_ms.toFixed(1)}ms</TableCell>
                    <TableCell>
                      <span className={pipeline.queue_depth > 5 ? 'text-[var(--color-warning)]' : ''}>
                        {pipeline.queue_depth}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className={pipeline.total_drops > 0 ? 'text-[var(--color-danger)]' : ''}>
                        {pipeline.total_drops}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          pipeline.status === 'ok'
                            ? 'success'
                            : pipeline.status === 'warning'
                            ? 'warning'
                            : 'destructive'
                        }
                      >
                        {pipeline.status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="py-8">
            <div className="text-center">
              <Activity className="h-12 w-12 text-muted mx-auto mb-4 opacity-50" />
              <p className="text-muted">No active pipelines</p>
              <p className="text-sm text-subtle mt-1">
                Configure pipelines in the Dashboard to see performance metrics
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Thresholds Info */}
      <Card>
        <CardHeader>
          <CardTitle>Monitoring Configuration</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-muted">Queue High Water:</span>
              <span className="ml-2 font-medium">{thresholds.queue_high_water_pct}%</span>
            </div>
            <div>
              <span className="text-muted">Latency Warning:</span>
              <span className="ml-2 font-medium">{thresholds.latency_warn_ms}ms</span>
            </div>
            <div>
              <span className="text-muted">Window Size:</span>
              <span className="ml-2 font-medium">{thresholds.window_seconds}s</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
