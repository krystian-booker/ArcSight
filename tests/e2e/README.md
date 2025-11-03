# ArcSight E2E Tests

End-to-end tests for ArcSight computer vision application using Playwright with TypeScript.

## Overview

This test suite provides comprehensive E2E testing covering:
- **Camera Management**: Discovery, registration, configuration, and deletion
- **Pipeline Workflows**: CRUD operations for vision pipelines
- **Visual Regression**: Screenshot comparison to detect UI changes
- **Mock Hardware**: Simulated camera devices and video feeds

**Note**: Tests run against the production build of the React frontend. The global setup automatically builds the React app before starting the Flask server.

## Prerequisites

- **Node.js** >= 18.0.0
- **Python 3.11** with ArcSight dependencies installed
- **Conda environment** activated (recommended)

## Installation

```bash
# Install Node.js dependencies
npm install

# Install Playwright browsers (only Chromium by default)
npm run playwright:install

# Or install all browsers
npx playwright install
```

## Running Tests

### Run All Tests
```bash
npm run test:e2e
```

### Run Tests with Browser UI (Headed Mode)
```bash
npm run test:e2e:headed
```

### Run Tests in Debug Mode
```bash
npm run test:e2e:debug
```

### Run Tests with Playwright UI Mode
```bash
npm run test:e2e:ui
```

### Run Specific Test File
```bash
npx playwright test tests/e2e/tests/camera-workflows.spec.ts
```

### Run Tests Matching a Pattern
```bash
npx playwright test -g "should add a camera"
```

### View Test Report
```bash
npm run test:e2e:report
```

## Test Structure

```
tests/e2e/
├── README.md                          # This file
├── global-setup.ts                    # Flask server startup
├── global-teardown.ts                 # Flask server shutdown
├── fixtures/
│   └── database-fixtures.ts           # Test data helpers
├── pages/
│   ├── BasePage.ts                    # Common page functionality
│   ├── DashboardPage.ts               # Dashboard page object
│   └── CamerasPage.ts                 # Cameras page object
├── tests/
│   ├── camera-workflows.spec.ts       # Camera management tests
│   ├── pipeline-workflows.spec.ts     # Pipeline CRUD tests
│   └── visual-regression.spec.ts      # Visual regression tests
├── utils/
│   ├── wait-for-server.ts             # Server readiness utilities
│   └── cleanup.ts                     # Cleanup and retry utilities
└── reports/                           # Test reports (gitignored)
```

## Writing Tests

### Basic Test Structure

```typescript
import { test, expect } from '@playwright/test';
import { CamerasPage } from '../pages/CamerasPage';

test.describe('My Test Suite', () => {
  let camerasPage: CamerasPage;

  test.beforeEach(async ({ page }) => {
    camerasPage = new CamerasPage(page);

    // Reset database before each test
    await page.request.post('/test/reset-database');

    // Navigate to page
    await camerasPage.navigate();
  });

  test('should do something', async () => {
    // Test implementation
    await camerasPage.addCamera({
      name: 'Test Camera',
      type: 'USB',
      identifier: 'test_0',
    });

    // Assertions
    const cameras = await camerasPage.getCameraNames();
    expect(cameras).toContain('Test Camera');
  });
});
```

### Using Database Fixtures

```typescript
import { resetDatabase, seedTestData, CAMERA_FIXTURES } from '../fixtures/database-fixtures';

test('example with fixtures', async ({ page }) => {
  // Reset database
  await resetDatabase(page.request);

  // Seed with default test data
  await seedTestData(page.request);

  // Or use predefined fixtures
  await createCamera(page.request, CAMERA_FIXTURES.USB_DEFAULT);
});
```

### Page Object Model Pattern

Always use Page Object Models (POMs) for UI interactions:

```typescript
// Good ✓
await camerasPage.addCamera({ name: 'Cam', type: 'USB', identifier: 'test' });

// Bad ✗
await page.click('button[text="Add Camera"]');
await page.fill('input[name="name"]', 'Cam');
```

## Visual Regression Testing

### Capturing Baselines

First time running visual tests, capture baseline screenshots:

```bash
npm run test:e2e:update-snapshots
```

This creates baseline images in `tests/e2e/tests/*.spec.ts-snapshots/`.

### Updating Baselines

When UI changes are intentional, update baselines:

```bash
npm run test:e2e:update-snapshots
```

### Visual Test Example

```typescript
test('dashboard layout should match', async ({ page }) => {
  await page.goto('/');

  // Compare full page screenshot
  await expect(page).toHaveScreenshot('dashboard.png', {
    fullPage: true,
    animations: 'disabled',
  });
});
```

## Mock Camera Endpoints

E2E tests use mock endpoints (only available when `E2E_TESTING=true`):

- `POST /test/reset-database` - Clear all test data
- `POST /test/seed-test-data` - Add default cameras and pipelines
- `GET /test/mock-cameras` - List mock camera devices
- `GET /test/mock-video-feed/<id>` - Stream test video pattern
- `GET /test/health` - Server health check

## Test Environment

Tests run with these environment variables:

```bash
FLASK_ENV=testing
FLASK_DEBUG=0
TESTING=true
DATABASE_PATH=tests/e2e/test_data.db
METRICS_ENABLED=false
E2E_TESTING=true
```

The Flask server:
- Starts automatically before tests via `global-setup.ts`
- Stops automatically after tests via `global-teardown.ts`
- Uses an isolated test database
- Disables camera threads and metrics

## Debugging Tests

### Run with Playwright Inspector

```bash
npm run test:e2e:debug
```

This opens the Playwright Inspector where you can:
- Step through test actions
- Inspect element selectors
- View browser console
- Record new test actions

### View Trace Files

When tests fail, traces are saved to `tests/e2e/test-results/`. View them:

```bash
npx playwright show-trace tests/e2e/test-results/trace.zip
```

### Add Debug Screenshots

```typescript
await page.screenshot({ path: 'debug-screenshot.png', fullPage: true });
```

### Use Page Pause

```typescript
await page.pause(); // Opens Playwright Inspector
```

## Common Issues

### Tests Timing Out

If tests timeout waiting for Flask:
1. Check Flask logs in test output
2. Verify Python environment is correct
3. Increase timeout in `global-setup.ts`

### Visual Regression Failures

If screenshots don't match:
1. Review diff images in test results
2. If changes are intentional: `npm run test:e2e:update-snapshots`
3. Check for animation or loading state issues

### Flask Server Won't Stop

If Flask process hangs:
```bash
# Windows
taskkill /F /IM python.exe

# Linux/Mac
pkill -9 python
```

### Port Already in Use

If port 8080 is busy:
```bash
# Windows
netstat -ano | findstr :8080
taskkill /PID <PID> /F

# Linux/Mac
lsof -ti:8080 | xargs kill -9
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          npm install
          pip install -r requirements.txt
          npx playwright install --with-deps chromium

      - name: Run E2E tests
        run: npm run test:e2e

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: playwright-report
          path: tests/e2e/reports/
```

## Best Practices

1. **Always reset database** in `beforeEach` for test isolation
2. **Use Page Object Models** for maintainable tests
3. **Wait for React** initialization with `waitForPageReady()`
4. **Add descriptive test names** that explain what is being tested
5. **Keep tests focused** - one concept per test
6. **Use data-testid** attributes for stable selectors (if needed)
7. **Avoid hard-coded waits** - use `waitFor()` instead
8. **Take screenshots** on complex UI state for debugging

## Resources

- [Playwright Documentation](https://playwright.dev/docs/intro)
- [Playwright Test API](https://playwright.dev/docs/api/class-test)
- [Best Practices](https://playwright.dev/docs/best-practices)
- [Debugging Guide](https://playwright.dev/docs/debug)
