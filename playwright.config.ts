import { defineConfig, devices } from '@playwright/test';

/**
 * See https://playwright.dev/docs/test-configuration.
 */
const resolvePythonCommand = () => {
  if (process.env.PLAYWRIGHT_PYTHON_COMMAND) {
    return process.env.PLAYWRIGHT_PYTHON_COMMAND;
  }

  const condaEnv = process.env.CONDA_DEFAULT_ENV;
  const hasConda = !!process.env.CONDA_EXE;

  if (hasConda && condaEnv === 'ArcSight') {
    return 'conda run -n ArcSight --no-capture-output python run.py';
  }

  const pythonBinary = process.env.PLAYWRIGHT_PYTHON ?? 'python';
  return `${pythonBinary} run.py`;
};

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // Run tests serially to avoid conflicts
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // Single worker to avoid conflicts with Flask backend
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:8080',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  /* Run Flask backend before starting tests */
  webServer: {
    command: resolvePythonCommand(),
    url: 'http://localhost:8080',
    reuseExistingServer: !process.env.CI,
    timeout: 60000, // Increased to 60 seconds for environment startup
    env: {
      FLASK_ENV: 'testing',
      CAMERA_THREADS_ENABLED: 'False',
      SKIP_VITE_START: 'true', // Don't try to start Vite in testing mode
    },
  },
});
