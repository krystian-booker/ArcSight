import { FullConfig } from '@playwright/test';
import { spawn, ChildProcess } from 'child_process';
import path from 'path';
import { waitForServer } from './utils/wait-for-server';
import { execSync } from 'child_process';

let flaskProcess: ChildProcess | null = null;
let viteProcess: ChildProcess | null = null;

/**
 * Global setup runs once before all tests
 * Builds React app and starts Flask server with test configuration
 */
async function globalSetup(config: FullConfig) {
  const projectRoot = path.resolve(__dirname, '../..');
  const frontendDir = path.join(projectRoot, 'frontend');

  console.log('Building React app for E2E tests...');
  try {
    // Build React app for production
    execSync('npm run build', {
      cwd: frontendDir,
      stdio: 'inherit',
      shell: true,
    });
    console.log('React app built successfully');
  } catch (error) {
    console.error('Failed to build React app:', error);
    throw error;
  }

  console.log('Starting Flask server for E2E tests...');

  const flaskApp = path.join(projectRoot, 'run.py');

  // Environment variables for test configuration
  const env = {
    ...process.env,
    FLASK_ENV: 'testing',
    FLASK_DEBUG: '0',
    TESTING: 'true',
    // Use a separate test database
    DATABASE_PATH: path.join(projectRoot, 'tests', 'e2e', 'test_data.db'),
    // Disable metrics to reduce noise
    METRICS_ENABLED: 'false',
    // Enable test mock endpoints
    E2E_TESTING: 'true',
    // Don't auto-start Vite since we're using the production build
    VITE_AUTO_START: 'false',
  };

  // Start Flask process
  flaskProcess = spawn('python', [flaskApp], {
    env,
    cwd: projectRoot,
    stdio: 'pipe',
    shell: true,
  });

  // Log Flask output for debugging
  flaskProcess.stdout?.on('data', (data) => {
    console.log(`[Flask] ${data.toString().trim()}`);
  });

  flaskProcess.stderr?.on('data', (data) => {
    console.error(`[Flask Error] ${data.toString().trim()}`);
  });

  flaskProcess.on('error', (error) => {
    console.error('Failed to start Flask server:', error);
  });

  flaskProcess.on('exit', (code, signal) => {
    if (code !== 0 && code !== null) {
      console.error(`Flask server exited with code ${code}, signal ${signal}`);
    }
  });

  // Wait for server to be ready
  const baseURL = config.projects[0].use?.baseURL || 'http://localhost:8080';
  try {
    await waitForServer(baseURL, 30000);
    console.log('Flask server is ready for testing');
  } catch (error) {
    console.error('Failed to start Flask server:', error);
    if (flaskProcess) {
      flaskProcess.kill();
    }
    throw error;
  }

  // Store process reference for teardown
  (global as any).__FLASK_PROCESS__ = flaskProcess;
  (global as any).__VITE_PROCESS__ = viteProcess;
}

export default globalSetup;
