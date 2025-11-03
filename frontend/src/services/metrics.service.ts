/**
 * Metrics and monitoring service
 * Handles performance metrics and system health
 */

import { get } from './api.client';
import type { MetricsSummary, SystemMetrics } from '@/types';

/**
 * Get pipeline metrics summary
 */
export async function getMetricsSummary(): Promise<MetricsSummary> {
  return get<MetricsSummary>('/api/metrics/summary');
}

/**
 * Get system metrics (CPU, RAM, temperature)
 */
export async function getSystemMetrics(): Promise<SystemMetrics> {
  return get<SystemMetrics>('/api/metrics/system');
}
