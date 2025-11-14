import { test, expect } from '@playwright/test';

test.describe('Cameras Page', () => {
  test.beforeEach(async ({ page, request }) => {
    const resetResponse = await request.post('/test/reset-database');
    expect(resetResponse.ok()).toBeTruthy();

    await page.goto('/cameras');
    await expect(page.getByRole('heading', { level: 1, name: 'Cameras' })).toBeVisible();
  });

  test('should load cameras page', async ({ page }) => {
    // Check page title
    await expect(page.locator('h1')).toContainText('Cameras');

    // Check for Add Camera button
    await expect(page.getByRole('button', { name: 'Add Camera' })).toBeVisible();
  });

  test('should show empty state when no cameras configured', async ({ page }) => {
    // Check for empty state message
    await expect(page.getByText('No cameras configured', { exact: true })).toBeVisible();
    await expect(page.getByText('Click "Add Camera" to get started', { exact: true })).toBeVisible();
  });

  test('should open add camera modal', async ({ page }) => {
    // Click Add Camera button (the main one that opens the modal)
    await page.getByRole('button', { name: 'Add Camera' }).first().click();

    // Modal should appear
    await expect(page.getByRole('heading', { level: 2, name: 'Add Camera' })).toBeVisible();
    await expect(page.getByText('Configure a new camera device', { exact: true })).toBeVisible();

    // Check form fields exist
    await expect(page.locator('#camera-name')).toBeVisible();
    await expect(page.locator('#camera-type')).toBeVisible();
  });

  test('should close add camera modal on cancel', async ({ page }) => {
    // Open modal
    await page.getByRole('button', { name: 'Add Camera' }).first().click();
    await expect(page.getByRole('heading', { level: 2, name: 'Add Camera' })).toBeVisible();

    // Click Cancel
    await page.getByRole('button', { name: 'Cancel' }).click();

    // Modal should close
    await expect(page.getByRole('heading', { level: 2, name: 'Add Camera' })).not.toBeVisible();
  });

  test('should discover mock USB cameras', async ({ page }) => {
    // Open add camera modal
    await page.getByRole('button', { name: 'Add Camera' }).first().click();

    // Select camera type
    await page.locator('#camera-type').click();
    await page.locator('[role="option"]:has-text("USB Camera")').click();

    // Click Discover button
    await page.getByRole('button', { name: 'Discover' }).click();

    // Wait for discovery to complete
    await page.waitForTimeout(1000);

    // Check if mock devices appeared (should show select dropdown)
    const selectTrigger = page.locator('button[role="combobox"]:has-text("Select device")');
    await expect(selectTrigger).toBeVisible();

    await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();
  });

  test('should add a USB camera successfully', async ({ page }) => {
    const cameraName = 'Test USB Camera';

    // Open modal
    await page.getByRole('button', { name: 'Add Camera' }).first().click();

    // Fill in camera name
    await page.locator('#camera-name').fill(cameraName);

    // Select camera type
    await page.locator('#camera-type').click();
    await page.locator('[role="option"]:has-text("USB Camera")').click();

    // Discover devices
    await page.getByRole('button', { name: 'Discover' }).click();
    await page.waitForTimeout(1000);

    // Select first mock device
    await page.locator('button[role="combobox"]:has-text("Select device")').click();
    await page.locator('[role="option"]:has-text("Mock USB Camera 0")').first().click();

    // Add camera (click submit button inside modal)
    await page.getByRole('button', { name: 'Add Camera' }).last().click();

    // Wait for success toast and modal to close
    await page.waitForTimeout(1500);

    // Modal should close
    await expect(page.getByRole('heading', { level: 2, name: 'Add Camera' })).not.toBeVisible();

    // Camera should appear in table
    const cameraRow = page.locator('tbody tr').filter({ hasText: cameraName });
    await expect(cameraRow).toBeVisible();
    await expect(cameraRow).toContainText('USB');
  });

  test('should show camera in table after adding', async ({ page }) => {
    const cameraName = 'Front Camera';

    // Add a camera first
    await page.getByRole('button', { name: 'Add Camera' }).first().click();
    await page.locator('#camera-name').fill(cameraName);
    await page.locator('#camera-type').click();
    await page.locator('[role="option"]:has-text("GenICam Camera")').click();
    await page.getByRole('button', { name: 'Discover' }).click();
    await page.waitForTimeout(1000);
    await page.locator('button[role="combobox"]:has-text("Select device")').click();
    await page.locator('[role="option"]:has-text("Mock GenICam Camera")').first().click();
    await page.getByRole('button', { name: 'Add Camera' }).last().click();
    await page.waitForTimeout(1500);

    // Check table has correct columns
    await expect(page.locator('th:has-text("Name")')).toBeVisible();
    await expect(page.locator('th:has-text("Type")')).toBeVisible();
    await expect(page.locator('th:has-text("Identifier")')).toBeVisible();
    await expect(page.locator('th:has-text("Status")')).toBeVisible();
    await expect(page.locator('th:has-text("Actions")')).toBeVisible();

    // Check camera appears in table
    await expect(page.locator(`td:has-text("${cameraName}")`)).toBeVisible();
  });

  test('should edit camera name', async ({ page }) => {
    const originalName = 'Original Camera';
    const newName = 'Updated Camera Name';

    // Add a camera first
    await page.getByRole('button', { name: 'Add Camera' }).first().click();
    await page.locator('#camera-name').fill(originalName);
    await page.locator('#camera-type').click();
    await page.locator('[role="option"]:has-text("USB Camera")').click();
    await page.getByRole('button', { name: 'Discover' }).click();
    await page.waitForTimeout(1000);
    await page.locator('button[role="combobox"]:has-text("Select device")').click();
    await page.locator('[role="option"]:has-text("Mock USB Camera 0")').first().click();
    await page.getByRole('button', { name: 'Add Camera' }).last().click();
    await page.waitForTimeout(1500);

    // Click edit button (look for Edit2 icon button in the row)
    await page.locator(`tr:has-text("${originalName}")`).getByRole('button', { name: 'Edit camera' }).click();

    // Edit modal should open
    await expect(page.getByRole('heading', { level: 2, name: 'Edit Camera' })).toBeVisible();
    await expect(page.getByText('Change camera name', { exact: true })).toBeVisible();

    // Clear and enter new name
    await page.locator('#edit-camera-name').clear();
    await page.locator('#edit-camera-name').fill(newName);

    // Save changes
    await page.getByRole('button', { name: 'Save Changes' }).click();
    await page.waitForTimeout(1000);

    // Check updated name appears
    await expect(page.locator(`td:has-text("${newName}")`)).toBeVisible();
    await expect(page.locator(`td:has-text("${originalName}")`)).not.toBeVisible();
  });

  test('should show delete confirmation dialog', async ({ page }) => {
    const cameraName = 'Camera to Delete';

    // Add a camera first
    await page.getByRole('button', { name: 'Add Camera' }).first().click();
    await page.locator('#camera-name').fill(cameraName);
    await page.locator('#camera-type').click();
    await page.locator('[role="option"]:has-text("OAK-D Camera")').click();
    await page.getByRole('button', { name: 'Discover' }).click();
    await page.waitForTimeout(1000);
    await page.locator('button[role="combobox"]:has-text("Select device")').click();
    await page.locator('[role="option"]:has-text("Mock OAK-D Camera")').first().click();
    await page.getByRole('button', { name: 'Add Camera' }).last().click();
    await page.waitForTimeout(1500);

    // Click delete button (second button in actions column)
    await page.locator(`tr:has-text("${cameraName}")`).getByRole('button', { name: 'Delete camera' }).click();

    // Delete confirmation should appear
    await expect(page.getByRole('heading', { level: 2, name: 'Delete Camera' })).toBeVisible();
    await expect(page.getByText(`Are you sure you want to delete "${cameraName}"`)).toBeVisible();
    await expect(page.getByText('cannot be undone')).toBeVisible();

    // Cancel deletion
    await page.getByRole('button', { name: 'Cancel' }).click();

    // Camera should still be visible
    await expect(page.locator(`td:has-text("${cameraName}")`)).toBeVisible();
  });

  test('should delete camera successfully', async ({ page }) => {
    const cameraName = 'Camera to Remove';

    // Add a camera first
    await page.getByRole('button', { name: 'Add Camera' }).first().click();
    await page.locator('#camera-name').fill(cameraName);
    await page.locator('#camera-type').click();
    await page.locator('[role="option"]:has-text("RealSense")').click();
    await page.getByRole('button', { name: 'Discover' }).click();
    await page.waitForTimeout(1000);
    await page.locator('button[role="combobox"]:has-text("Select device")').click();
    await page.locator('[role="option"]:has-text("Mock RealSense Camera")').first().click();
    await page.getByRole('button', { name: 'Add Camera' }).last().click();
    await page.waitForTimeout(1500);

    // Confirm camera was added
    await expect(page.locator(`td:has-text("${cameraName}")`)).toBeVisible();

    // Click delete button
    await page.locator(`tr:has-text("${cameraName}")`).getByRole('button', { name: 'Delete camera' }).click();

    // Confirm deletion
    await page.getByRole('button', { name: 'Delete Camera' }).click();
    await page.waitForTimeout(1000);

    // Camera should be removed
    await expect(page.locator(`td:has-text("${cameraName}")`)).not.toBeVisible();

    // Should show empty state
    await expect(page.getByText('No cameras configured', { exact: true })).toBeVisible();
  });

  test('should show validation error when adding camera without name', async ({ page }) => {
    // Open modal
    await page.getByRole('button', { name: 'Add Camera' }).first().click();

    // Select type and device but leave name empty
    await page.locator('#camera-type').click();
    await page.locator('[role="option"]:has-text("USB Camera")').click();
    await page.getByRole('button', { name: 'Discover' }).click();
    await page.waitForTimeout(1000);
    await page.locator('button[role="combobox"]:has-text("Select device")').click();
    await page.locator('[role="option"]:has-text("Mock USB Camera 0")').first().click();

    // Try to add without name
    await page.getByRole('button', { name: 'Add Camera' }).last().click();
    await page.waitForTimeout(500);

    // Should show error toast (modal stays open)
    await expect(page.getByText('Configure a new camera device', { exact: true })).toBeVisible();

    await page.getByRole('button', { name: 'Cancel' }).click();
  });

  test('should require device discovery before adding camera', async ({ page }) => {
    // Open modal
    await page.getByRole('button', { name: 'Add Camera' }).first().click();

    // Fill name and select type but don't discover
    await page.locator('#camera-name').fill('Test Camera');
    await page.locator('#camera-type').click();
    await page.locator('[role="option"]:has-text("USB Camera")').click();

    // Try to add without discovering/selecting device
    await page.getByRole('button', { name: 'Add Camera' }).last().click();
    await page.waitForTimeout(500);

    // Modal should stay open (validation error)
    await expect(page.getByText('Configure a new camera device', { exact: true })).toBeVisible();

    await page.getByRole('button', { name: 'Cancel' }).click();
  });

  test('should handle all camera types', async ({ page }) => {
    const cameraTypes = [
      { type: 'USB Camera', mockDevice: 'Mock USB Camera 0' },
      { type: 'GenICam Camera', mockDevice: 'Mock GenICam Camera' },
      { type: 'OAK-D Camera', mockDevice: 'Mock OAK-D Camera' },
      { type: 'RealSense', mockDevice: 'Mock RealSense Camera' },
    ];

    for (const { type, mockDevice } of cameraTypes) {
      // Open modal
      await page.getByRole('button', { name: 'Add Camera' }).first().click();

      // Select camera type
      await page.locator('#camera-type').click();
      await page.locator(`[role="option"]:has-text("${type}")`).click();

      // Discover should work
      await page.getByRole('button', { name: 'Discover' }).click();
      await page.waitForTimeout(1000);

      // Mock device should be available
      await page.locator('button[role="combobox"]:has-text("Select device")').click();
      await expect(page.locator(`[role="option"]:has-text("${mockDevice}")`).first()).toBeVisible();

      // Close modal
      await page.keyboard.press('Escape');
      await page.getByRole('button', { name: 'Cancel' }).click();
      await page.waitForTimeout(200);
    }
  });

  test('should persist cameras across page reload', async ({ page }) => {
    const cameraName = 'Persistent Camera';

    // Add camera
    await page.getByRole('button', { name: 'Add Camera' }).first().click();
    await page.locator('#camera-name').fill(cameraName);
    await page.locator('#camera-type').click();
    await page.locator('[role="option"]:has-text("USB Camera")').click();
    await page.getByRole('button', { name: 'Discover' }).click();
    await page.waitForTimeout(1000);
    await page.locator('button[role="combobox"]:has-text("Select device")').click();
    await page.locator('[role="option"]:has-text("Mock USB Camera 0")').first().click();
    await page.getByRole('button', { name: 'Add Camera' }).last().click();
    await page.waitForTimeout(1500);

    // Reload page
    await page.reload();
    await expect(page.getByRole('heading', { level: 1, name: 'Cameras' })).toBeVisible();
    await page.waitForTimeout(1000);

    // Camera should still be there
    await expect(page.locator(`td:has-text("${cameraName}")`)).toBeVisible();
  });
});
