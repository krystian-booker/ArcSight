import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * Page Object Model for the Cameras page
 * Handles camera discovery, registration, and configuration
 */
export class CamerasPage extends BasePage {
  // Selectors
  readonly addCameraButton: Locator;
  readonly camerasTable: Locator;
  readonly cameraRows: Locator;
  readonly deviceCountBadge: Locator;

  constructor(page: Page) {
    super(page);

    this.addCameraButton = page.getByRole('button', { name: /Add Camera/i });
    this.camerasTable = page.locator('table.table');
    this.cameraRows = this.camerasTable.locator('tbody tr');
    this.deviceCountBadge = page.locator('.status-pill').filter({ hasText: /device/ });
  }

  /**
   * Navigate to cameras page
   */
  async navigate() {
    await this.goto('/cameras');
    await this.waitForPageReady();
  }

  /**
   * Get the number of registered cameras
   */
  async getCameraCount(): Promise<number> {
    const text = await this.deviceCountBadge.textContent();
    const match = text?.match(/(\d+)/);
    return match ? parseInt(match[1]) : 0;
  }

  /**
   * Check if the cameras table is empty
   */
  async isTableEmpty(): Promise<boolean> {
    const emptyMessage = this.page.locator('text=/No cameras registered/i');
    return await this.isVisible(emptyMessage);
  }

  /**
   * Get all camera names from the table
   */
  async getCameraNames(): Promise<string[]> {
    const rows = await this.cameraRows.all();
    const names: string[] = [];

    for (const row of rows) {
      const nameCell = row.locator('td').first();
      const text = await nameCell.textContent();
      if (text && !text.includes('Loading') && !text.includes('No cameras')) {
        // Extract just the camera name (without ID)
        const name = text.split('ID:')[0].trim();
        names.push(name);
      }
    }

    return names;
  }

  /**
   * Get camera details by name
   */
  async getCameraByName(name: string) {
    const row = this.cameraRows.filter({ hasText: name }).first();

    if (!await this.isVisible(row)) {
      return null;
    }

    const cells = row.locator('td');
    const nameText = await cells.nth(0).textContent();
    const type = await cells.nth(1).textContent();
    const identifier = await cells.nth(2).textContent();
    const statusPill = cells.nth(3).locator('.status-pill');
    const status = await statusPill.textContent();

    return {
      name: nameText?.split('ID:')[0].trim() || '',
      type: type?.trim() || '',
      identifier: identifier?.trim() || '',
      status: status?.trim() || '',
    };
  }

  /**
   * Click add camera button to open modal
   */
  async clickAddCamera() {
    await this.addCameraButton.click();
    await this.page.waitForSelector('[role="dialog"], .modal', { state: 'visible' });
  }

  /**
   * Add a camera via the modal
   */
  async addCamera(params: {
    name: string;
    type: 'USB' | 'GenICam' | 'OAK-D' | 'RealSense';
    identifier: string;
  }) {
    await this.clickAddCamera();

    const modal = this.page.locator('[role="dialog"], .modal').first();

    // Fill in camera details
    await modal.locator('input[name="name"], input[placeholder*="name"]').fill(params.name);
    await modal.locator('select[name="type"], select').first().selectOption(params.type);
    await modal.locator('input[name="identifier"], input[placeholder*="identifier"]').fill(params.identifier);

    // Submit
    await modal.getByRole('button', { name: /Add|Create|Save/i }).click();

    // Wait for modal to close and camera to be added
    await this.page.waitForSelector('[role="dialog"], .modal', { state: 'hidden' });
    await this.page.waitForTimeout(1000); // Wait for camera status to update
  }

  /**
   * Delete a camera by name
   */
  async deleteCamera(name: string) {
    const row = this.cameraRows.filter({ hasText: name }).first();

    // Find and click delete button
    const deleteButton = row.getByRole('button', { name: /Delete/i });
    await deleteButton.click();

    // Confirm deletion
    const confirmButton = this.page.getByRole('button', { name: /Delete|Confirm|Yes/i });
    if (await this.isVisible(confirmButton)) {
      await confirmButton.click();
    }

    await this.page.waitForTimeout(500);
  }

  /**
   * Check if a camera is connected
   */
  async isCameraConnected(name: string): Promise<boolean> {
    const camera = await this.getCameraByName(name);
    return camera?.status.includes('Connected') || false;
  }

  /**
   * Wait for camera status to update
   */
  async waitForCameraStatus(name: string, expectedStatus: 'Connected' | 'Disconnected', timeout: number = 10000) {
    const row = this.cameraRows.filter({ hasText: name }).first();
    const statusPill = row.locator('.status-pill').filter({ hasText: expectedStatus });

    await statusPill.waitFor({ state: 'visible', timeout });
  }

  /**
   * Open camera controls/settings
   */
  async openCameraControls(name: string) {
    const row = this.cameraRows.filter({ hasText: name }).first();
    const controlsButton = row.getByRole('button', { name: /Controls|Settings|Configure/i });
    await controlsButton.click();

    // Wait for controls panel to expand
    await this.page.waitForTimeout(500);
  }

  /**
   * Update camera exposure
   */
  async updateExposure(cameraName: string, mode: 'auto' | 'manual', value?: number) {
    await this.openCameraControls(cameraName);

    const controlsPanel = this.page.locator('[data-camera-controls], .camera-controls-panel').first();

    // Set exposure mode
    const exposureModeSelect = controlsPanel.locator('select[name*="exposure"]').first();
    await exposureModeSelect.selectOption(mode);

    // If manual, set value
    if (mode === 'manual' && value !== undefined) {
      const exposureInput = controlsPanel.locator('input[name*="exposure"]');
      await exposureInput.fill(value.toString());
    }

    // Save changes
    const saveButton = controlsPanel.getByRole('button', { name: /Save|Apply|Update/i });
    await saveButton.click();
    await this.page.waitForTimeout(500);
  }

  /**
   * Check if cameras are loading
   */
  async isLoading(): Promise<boolean> {
    const loadingMessage = this.page.locator('text=/Loading cameras/i');
    return await this.isVisible(loadingMessage);
  }
}
