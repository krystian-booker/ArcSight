import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for ArcSight E2E tests
 * See https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: './tests/e2e/tests',

  // Maximum time one test can run
  timeout: 30 * 1000,

  // Test execution settings
  fullyParallel: false, // Run tests serially to avoid Flask database conflicts
  forbidOnly: !!process.env.CI, // Fail if test.only in CI
  retries: process.env.CI ? 2 : 0, // Retry flaky tests in CI
  workers: 1, // Single worker to avoid Flask port conflicts

  // Reporter configuration
  reporter: [
    ['html', { outputFolder: 'tests/e2e/reports/html' }],
    ['json', { outputFile: 'tests/e2e/reports/results.json' }],
    ['list'], // Console output
  ],

  // Shared settings for all projects
  use: {
    // Base URL for the Flask application
    baseURL: 'http://localhost:8080',

    // Capture screenshot on test failure
    screenshot: 'only-on-failure',

    // Capture trace for debugging
    trace: 'retain-on-failure',

    // Video recording
    video: 'retain-on-failure',

    // Navigation timeout
    navigationTimeout: 10 * 1000,

    // Action timeout
    actionTimeout: 10 * 1000,
  },

  // Global setup and teardown
  globalSetup: require.resolve('./tests/e2e/global-setup.ts'),
  globalTeardown: require.resolve('./tests/e2e/global-teardown.ts'),

  // Configure projects for different browsers
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1920, height: 1080 },
      },
    },

    // Uncomment to test in Firefox
    // {
    //   name: 'firefox',
    //   use: {
    //     ...devices['Desktop Firefox'],
    //     viewport: { width: 1920, height: 1080 },
    //   },
    // },

    // Uncomment to test in WebKit (Safari)
    // {
    //   name: 'webkit',
    //   use: {
    //     ...devices['Desktop Safari'],
    //     viewport: { width: 1920, height: 1080 },
    //   },
    // },
  ],

  // Output folder for test artifacts
  outputDir: 'tests/e2e/test-results',

  // Snapshot configuration for visual regression
  expect: {
    toHaveScreenshot: {
      // Maximum pixel difference threshold
      maxDiffPixels: 100,

      // Animation disabling
      animations: 'disabled',

      // Screenshot scale
      scale: 'css',
    },
  },

  // Web server configuration (if needed for manual testing)
  // webServer: {
  //   command: 'python run.py',
  //   url: 'http://localhost:8080',
  //   timeout: 30 * 1000,
  //   reuseExistingServer: !process.env.CI,
  // },
});
