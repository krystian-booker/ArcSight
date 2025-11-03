import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';
import { CamerasPage } from '../pages/CamerasPage';

/**
 * Visual regression tests
 * Captures and compares screenshots to detect unintended UI changes
 */
test.describe('Visual Regression Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Reset and seed database for consistent state
    await page.request.post('/test/reset-database');
    await page.request.post('/test/seed-test-data');
  });

  test('dashboard page layout should match baseline', async ({ page }) => {
    const dashboardPage = new DashboardPage(page);
    await dashboardPage.navigate();

    // Wait for all content to load
    await page.waitForTimeout(1000);

    // Take full page screenshot
    await expect(page).toHaveScreenshot('dashboard-layout.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('cameras page empty state should match baseline', async ({ page }) => {
    // Use empty database for this test
    await page.request.post('/test/reset-database');

    const camerasPage = new CamerasPage(page);
    await camerasPage.navigate();

    // Wait for page to fully render
    await page.waitForTimeout(500);

    // Take screenshot of empty state
    await expect(page).toHaveScreenshot('cameras-empty-state.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('cameras page with data should match baseline', async ({ page }) => {
    const camerasPage = new CamerasPage(page);
    await camerasPage.navigate();

    // Wait for cameras to load
    await page.waitForTimeout(1000);

    // Take screenshot with camera data
    await expect(page).toHaveScreenshot('cameras-with-data.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('dashboard with selected camera should match baseline', async ({ page }) => {
    const dashboardPage = new DashboardPage(page);
    await dashboardPage.navigate();

    // Select first camera
    const cameras = await dashboardPage.getAvailableCameras();
    if (cameras.length > 0) {
      await dashboardPage.selectCamera(cameras[0]);
      await page.waitForTimeout(500);

      // Take screenshot
      await expect(page).toHaveScreenshot('dashboard-camera-selected.png', {
        fullPage: true,
        animations: 'disabled',
      });
    }
  });

  test('camera table row should match baseline', async ({ page }) => {
    const camerasPage = new CamerasPage(page);
    await camerasPage.navigate();

    // Wait for table to load
    await page.waitForTimeout(1000);

    // Take screenshot of just the first camera row
    const firstRow = camerasPage.cameraRows.first();
    await expect(firstRow).toHaveScreenshot('camera-table-row.png', {
      animations: 'disabled',
    });
  });

  test('pipeline controls panel should match baseline', async ({ page }) => {
    const dashboardPage = new DashboardPage(page);
    await dashboardPage.navigate();

    // Select camera to enable pipeline controls
    const cameras = await dashboardPage.getAvailableCameras();
    if (cameras.length > 0) {
      await dashboardPage.selectCamera(cameras[0]);
      await page.waitForTimeout(500);

      // Take screenshot of the pipeline setup panel
      const setupPanel = page.locator('.panel').filter({ hasText: 'Pipeline & Camera Setup' });
      await expect(setupPanel).toHaveScreenshot('pipeline-controls-panel.png', {
        animations: 'disabled',
      });
    }
  });

  test('navigation header should match baseline', async ({ page }) => {
    const dashboardPage = new DashboardPage(page);
    await dashboardPage.navigate();

    // Screenshot of just the navigation/header
    const header = page.locator('nav, header').first();
    await expect(header).toHaveScreenshot('navigation-header.png', {
      animations: 'disabled',
    });
  });

  test('camera status pills should match baseline', async ({ page }) => {
    const camerasPage = new CamerasPage(page);
    await camerasPage.navigate();

    // Wait for status to update
    await page.waitForTimeout(1500);

    // Get all status pills
    const statusPills = page.locator('.status-pill');
    const count = await statusPills.count();

    if (count > 0) {
      // Screenshot first status pill
      await expect(statusPills.first()).toHaveScreenshot('status-pill.png', {
        animations: 'disabled',
      });
    }
  });

  test('responsive layout on mobile viewport', async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });

    const dashboardPage = new DashboardPage(page);
    await dashboardPage.navigate();

    await page.waitForTimeout(500);

    // Take screenshot of mobile layout
    await expect(page).toHaveScreenshot('dashboard-mobile.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('responsive layout on tablet viewport', async ({ page }) => {
    // Set tablet viewport
    await page.setViewportSize({ width: 768, height: 1024 });

    const camerasPage = new CamerasPage(page);
    await camerasPage.navigate();

    await page.waitForTimeout(500);

    // Take screenshot of tablet layout
    await expect(page).toHaveScreenshot('cameras-tablet.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });
});
