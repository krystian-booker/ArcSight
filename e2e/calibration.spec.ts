import { test, expect } from '@playwright/test';

test.describe('Calibration Page', () => {
  test.beforeEach(async ({ page }) => {
    // Add a mock camera first for calibration tests
    await page.goto('/cameras');
    await page.waitForSelector('h1:has-text("Cameras")');

    // Check if we already have a camera
    const hasCameras = await page.locator('td').count() > 0;

    if (!hasCameras) {
      // Add a mock USB camera
      await page.locator('button:has-text("Add Camera")').first().click();
      await page.locator('#camera-name').fill('Test Calibration Camera');
      await page.locator('#camera-type').click();
      await page.locator('[role="option"]:has-text("USB Camera")').click();
      await page.locator('button:has-text("Discover")').click();
      await page.waitForTimeout(1000);
      await page.locator('button[role="combobox"]:has-text("Select device")').click();
      await page.locator('[role="option"]:has-text("Mock USB Camera 0")').first().click();
      // Click the submit button inside the modal (last "Add Camera" button on page)
      await page.locator('button:has-text("Add Camera")').last().click();
      await page.waitForTimeout(1500);
    }

    // Navigate to calibration page
    await page.goto('/calibration');
    await page.waitForSelector('h1:has-text("Camera Calibration")');
  });

  test('should load calibration page', async ({ page }) => {
    // Check page title
    await expect(page.locator('h1')).toContainText('Camera Calibration');

    // Check step indicator
    await expect(page.getByTestId('calibration-step-setup')).toBeVisible();
    await expect(page.getByTestId('calibration-step-capture')).toBeVisible();
    await expect(page.getByTestId('calibration-step-results')).toBeVisible();

    // Should be on setup step
    await expect(page.locator('text=Calibration Setup')).toBeVisible();
  });

  test('should have valid default pattern values', async ({ page }) => {
    // Check default values are within valid ranges
    const width = await page.locator('#width').inputValue();
    const height = await page.locator('#height').inputValue();
    const squareSize = await page.locator('#square-size').inputValue();

    // Default should be 7x5 with 25mm squares (fits on A4)
    expect(parseInt(width)).toBe(7);
    expect(parseInt(height)).toBe(5);
    expect(parseFloat(squareSize)).toBe(25);

    // Verify max hints are shown
    await expect(page.locator('text=Max 7 for 25mm squares on A4')).toBeVisible();
    await expect(page.locator('text=Max 10 for 25mm squares on A4')).toBeVisible();
  });

  test('should update max dimensions when square size changes', async ({ page }) => {
    // Change square size to 20mm
    await page.locator('#square-size').clear();
    await page.locator('#square-size').fill('20');

    // Max should update
    await expect(page.locator('text=Max 9 for 20mm squares on A4')).toBeVisible();
    await expect(page.locator('text=Max 13 for 20mm squares on A4')).toBeVisible();

    // Change to 15mm
    await page.locator('#square-size').clear();
    await page.locator('#square-size').fill('15');

    await expect(page.locator('text=Max 13 for 15mm squares on A4')).toBeVisible();
    await expect(page.locator('text=Max 18 for 15mm squares on A4')).toBeVisible();
  });

  test('should have bounded input fields', async ({ page }) => {
    // Width should have min/max
    const widthMin = await page.locator('#width').getAttribute('min');
    const widthMax = await page.locator('#width').getAttribute('max');
    expect(widthMin).toBe('3');
    expect(widthMax).toBe('7'); // For 25mm squares

    // Height should have min/max
    const heightMin = await page.locator('#height').getAttribute('min');
    const heightMax = await page.locator('#height').getAttribute('max');
    expect(heightMin).toBe('3');
    expect(heightMax).toBe('10'); // For 25mm squares

    // Square size should have min/max
    const sizeMin = await page.locator('#square-size').getAttribute('min');
    const sizeMax = await page.locator('#square-size').getAttribute('max');
    expect(sizeMin).toBe('5');
    expect(sizeMax).toBe('50');
  });

  test('should select camera from dropdown', async ({ page }) => {
    // Camera dropdown should exist
    await expect(page.locator('#camera')).toBeVisible();

    // Select a camera
    await page.locator('#camera').click();
    await page.locator('[role="option"]:has-text("Test Calibration Camera")').click();

    // Start button should become enabled
    await expect(page.locator('button:has-text("Start Calibration")')).toBeEnabled();
  });

  test('should toggle between chessboard and charuco patterns', async ({ page }) => {
    // Default should be ChAruco
    await expect(page.locator('#pattern-type')).toContainText('ChAruco');

    // Marker dict should be visible
    await expect(page.locator('#marker-dict')).toBeVisible();

    // Switch to Chessboard
    await page.locator('#pattern-type').click();
    await page.locator('[role="option"]:has-text("Chessboard")').click();

    // Marker dict should disappear
    await expect(page.locator('#marker-dict')).not.toBeVisible();

    // Switch back to ChAruco
    await page.locator('#pattern-type').click();
    await page.locator('[role="option"]:has-text("ChAruco")').click();

    // Marker dict should appear again
    await expect(page.locator('#marker-dict')).toBeVisible();
  });

  test('should show pattern download button', async ({ page }) => {
    await expect(page.locator('button:has-text("Download Pattern")')).toBeVisible();
  });

  test('should require camera selection before starting calibration', async ({ page }) => {
    // Start button should be disabled without camera
    await expect(page.locator('button:has-text("Start Calibration")')).toBeDisabled();

    // Select camera
    await page.locator('#camera').click();
    await page.locator('[role="option"]').first().click();

    // Start button should be enabled
    await expect(page.locator('button:has-text("Start Calibration")')).toBeEnabled();
  });

  test('should start calibration and move to capture step', async ({ page }) => {
    // Select camera
    await page.locator('#camera').click();
    await page.locator('[role="option"]').first().click();

    // Start calibration
    await page.locator('button:has-text("Start Calibration")').click();
    await page.waitForTimeout(1000);

    // Should move to capture step
    await expect(page.getByRole('heading', { name: 'Calibration Feed' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Capture Frames' })).toBeVisible();
    await expect(page.getByText('Frames captured', { exact: true })).toBeVisible();

    // Should show 0 frames initially
    await expect(page.getByTestId('captured-frames-count')).toHaveText('0');
  });

  test('should show capture frame button in capture step', async ({ page }) => {
    // Select camera and start
    await page.locator('#camera').click();
    await page.locator('[role="option"]').first().click();
    await page.locator('button:has-text("Start Calibration")').click();
    await page.waitForTimeout(1000);

    // Capture button should be visible
    await expect(page.locator('button:has-text("Capture Frame")')).toBeVisible();

    // Calculate button should be visible but disabled
    await expect(page.locator('button:has-text("Calculate Intrinsics")')).toBeVisible();
    await expect(page.locator('button:has-text("Calculate Intrinsics")')).toBeDisabled();
  });

  test('should require minimum 5 frames before calculating', async ({ page }) => {
    // Select camera and start
    await page.locator('#camera').click();
    await page.locator('[role="option"]').first().click();
    await page.locator('button:has-text("Start Calibration")').click();
    await page.waitForTimeout(1000);

    // Should show message about capturing more frames
    await expect(page.locator('text=Capture 5 more frames to calculate')).toBeVisible();

    // Calculate button should be disabled
    await expect(page.locator('button:has-text("Calculate Intrinsics")')).toBeDisabled();
  });

  test('should have all marker dictionary options for charuco', async ({ page }) => {
    // Switch to ChAruco
    await page.locator('#pattern-type').click();
    await page.locator('[role="option"]:has-text("ChAruco")').click();

    // Open marker dict dropdown
    await page.locator('#marker-dict').click();

    // Should have all 4 options
    await expect(page.locator('[role="option"]:has-text("4x4 (50)")')).toBeVisible();
    await expect(page.locator('[role="option"]:has-text("5x5 (50)")')).toBeVisible();
    await expect(page.locator('[role="option"]:has-text("6x6 (250)")')).toBeVisible();
    await expect(page.locator('[role="option"]:has-text("7x7 (1000)")')).toBeVisible();
  });

  test('should show validation hints for pattern dimensions', async ({ page }) => {
    // Should show helpful hints
    await expect(page.locator('text=Max 7 for 25mm squares on A4')).toBeVisible();
    await expect(page.locator('text=Max 10 for 25mm squares on A4')).toBeVisible();
    await expect(page.locator('text=5mm - 50mm (affects max board size)')).toBeVisible();
  });

  test('should persist pattern settings when navigating away and back', async ({ page }) => {
    // Change pattern settings
    await page.locator('#width').clear();
    await page.locator('#width').fill('5');
    await page.locator('#height').clear();
    await page.locator('#height').fill('4');
    await page.locator('#square-size').clear();
    await page.locator('#square-size').fill('20');

    // Navigate away
    await page.goto('/cameras');
    await page.waitForTimeout(500);

    // Navigate back
    await page.goto('/calibration');
    await page.waitForSelector('h1:has-text("Camera Calibration")');

    // Settings should persist
    await expect(page.locator('#width')).toHaveValue('5');
    await expect(page.locator('#height')).toHaveValue('4');
    await expect(page.locator('#square-size')).toHaveValue('20');
  });

  test('should display step indicator correctly', async ({ page }) => {
    // Step 1 should be highlighted
    const step1 = page.getByTestId('calibration-step-setup');
    await expect(step1).toHaveAttribute('data-active', 'true');

    // Select camera and start
    await page.locator('#camera').click();
    await page.locator('[role="option"]').first().click();
    await page.locator('button:has-text("Start Calibration")').click();
    await page.waitForTimeout(1000);

    // Step 2 should be highlighted
    const step2 = page.getByTestId('calibration-step-capture');
    await expect(step2).toHaveAttribute('data-active', 'true');
  });

  test('should show camera feed in capture step', async ({ page }) => {
    // Select camera and start
    await page.locator('#camera').click();
    await page.locator('[role="option"]').first().click();
    await page.locator('button:has-text("Start Calibration")').click();
    await page.waitForTimeout(1000);

    // Should show MJPEG stream component
    await expect(page.locator('img[alt="Calibration Feed"]')).toBeVisible();
  });

  test('should validate input ranges', async ({ page }) => {
    // Try to set width too low
    await page.locator('#width').clear();
    await page.locator('#width').fill('2');

    // Input should enforce min=3
    await expect(page.locator('#width')).toHaveValue('3');

    // Try to set square size too high
    await page.locator('#square-size').clear();
    await page.locator('#square-size').fill('100');

    // Input should enforce max=50
    await expect(page.locator('#square-size')).toHaveValue('50');
  });

  // ChAruco-specific tests
  test('should show marker dictionary field only for ChAruco', async ({ page }) => {
    // Default is ChAruco - marker dict should be visible
    await expect(page.locator('#marker-dict')).toBeVisible();

    // Default should be 6x6 (250)
    await expect(page.locator('#marker-dict')).toContainText('6x6 (250)');

    // Switch to Chessboard
    await page.locator('#pattern-type').click();
    await page.locator('[role="option"]:has-text("Chessboard")').click();

    // Marker dict should now be hidden
    await expect(page.locator('#marker-dict')).not.toBeVisible();
  });

  test('should persist ChAruco marker dictionary selection', async ({ page }) => {
    // Default is ChAruco - select different dictionary
    await page.locator('#marker-dict').click();
    await page.locator('[role="option"]:has-text("4x4 (50)")').click();

    // Navigate away
    await page.goto('/cameras');
    await page.waitForTimeout(500);

    // Navigate back
    await page.goto('/calibration');
    await page.waitForSelector('h1:has-text("Camera Calibration")');

    // Should still be ChAruco with 4x4
    await expect(page.locator('#pattern-type')).toContainText('ChAruco');
    await expect(page.locator('#marker-dict')).toBeVisible();
    await expect(page.locator('#marker-dict')).toContainText('4x4 (50)');
  });

  test('should apply same A4 validation to ChAruco patterns', async ({ page }) => {
    // Default is ChAruco - check validation applies
    await expect(page.locator('#pattern-type')).toContainText('ChAruco');

    // Same max dimensions should apply
    const widthMax = await page.locator('#width').getAttribute('max');
    const heightMax = await page.locator('#height').getAttribute('max');
    expect(widthMax).toBe('7'); // For 25mm squares
    expect(heightMax).toBe('10'); // For 25mm squares

    // Hints should still show
    await expect(page.locator('text=Max 7 for 25mm squares on A4')).toBeVisible();
    await expect(page.locator('text=Max 10 for 25mm squares on A4')).toBeVisible();
  });

  test('should maintain dimensions when switching between pattern types', async ({ page }) => {
    // Default is ChAruco - set custom dimensions
    await page.locator('#width').clear();
    await page.locator('#width').fill('5');
    await page.locator('#height').clear();
    await page.locator('#height').fill('4');
    await page.locator('#square-size').clear();
    await page.locator('#square-size').fill('20');

    // Switch to Chessboard
    await page.locator('#pattern-type').click();
    await page.locator('[role="option"]:has-text("Chessboard")').click();

    // Dimensions should be preserved
    expect(await page.locator('#width').inputValue()).toBe('5');
    expect(await page.locator('#height').inputValue()).toBe('4');
    expect(await page.locator('#square-size').inputValue()).toBe('20');

    // Switch back to ChAruco
    await page.locator('#pattern-type').click();
    await page.locator('[role="option"]:has-text("ChAruco")').click();

    // Dimensions should still be preserved
    expect(await page.locator('#width').inputValue()).toBe('5');
    expect(await page.locator('#height').inputValue()).toBe('4');
    expect(await page.locator('#square-size').inputValue()).toBe('20');
  });

  test('should allow ChAruco pattern download', async ({ page }) => {
    // Default is ChAruco - select a marker dictionary
    await page.locator('#marker-dict').click();
    await page.locator('[role="option"]:has-text("5x5 (50)")').click();

    // Download button should be visible and work
    await expect(page.locator('button:has-text("Download Pattern")')).toBeVisible();
    await expect(page.locator('button:has-text("Download Pattern")')).toBeEnabled();
  });

  test('should validate all marker dictionary options', async ({ page }) => {
    // Default is ChAruco - test all dictionary options
    const dictionaries = ['4x4 (50)', '5x5 (50)', '6x6 (250)', '7x7 (1000)'];

    for (const dict of dictionaries) {
      await page.locator('#marker-dict').click();
      await page.locator(`[role="option"]:has-text("${dict}")`).click();
      await expect(page.locator('#marker-dict')).toContainText(dict);
    }
  });

  test('should start calibration with ChAruco pattern', async ({ page }) => {
    // Default is ChAruco - select camera and start
    await expect(page.locator('#pattern-type')).toContainText('ChAruco');

    // Select camera
    await page.locator('#camera').click();
    await page.locator('[role="option"]').first().click();

    // Start calibration
    await page.locator('button:has-text("Start Calibration")').click();
    await page.waitForTimeout(1000);

    // Should move to capture step
    await expect(page.getByRole('heading', { name: 'Calibration Feed' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Capture Frames' })).toBeVisible();
  });

  test('should use valid ChAruco default values', async ({ page }) => {
    // Default is ChAruco - no need to switch
    await expect(page.locator('#pattern-type')).toContainText('ChAruco');

    // Check defaults - should be 7x5 with 25mm
    const width = await page.locator('#width').inputValue();
    const height = await page.locator('#height').inputValue();
    const squareSize = await page.locator('#square-size').inputValue();

    expect(parseInt(width)).toBe(7);
    expect(parseInt(height)).toBe(5);
    expect(parseFloat(squareSize)).toBe(25);

    // These dimensions should fit on A4
    // Squares = inner_corners + 1 = 8x6
    // Board size = 8*25 x 6*25 = 200mm x 150mm (fits on 210mm x 297mm A4)
  });
});
