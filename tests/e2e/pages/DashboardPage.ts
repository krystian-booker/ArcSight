import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * Page Object Model for the Dashboard page
 * Handles camera feed viewing and pipeline management
 */
export class DashboardPage extends BasePage {
  // Selectors
  readonly cameraSelect: Locator;
  readonly pipelineSelect: Locator;
  readonly pipelineTypeSelect: Locator;
  readonly addPipelineButton: Locator;
  readonly renamePipelineButton: Locator;
  readonly deletePipelineButton: Locator;
  readonly videoFeed: Locator;
  readonly feedTypeToggle: Locator;

  constructor(page: Page) {
    super(page);

    // Form controls
    this.cameraSelect = page.locator('#camera-select');
    this.pipelineSelect = page.locator('select.form-control.form-control--inline');
    this.pipelineTypeSelect = page.locator('#pipeline-type');
    this.addPipelineButton = page.getByRole('button', { name: /Add pipeline/i });
    this.renamePipelineButton = page.getByRole('button', { name: /Rename pipeline/i });
    this.deletePipelineButton = page.getByRole('button', { name: /Delete pipeline/i });

    // Video feed
    this.videoFeed = page.locator('img.camera-feed, img[alt*="feed"], video');

    // Feed type toggle (if exists)
    this.feedTypeToggle = page.locator('button:has-text("Feed Type"), select:has-text("Feed")');
  }

  /**
   * Navigate to dashboard
   */
  async navigate() {
    await this.goto('/');
    await this.waitForPageReady();
  }

  /**
   * Get the number of registered cameras displayed
   */
  async getCameraCount(): Promise<number> {
    const text = await this.page.locator('text=/Registered cameras:/').textContent();
    const match = text?.match(/(\d+)/);
    return match ? parseInt(match[1]) : 0;
  }

  /**
   * Get the number of pipelines displayed
   */
  async getPipelineCount(): Promise<number> {
    const text = await this.page.locator('text=/Pipelines:/').textContent();
    const match = text?.match(/(\d+)/);
    return match ? parseInt(match[1]) : 0;
  }

  /**
   * Select a camera from the dropdown
   */
  async selectCamera(cameraName: string) {
    await this.cameraSelect.selectOption({ label: cameraName });
    // Wait for pipelines to load
    await this.page.waitForTimeout(500);
  }

  /**
   * Select a pipeline from the dropdown
   */
  async selectPipeline(pipelineName: string) {
    await this.pipelineSelect.selectOption({ label: pipelineName });
    await this.page.waitForTimeout(300);
  }

  /**
   * Get all available cameras in the dropdown
   */
  async getAvailableCameras(): Promise<string[]> {
    const options = await this.cameraSelect.locator('option').allTextContents();
    return options.filter(opt => opt && !opt.includes('Select') && !opt.includes('No cameras'));
  }

  /**
   * Get all available pipelines in the dropdown
   */
  async getAvailablePipelines(): Promise<string[]> {
    const options = await this.pipelineSelect.locator('option').allTextContents();
    return options.filter(opt => opt && !opt.includes('Select'));
  }

  /**
   * Click add pipeline button and wait for modal
   */
  async clickAddPipeline() {
    await this.addPipelineButton.click();
    // Wait for modal to appear
    await this.page.waitForSelector('[role="dialog"], .modal', { state: 'visible' });
  }

  /**
   * Add a new pipeline via the modal
   */
  async addPipeline(name: string, type: 'AprilTag' | 'ColouredShape' | 'ObjectDetectionML') {
    await this.clickAddPipeline();

    // Fill in pipeline details in modal
    const modal = this.page.locator('[role="dialog"], .modal').first();
    await modal.locator('input[name="name"], input[placeholder*="name"]').fill(name);
    await modal.locator('select[name="type"], select').selectOption(type);

    // Submit
    await modal.getByRole('button', { name: /Add|Create|Save/i }).click();

    // Wait for modal to close
    await this.page.waitForSelector('[role="dialog"], .modal', { state: 'hidden' });
    await this.page.waitForTimeout(500);
  }

  /**
   * Delete the currently selected pipeline
   */
  async deletePipeline() {
    await this.deletePipelineButton.click();

    // Confirm deletion if there's a confirmation dialog
    const confirmButton = this.page.getByRole('button', { name: /Delete|Confirm|Yes/i });
    if (await this.isVisible(confirmButton)) {
      await confirmButton.click();
    }

    await this.page.waitForTimeout(500);
  }

  /**
   * Rename the currently selected pipeline
   */
  async renamePipeline(newName: string) {
    await this.renamePipelineButton.click();

    // Wait for rename modal/prompt
    const modal = this.page.locator('[role="dialog"], .modal').first();
    await modal.locator('input[type="text"]').fill(newName);
    await modal.getByRole('button', { name: /Save|Rename|OK/i }).click();

    await this.page.waitForSelector('[role="dialog"], .modal', { state: 'hidden' });
    await this.page.waitForTimeout(500);
  }

  /**
   * Check if video feed is displaying
   */
  async isVideoFeedVisible(): Promise<boolean> {
    return await this.isVisible(this.videoFeed);
  }

  /**
   * Wait for video feed to load
   */
  async waitForVideoFeed(timeout: number = 10000) {
    await this.videoFeed.waitFor({ state: 'visible', timeout });
  }

  /**
   * Toggle between default and processed feed
   */
  async toggleFeedType() {
    await this.feedTypeToggle.click();
    await this.page.waitForTimeout(500);
  }

  /**
   * Get current feed type from info bar
   */
  async getCurrentFeedType(): Promise<string> {
    const text = await this.page.locator('text=/Feed selector:/').textContent();
    return text?.includes('Processed') ? 'processed' : 'default';
  }
}
