import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';

/**
 * E2E tests for pipeline management workflows
 * Tests pipeline creation, configuration, switching, and deletion
 */
test.describe('Pipeline Management Workflows', () => {
  let dashboardPage: DashboardPage;

  test.beforeEach(async ({ page }) => {
    dashboardPage = new DashboardPage(page);

    // Reset database and seed test data (includes cameras)
    await page.request.post('/test/reset-database');
    await page.request.post('/test/seed-test-data');

    // Navigate to dashboard
    await dashboardPage.navigate();
  });

  test('should display dashboard with seeded data', async () => {
    // Verify page title
    await expect(dashboardPage.page).toHaveTitle(/Dashboard/);

    // Verify camera count
    const cameraCount = await dashboardPage.getCameraCount();
    expect(cameraCount).toBeGreaterThan(0);

    // Verify cameras are available in dropdown
    const cameras = await dashboardPage.getAvailableCameras();
    expect(cameras.length).toBeGreaterThan(0);
  });

  test('should select a camera', async () => {
    // Get available cameras
    const cameras = await dashboardPage.getAvailableCameras();
    expect(cameras.length).toBeGreaterThan(0);

    // Select first camera
    await dashboardPage.selectCamera(cameras[0]);

    // Verify camera is selected (add pipeline button should be enabled)
    await expect(dashboardPage.addPipelineButton).toBeEnabled();
  });

  test('should add an AprilTag pipeline', async () => {
    // Select a camera first
    const cameras = await dashboardPage.getAvailableCameras();
    await dashboardPage.selectCamera(cameras[0]);

    // Add pipeline
    await dashboardPage.addPipeline('AprilTag Test', 'AprilTag');

    // Verify pipeline appears in dropdown
    const pipelines = await dashboardPage.getAvailablePipelines();
    expect(pipelines).toContain('AprilTag Test');

    // Verify pipeline count increased
    const pipelineCount = await dashboardPage.getPipelineCount();
    expect(pipelineCount).toBeGreaterThan(0);
  });

  test('should add multiple pipeline types', async () => {
    // Select a camera
    const cameras = await dashboardPage.getAvailableCameras();
    await dashboardPage.selectCamera(cameras[0]);

    // Add AprilTag pipeline
    await dashboardPage.addPipeline('Tags Pipeline', 'AprilTag');

    // Add ColourShape pipeline
    await dashboardPage.addPipeline('Shapes Pipeline', 'ColouredShape');

    // Verify both pipelines exist
    const pipelines = await dashboardPage.getAvailablePipelines();
    expect(pipelines).toContain('Tags Pipeline');
    expect(pipelines).toContain('Shapes Pipeline');

    // Verify pipeline count
    const pipelineCount = await dashboardPage.getPipelineCount();
    expect(pipelineCount).toBeGreaterThanOrEqual(2);
  });

  test('should select and switch between pipelines', async () => {
    // Select camera and add pipelines
    const cameras = await dashboardPage.getAvailableCameras();
    await dashboardPage.selectCamera(cameras[0]);

    await dashboardPage.addPipeline('Pipeline A', 'AprilTag');
    await dashboardPage.addPipeline('Pipeline B', 'ColouredShape');

    // Select first pipeline
    await dashboardPage.selectPipeline('Pipeline A');

    // Pipeline type should update (if visible in UI)
    // This verifies the selection worked

    // Switch to second pipeline
    await dashboardPage.selectPipeline('Pipeline B');

    // Verify we can interact with pipeline controls
    await expect(dashboardPage.renamePipelineButton).toBeEnabled();
    await expect(dashboardPage.deletePipelineButton).toBeEnabled();
  });

  test('should delete a pipeline', async () => {
    // Select camera and add pipeline
    const cameras = await dashboardPage.getAvailableCameras();
    await dashboardPage.selectCamera(cameras[0]);

    await dashboardPage.addPipeline('Pipeline To Delete', 'AprilTag');

    // Verify pipeline exists
    let pipelines = await dashboardPage.getAvailablePipelines();
    expect(pipelines).toContain('Pipeline To Delete');

    // Select and delete the pipeline
    await dashboardPage.selectPipeline('Pipeline To Delete');
    await dashboardPage.deletePipeline();

    // Verify pipeline is removed
    pipelines = await dashboardPage.getAvailablePipelines();
    expect(pipelines).not.toContain('Pipeline To Delete');
  });

  test('should rename a pipeline', async () => {
    // Select camera and add pipeline
    const cameras = await dashboardPage.getAvailableCameras();
    await dashboardPage.selectCamera(cameras[0]);

    await dashboardPage.addPipeline('Original Name', 'AprilTag');

    // Select and rename the pipeline
    await dashboardPage.selectPipeline('Original Name');
    await dashboardPage.renamePipeline('New Name');

    // Verify pipeline has new name
    const pipelines = await dashboardPage.getAvailablePipelines();
    expect(pipelines).toContain('New Name');
    expect(pipelines).not.toContain('Original Name');
  });

  test('should disable pipeline controls when no camera selected', async () => {
    // Ensure no camera is selected
    await dashboardPage.cameraSelect.selectOption('');

    // Add pipeline button should be disabled
    await expect(dashboardPage.addPipelineButton).toBeDisabled();

    // Pipeline select should be disabled
    await expect(dashboardPage.pipelineSelect).toBeDisabled();
  });

  test('should disable pipeline actions when no pipeline selected', async () => {
    // Select a camera but no pipeline
    const cameras = await dashboardPage.getAvailableCameras();
    await dashboardPage.selectCamera(cameras[0]);

    // Ensure no pipeline is selected
    await dashboardPage.pipelineSelect.selectOption('');

    // Rename and delete buttons should be disabled
    await expect(dashboardPage.renamePipelineButton).toBeDisabled();
    await expect(dashboardPage.deletePipelineButton).toBeDisabled();
  });

  test('should persist pipelines across page reloads', async () => {
    // Select camera and add pipeline
    const cameras = await dashboardPage.getAvailableCameras();
    await dashboardPage.selectCamera(cameras[0]);

    await dashboardPage.addPipeline('Persistent Pipeline', 'AprilTag');

    // Reload page
    await dashboardPage.navigate();

    // Select same camera
    await dashboardPage.selectCamera(cameras[0]);

    // Verify pipeline still exists
    const pipelines = await dashboardPage.getAvailablePipelines();
    expect(pipelines).toContain('Persistent Pipeline');
  });

  test('should show correct pipeline count in info bar', async () => {
    // Get initial count
    const initialCount = await dashboardPage.getPipelineCount();

    // Select camera and add pipeline
    const cameras = await dashboardPage.getAvailableCameras();
    await dashboardPage.selectCamera(cameras[0]);

    await dashboardPage.addPipeline('Count Test Pipeline', 'AprilTag');

    // Verify count increased
    const newCount = await dashboardPage.getPipelineCount();
    expect(newCount).toBe(initialCount + 1);

    // Delete pipeline
    await dashboardPage.selectPipeline('Count Test Pipeline');
    await dashboardPage.deletePipeline();

    // Verify count decreased
    const finalCount = await dashboardPage.getPipelineCount();
    expect(finalCount).toBe(initialCount);
  });
});
