import { APIRequestContext } from '@playwright/test';

/**
 * Database fixture helpers for E2E tests
 * Provides utilities to set up and tear down test data
 */

export interface CameraFixture {
  name: string;
  identifier: string;
  camera_type: 'USB' | 'GenICam' | 'OAK-D' | 'RealSense';
  device_info?: Record<string, any>;
}

export interface PipelineFixture {
  name: string;
  camera_id: number;
  pipeline_type: 'AprilTag' | 'ColouredShape' | 'ObjectDetectionML';
  config?: Record<string, any>;
}

/**
 * Reset the test database to a clean state
 */
export async function resetDatabase(request: APIRequestContext): Promise<void> {
  const response = await request.post('/test/reset-database');
  if (!response.ok()) {
    throw new Error(`Failed to reset database: ${response.status()} ${response.statusText()}`);
  }
}

/**
 * Seed the database with default test data
 */
export async function seedTestData(request: APIRequestContext): Promise<any> {
  const response = await request.post('/test/seed-test-data');
  if (!response.ok()) {
    throw new Error(`Failed to seed test data: ${response.status()} ${response.statusText()}`);
  }
  return await response.json();
}

/**
 * Create a camera via the API
 */
export async function createCamera(
  request: APIRequestContext,
  camera: CameraFixture
): Promise<number> {
  const response = await request.post('/cameras/add', {
    data: {
      name: camera.name,
      identifier: camera.identifier,
      camera_type: camera.camera_type,
      device_info: JSON.stringify(camera.device_info || {}),
    },
  });

  if (!response.ok()) {
    throw new Error(`Failed to create camera: ${response.status()} ${response.statusText()}`);
  }

  const data = await response.json();
  return data.camera_id || data.id;
}

/**
 * Create multiple cameras
 */
export async function createCameras(
  request: APIRequestContext,
  cameras: CameraFixture[]
): Promise<number[]> {
  const ids: number[] = [];
  for (const camera of cameras) {
    const id = await createCamera(request, camera);
    ids.push(id);
  }
  return ids;
}

/**
 * Delete a camera via the API
 */
export async function deleteCamera(
  request: APIRequestContext,
  cameraId: number
): Promise<void> {
  const response = await request.post(`/cameras/delete/${cameraId}`);
  if (!response.ok()) {
    throw new Error(`Failed to delete camera: ${response.status()} ${response.statusText()}`);
  }
}

/**
 * Create a pipeline via the API
 */
export async function createPipeline(
  request: APIRequestContext,
  pipeline: PipelineFixture
): Promise<number> {
  const response = await request.post(`/api/cameras/${pipeline.camera_id}/pipelines`, {
    data: {
      name: pipeline.name,
      pipeline_type: pipeline.pipeline_type,
      config: JSON.stringify(pipeline.config || {}),
    },
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok()) {
    throw new Error(`Failed to create pipeline: ${response.status()} ${response.statusText()}`);
  }

  const data = await response.json();
  return data.pipeline_id || data.id;
}

/**
 * Delete a pipeline via the API
 */
export async function deletePipeline(
  request: APIRequestContext,
  pipelineId: number
): Promise<void> {
  const response = await request.delete(`/api/pipelines/${pipelineId}`);
  if (!response.ok()) {
    throw new Error(`Failed to delete pipeline: ${response.status()} ${response.statusText()}`);
  }
}

/**
 * Get all cameras via the API
 */
export async function getAllCameras(request: APIRequestContext): Promise<any[]> {
  const response = await request.get('/api/pipelines/cameras');
  if (!response.ok()) {
    throw new Error(`Failed to get cameras: ${response.status()} ${response.statusText()}`);
  }
  return await response.json();
}

/**
 * Get pipelines for a camera via the API
 */
export async function getCameraPipelines(
  request: APIRequestContext,
  cameraId: number
): Promise<any[]> {
  const response = await request.get(`/api/cameras/${cameraId}/pipelines`);
  if (!response.ok()) {
    throw new Error(`Failed to get pipelines: ${response.status()} ${response.statusText()}`);
  }
  return await response.json();
}

/**
 * Predefined camera fixtures for common test scenarios
 */
export const CAMERA_FIXTURES = {
  USB_DEFAULT: {
    name: 'Test USB Camera',
    identifier: 'test_usb_0',
    camera_type: 'USB' as const,
    device_info: { index: 0 },
  },
  USB_SECONDARY: {
    name: 'Test USB Camera 2',
    identifier: 'test_usb_1',
    camera_type: 'USB' as const,
    device_info: { index: 1 },
  },
  GENICAM_DEFAULT: {
    name: 'Test GenICam Camera',
    identifier: 'test_genicam_12345',
    camera_type: 'GenICam' as const,
    device_info: { serial: '12345', model: 'MockCam' },
  },
  REALSENSE_DEFAULT: {
    name: 'Test RealSense D435',
    identifier: 'test_realsense_f0123456',
    camera_type: 'RealSense' as const,
    device_info: { serial: 'f0123456', model: 'D435' },
  },
};

/**
 * Predefined pipeline fixtures for common test scenarios
 */
export const PIPELINE_FIXTURES = {
  APRILTAG_DEFAULT: (cameraId: number) => ({
    name: 'Test AprilTag Pipeline',
    camera_id: cameraId,
    pipeline_type: 'AprilTag' as const,
    config: { tag_family: 'tag36h11', threads: 1 },
  }),
  COLOURED_SHAPE_DEFAULT: (cameraId: number) => ({
    name: 'Test Coloured Shape Pipeline',
    camera_id: cameraId,
    pipeline_type: 'ColouredShape' as const,
    config: { min_area: 100 },
  }),
};
