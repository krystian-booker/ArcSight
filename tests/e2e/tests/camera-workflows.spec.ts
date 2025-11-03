import { test, expect } from '@playwright/test';
import { CamerasPage } from '../pages/CamerasPage';

/**
 * E2E tests for camera management workflows
 * Tests camera discovery, registration, configuration, and deletion
 */
test.describe('Camera Management Workflows', () => {
  let camerasPage: CamerasPage;

  test.beforeEach(async ({ page }) => {
    camerasPage = new CamerasPage(page);

    // Reset database before each test
    await page.request.post('/test/reset-database');

    // Navigate to cameras page
    await camerasPage.navigate();
  });

  test('should display empty cameras page initially', async () => {
    // Verify page title
    await expect(camerasPage.page).toHaveTitle(/Cameras/);

    // Verify empty state
    const isEmpty = await camerasPage.isTableEmpty();
    expect(isEmpty).toBe(true);

    // Verify camera count is 0
    const count = await camerasPage.getCameraCount();
    expect(count).toBe(0);

    // Verify add button is visible
    await expect(camerasPage.addCameraButton).toBeVisible();
  });

  test('should add a USB camera successfully', async () => {
    // Add a camera
    await camerasPage.addCamera({
      name: 'Test USB Camera',
      type: 'USB',
      identifier: 'test_usb_0',
    });

    // Verify camera appears in table
    const cameraNames = await camerasPage.getCameraNames();
    expect(cameraNames).toContain('Test USB Camera');

    // Verify camera count is updated
    const count = await camerasPage.getCameraCount();
    expect(count).toBe(1);

    // Verify camera details
    const camera = await camerasPage.getCameraByName('Test USB Camera');
    expect(camera).not.toBeNull();
    expect(camera?.type).toBe('USB');
    expect(camera?.identifier).toBe('test_usb_0');
  });

  test('should add multiple cameras', async () => {
    // Add first camera
    await camerasPage.addCamera({
      name: 'Camera One',
      type: 'USB',
      identifier: 'test_usb_0',
    });

    // Add second camera
    await camerasPage.addCamera({
      name: 'Camera Two',
      type: 'USB',
      identifier: 'test_usb_1',
    });

    // Verify both cameras appear
    const cameraNames = await camerasPage.getCameraNames();
    expect(cameraNames).toContain('Camera One');
    expect(cameraNames).toContain('Camera Two');

    // Verify camera count
    const count = await camerasPage.getCameraCount();
    expect(count).toBe(2);
  });

  test('should delete a camera', async () => {
    // Add a camera first
    await camerasPage.addCamera({
      name: 'Camera To Delete',
      type: 'USB',
      identifier: 'test_usb_0',
    });

    // Verify camera exists
    let cameraNames = await camerasPage.getCameraNames();
    expect(cameraNames).toContain('Camera To Delete');

    // Delete the camera
    await camerasPage.deleteCamera('Camera To Delete');

    // Verify camera is removed
    cameraNames = await camerasPage.getCameraNames();
    expect(cameraNames).not.toContain('Camera To Delete');

    // Verify empty state is shown
    const isEmpty = await camerasPage.isTableEmpty();
    expect(isEmpty).toBe(true);
  });

  test('should show camera status', async ({ page }) => {
    // Seed test data with a camera
    await page.request.post('/test/seed-test-data');

    // Reload page
    await camerasPage.navigate();

    // Get camera details
    const camera = await camerasPage.getCameraByName('Test Camera 1');
    expect(camera).not.toBeNull();

    // Status should be one of: Connected, Disconnected, Checking, Error
    expect(camera?.status).toMatch(/Connected|Disconnected|Checking|Error/);
  });

  test('should display camera information correctly', async () => {
    // Add a camera with specific details
    await camerasPage.addCamera({
      name: 'Industrial Camera',
      type: 'GenICam',
      identifier: 'genicam_12345',
    });

    // Get camera details
    const camera = await camerasPage.getCameraByName('Industrial Camera');

    // Verify all fields are displayed
    expect(camera).not.toBeNull();
    expect(camera?.name).toBe('Industrial Camera');
    expect(camera?.type).toBe('GenICam');
    expect(camera?.identifier).toBe('genicam_12345');
    expect(camera?.status).toBeTruthy();
  });

  test('should handle camera with special characters in name', async () => {
    const specialName = 'Test Camera #1 (Primary)';

    await camerasPage.addCamera({
      name: specialName,
      type: 'USB',
      identifier: 'test_special',
    });

    // Verify camera with special name appears correctly
    const cameraNames = await camerasPage.getCameraNames();
    expect(cameraNames).toContain(specialName);

    const camera = await camerasPage.getCameraByName(specialName);
    expect(camera?.name).toBe(specialName);
  });

  test('should navigate to cameras page from other pages', async ({ page }) => {
    // Start on dashboard
    await page.goto('/');
    await camerasPage.waitForPageReady();

    // Navigate to cameras via nav link
    await camerasPage.navigateTo('Cameras');

    // Verify we're on cameras page
    await expect(page).toHaveURL(/\/cameras/);
    await expect(page).toHaveTitle(/Cameras/);
  });
});
