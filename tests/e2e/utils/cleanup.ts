import { APIRequestContext } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

/**
 * Cleanup utilities for E2E tests
 * Handles test artifact cleanup and resource management
 */

/**
 * Clean up test screenshots older than a specified age
 */
export async function cleanupOldScreenshots(
  screenshotsDir: string,
  maxAgeMs: number = 7 * 24 * 60 * 60 * 1000 // 7 days
): Promise<void> {
  if (!fs.existsSync(screenshotsDir)) {
    return;
  }

  const now = Date.now();
  const files = fs.readdirSync(screenshotsDir);

  for (const file of files) {
    const filePath = path.join(screenshotsDir, file);
    const stats = fs.statSync(filePath);

    if (now - stats.mtimeMs > maxAgeMs) {
      fs.unlinkSync(filePath);
      console.log(`Cleaned up old screenshot: ${file}`);
    }
  }
}

/**
 * Clean up test database file
 */
export async function cleanupTestDatabase(dbPath: string): Promise<void> {
  if (fs.existsSync(dbPath)) {
    fs.unlinkSync(dbPath);
    console.log(`Cleaned up test database: ${dbPath}`);
  }
}

/**
 * Clean up test reports older than a specified age
 */
export async function cleanupOldReports(
  reportsDir: string,
  maxAgeMs: number = 30 * 24 * 60 * 60 * 1000 // 30 days
): Promise<void> {
  if (!fs.existsSync(reportsDir)) {
    return;
  }

  const now = Date.now();
  const entries = fs.readdirSync(reportsDir, { withFileTypes: true });

  for (const entry of entries) {
    const entryPath = path.join(reportsDir, entry.name);
    const stats = fs.statSync(entryPath);

    if (now - stats.mtimeMs > maxAgeMs) {
      if (entry.isDirectory()) {
        fs.rmSync(entryPath, { recursive: true, force: true });
        console.log(`Cleaned up old report directory: ${entry.name}`);
      } else {
        fs.unlinkSync(entryPath);
        console.log(`Cleaned up old report file: ${entry.name}`);
      }
    }
  }
}

/**
 * Ensure test directories exist
 */
export function ensureTestDirectories(dirs: string[]): void {
  for (const dir of dirs) {
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  }
}

/**
 * Wait for a condition with timeout
 */
export async function waitForCondition(
  condition: () => Promise<boolean>,
  timeoutMs: number = 5000,
  intervalMs: number = 100
): Promise<boolean> {
  const startTime = Date.now();

  while (Date.now() - startTime < timeoutMs) {
    if (await condition()) {
      return true;
    }
    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }

  return false;
}

/**
 * Retry an async operation with exponential backoff
 */
export async function retryWithBackoff<T>(
  operation: () => Promise<T>,
  maxRetries: number = 3,
  initialDelayMs: number = 100
): Promise<T> {
  let lastError: Error | undefined;

  for (let i = 0; i < maxRetries; i++) {
    try {
      return await operation();
    } catch (error) {
      lastError = error as Error;
      if (i < maxRetries - 1) {
        const delay = initialDelayMs * Math.pow(2, i);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }

  throw lastError || new Error('Operation failed after retries');
}

/**
 * Check if Flask server is healthy
 */
export async function checkServerHealth(request: APIRequestContext): Promise<boolean> {
  try {
    const response = await request.get('/test/health');
    if (response.ok()) {
      const data = await response.json();
      return data.status === 'healthy';
    }
    return false;
  } catch {
    return false;
  }
}

/**
 * Wait for Flask server to be healthy
 */
export async function waitForHealthyServer(
  request: APIRequestContext,
  timeoutMs: number = 30000
): Promise<void> {
  const healthy = await waitForCondition(
    () => checkServerHealth(request),
    timeoutMs,
    500
  );

  if (!healthy) {
    throw new Error('Flask server did not become healthy within timeout');
  }
}
