import { Page, Locator } from '@playwright/test';

/**
 * Base Page Object Model
 * Contains common functionality shared across all pages
 */
export class BasePage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  /**
   * Navigate to a specific path
   */
  async goto(path: string = '') {
    await this.page.goto(path);
  }

  /**
   * Wait for React to initialize
   * Checks for React root element to be rendered
   */
  async waitForReactInit() {
    // Wait for React root to be rendered
    await this.page.waitForSelector('#root', { timeout: 5000 });
    // Wait for React Router to settle
    await this.page.waitForFunction(
      () => {
        const root = document.getElementById('root');
        return root && root.children.length > 0;
      },
      { timeout: 5000 }
    );
  }

  /**
   * Wait for page to be fully loaded including React
   */
  async waitForPageReady() {
    await this.page.waitForLoadState('domcontentloaded');
    await this.waitForReactInit();
    // Additional wait for any async data loading
    await this.page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {
      // Ignore timeout - some pages may have ongoing network activity
    });
  }

  /**
   * Get the page title
   */
  async getTitle(): Promise<string> {
    return await this.page.title();
  }

  /**
   * Get navigation link
   */
  getNavLink(text: string): Locator {
    return this.page.getByRole('link', { name: text });
  }

  /**
   * Navigate to a page via the navigation menu
   */
  async navigateTo(linkText: string) {
    await this.getNavLink(linkText).click();
    await this.waitForPageReady();
  }

  /**
   * Check if an element is visible
   */
  async isVisible(locator: Locator): Promise<boolean> {
    try {
      await locator.waitFor({ state: 'visible', timeout: 1000 });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Wait for a toast/notification message
   */
  async waitForToast(message?: string) {
    const toastLocator = message
      ? this.page.locator('.toast, .notification, .alert').filter({ hasText: message })
      : this.page.locator('.toast, .notification, .alert').first();

    await toastLocator.waitFor({ state: 'visible', timeout: 5000 });
  }

  /**
   * Get callout message (error, warning, info)
   */
  getCallout(type?: 'danger' | 'warning' | 'info'): Locator {
    if (type) {
      return this.page.locator(`.callout.callout-${type}`);
    }
    return this.page.locator('.callout').first();
  }

  /**
   * Take a screenshot with a descriptive name
   */
  async takeScreenshot(name: string) {
    await this.page.screenshot({ path: `tests/e2e/screenshots/${name}.png`, fullPage: true });
  }
}
