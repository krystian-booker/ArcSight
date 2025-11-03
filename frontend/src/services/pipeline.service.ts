/**
 * Pipeline management service
 * Handles all pipeline-related API calls
 */

import { get, post, put, del, uploadFile } from './api.client';
import type {
  Pipeline,
  SuccessResponse,
  MLAvailability,
  FileUploadResponse,
} from '@/types';

/**
 * Get all pipelines (optionally filtered by camera)
 */
export async function listPipelines(cameraId?: number): Promise<Pipeline[]> {
  if (cameraId !== undefined) {
    return get<Pipeline[]>(`/api/cameras/${cameraId}/pipelines`);
  }
  return get<Pipeline[]>('/api/pipelines');
}

/**
 * Create a new pipeline
 */
export async function createPipeline(
  cameraId: number,
  data: {
    name: string;
    pipeline_type: string;
    config?: any;
  }
): Promise<Pipeline> {
  return post<Pipeline>(`/api/cameras/${cameraId}/pipelines`, data);
}

/**
 * Update pipeline metadata (name, type)
 */
export async function updatePipeline(
  pipelineId: number,
  data: {
    name?: string;
    pipeline_type?: string;
  }
): Promise<SuccessResponse> {
  return put<SuccessResponse>(`/api/pipelines/${pipelineId}`, data);
}

/**
 * Delete a pipeline
 */
export async function deletePipeline(pipelineId: number): Promise<SuccessResponse> {
  return del<SuccessResponse>(`/api/pipelines/${pipelineId}`);
}

/**
 * Update pipeline configuration
 */
export async function updatePipelineConfig(
  pipelineId: number,
  config: any
): Promise<SuccessResponse> {
  return put<SuccessResponse>(`/api/pipelines/${pipelineId}/config`, { config });
}

/**
 * Upload model or labels file for ML pipeline
 */
export async function uploadPipelineFile(
  pipelineId: number,
  file: File,
  fileType: 'model' | 'labels',
  onProgress?: (progress: number) => void
): Promise<FileUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('file_type', fileType);

  return uploadFile<FileUploadResponse>(
    `/api/pipelines/${pipelineId}/files`,
    formData,
    (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        onProgress(percentCompleted);
      }
    }
  );
}

/**
 * Delete model or labels file from ML pipeline
 */
export async function deletePipelineFile(
  pipelineId: number,
  fileType: 'model' | 'labels'
): Promise<{ updated_config: any }> {
  return del<{ updated_config: any }>(
    `/api/pipelines/${pipelineId}/files?file_type=${fileType}`
  );
}

/**
 * Get labels for ML pipeline
 */
export async function getPipelineLabels(pipelineId: number): Promise<{ labels: string[] }> {
  return get<{ labels: string[] }>(`/api/pipelines/${pipelineId}/labels`);
}

/**
 * Get ML runtime availability (ONNX, OpenVINO, CUDA)
 */
export async function getMLAvailability(): Promise<MLAvailability> {
  return get<MLAvailability>('/api/pipelines/ml/availability');
}

/**
 * Start a pipeline
 */
export async function startPipeline(pipelineId: number): Promise<SuccessResponse> {
  return post<SuccessResponse>(`/api/pipelines/${pipelineId}/start`);
}

/**
 * Stop a pipeline
 */
export async function stopPipeline(pipelineId: number): Promise<SuccessResponse> {
  return post<SuccessResponse>(`/api/pipelines/${pipelineId}/stop`);
}

/**
 * Get pipeline detection results
 */
export async function getPipelineResults(pipelineId: number): Promise<any> {
  return get<any>(`/api/pipelines/${pipelineId}/results`);
}
