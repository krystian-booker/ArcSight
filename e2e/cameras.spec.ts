import { test, expect } from '@playwright/test';

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

test.describe('Cameras Page', () => {
  test.beforeEach(async ({ page }) => {
    // Ensure a clean state before each test by deleting existing cameras
    const response = await page.request.get('/api/cameras');
    if (response.ok()) {
      const existingCameras = await response.json();
      if (Array.isArray(existingCameras)) {
        for (const camera of existingCameras) {
          if (camera?.id) {
            await page.request.post(`/cameras/delete/${camera.id}`);
          }
        }
      }
    }

    await page.goto('/cameras');
    // Wait for the page to load
    await page.waitForSelector('h1:has-text("Cameras")');
  });

  test('should load cameras page', async ({ page }) => {
    // Check page title
    await expect(page.locator('h1')).toContainText('Cameras');

    // Check for Add Camera button
    await expect(page.getByTestId('add-camera-button')).toBeVisible();
  });

  test('should show empty state when no cameras configured', async ({ page }) => {
    // Check for empty state message
    const emptyState = page.getByTestId('cameras-empty-state');
    await expect(emptyState).toBeVisible();
    await expect(emptyState.getByText('No cameras configured')).toBeVisible();
    await expect(emptyState.getByText('Click "Add Camera" to get started')).toBeVisible();
  });

  test('should open add camera modal', async ({ page }) => {
    // Click Add Camera button (the main one that opens the modal)
    const addButton = page.getByTestId('add-camera-button');
    await addButton.click();

    // Modal should appear
    const modal = page.getByRole('dialog', { name: 'Add Camera' });
    await expect(modal).toBeVisible();
    await expect(modal.getByText('Configure a new camera device')).toBeVisible();

    // Check form fields exist
    await expect(modal.locator('#camera-name')).toBeVisible();
    await expect(modal.locator('#camera-type')).toBeVisible();
  });

  test('should close add camera modal on cancel', async ({ page }) => {
    // Open modal
    const addButton = page.getByTestId('add-camera-button');
    await addButton.click();
    const modal = page.getByRole('dialog', { name: 'Add Camera' });
    await expect(modal).toBeVisible();

    // Click Cancel
    await modal.getByRole('button', { name: 'Cancel' }).click();

    // Modal should close
    await expect(modal).toBeHidden();
  });

  test('should discover mock USB cameras', async ({ page }) => {
    // Open add camera modal
    const addButton = page.getByTestId('add-camera-button');
    await addButton.click();
    const modal = page.getByRole('dialog', { name: 'Add Camera' });

    // Select camera type
    await modal.locator('#camera-type').click();
    await page.getByRole('option', { name: 'USB Camera' }).click();

    // Click Discover button
    await modal.getByRole('button', { name: 'Discover' }).click();

    // Wait for discovery to complete
    await page.waitForTimeout(1000);

    // Check if mock devices appeared (should show select dropdown)
    const selectTrigger = modal.locator('button[role="combobox"]:has-text("Select device")');
    await expect(selectTrigger).toBeVisible();
  });

  test('should add a USB camera successfully', async ({ page }) => {
    const cameraName = 'Test USB Camera';

    // Open modal
    const addButton = page.getByTestId('add-camera-button');
    await addButton.click();
    const modal = page.getByRole('dialog', { name: 'Add Camera' });

    // Fill in camera name
    await modal.locator('#camera-name').fill(cameraName);

    // Select camera type
    await modal.locator('#camera-type').click();
    await page.getByRole('option', { name: 'USB Camera' }).click();

    // Discover devices
    await modal.getByRole('button', { name: 'Discover' }).click();
    await page.waitForTimeout(1000);

    // Select first mock device
    await modal.locator('button[role="combobox"]:has-text("Select device")').click();
    await page.getByRole('option', { name: 'Mock USB Camera 0' }).first().click();

    // Add camera (click submit button inside modal)
    await modal.getByRole('button', { name: 'Add Camera' }).click();

    // Wait for success toast and modal to close
    await page.waitForTimeout(1500);

    // Modal should close
    await expect(modal).toBeHidden();

    // Camera should appear in table
    const cameraRow = page.getByRole('row', { name: new RegExp(escapeRegExp(cameraName), 'i') });
    await expect(cameraRow).toBeVisible();
    await expect(cameraRow.getByRole('cell', { name: cameraName, exact: true })).toBeVisible();
    await expect(cameraRow).toContainText('USB');
  });

  test('should show camera in table after adding', async ({ page }) => {
    const cameraName = 'Front Camera';

    // Add a camera first
    const addButton = page.getByTestId('add-camera-button');
    await addButton.click();
    const modal = page.getByRole('dialog', { name: 'Add Camera' });
    await modal.locator('#camera-name').fill(cameraName);
    await modal.locator('#camera-type').click();
    await page.getByRole('option', { name: 'GenICam Camera' }).click();
    await modal.getByRole('button', { name: 'Discover' }).click();
    await page.waitForTimeout(1000);
    await modal.locator('button[role="combobox"]:has-text("Select device")').click();
    await page.getByRole('option', { name: 'Mock GenICam Camera' }).first().click();
    await modal.getByRole('button', { name: 'Add Camera' }).click();
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
    const addButton = page.getByTestId('add-camera-button');
    await addButton.click();
    const addModal = page.getByRole('dialog', { name: 'Add Camera' });
    await addModal.locator('#camera-name').fill(originalName);
    await addModal.locator('#camera-type').click();
    await page.getByRole('option', { name: 'USB Camera' }).click();
    await addModal.getByRole('button', { name: 'Discover' }).click();
    await page.waitForTimeout(1000);
    await addModal.locator('button[role="combobox"]:has-text("Select device")').click();
    await page.getByRole('option', { name: 'Mock USB Camera 0' }).first().click();
    await addModal.getByRole('button', { name: 'Add Camera' }).click();
    await page.waitForTimeout(1500);

    // Click edit button (look for Edit2 icon button in the row)
    await page.getByRole('button', { name: `Edit camera ${originalName}` }).click();

    // Edit modal should open
    const editModal = page.getByRole('dialog', { name: 'Edit Camera' });
    await expect(editModal).toBeVisible();
    await expect(editModal.getByText('Change camera name')).toBeVisible();

    // Clear and enter new name
    await editModal.locator('#edit-camera-name').clear();
    await editModal.locator('#edit-camera-name').fill(newName);

    // Save changes
    await editModal.getByRole('button', { name: 'Save Changes' }).click();
    await page.waitForTimeout(1000);

    // Check updated name appears
    await expect(page.locator(`td:has-text("${newName}")`)).toBeVisible();
    await expect(page.locator(`td:has-text("${originalName}")`)).not.toBeVisible();
  });

  test('should show delete confirmation dialog', async ({ page }) => {
    const cameraName = 'Camera to Delete';

    // Add a camera first
    const addButton = page.getByTestId('add-camera-button');
    await addButton.click();
    const addModal = page.getByRole('dialog', { name: 'Add Camera' });
    await addModal.locator('#camera-name').fill(cameraName);
    await addModal.locator('#camera-type').click();
    await page.getByRole('option', { name: 'OAK-D Camera' }).click();
    await addModal.getByRole('button', { name: 'Discover' }).click();
    await page.waitForTimeout(1000);
    await addModal.locator('button[role="combobox"]:has-text("Select device")').click();
    await page.getByRole('option', { name: 'Mock OAK-D Camera' }).first().click();
    await addModal.getByRole('button', { name: 'Add Camera' }).click();
    await page.waitForTimeout(1500);

    // Click delete button (second button in actions column)
    await page.getByRole('button', { name: `Delete camera ${cameraName}` }).click();

    // Delete confirmation should appear
    const deleteModal = page.getByRole('dialog', { name: 'Delete Camera' });
    await expect(deleteModal).toBeVisible();
    await expect(deleteModal.getByText(`Are you sure you want to delete "${cameraName}"?`)).toBeVisible();
    await expect(deleteModal.getByText('cannot be undone')).toBeVisible();

    // Cancel deletion
    await deleteModal.getByRole('button', { name: 'Cancel' }).click();

    // Camera should still be visible
    await expect(page.locator(`td:has-text("${cameraName}")`)).toBeVisible();
  });

  test('should delete camera successfully', async ({ page }) => {
    const cameraName = 'Camera to Remove';

    // Add a camera first
    const addButton = page.getByTestId('add-camera-button');
    await addButton.click();
    const addModal = page.getByRole('dialog', { name: 'Add Camera' });
    await addModal.locator('#camera-name').fill(cameraName);
    await addModal.locator('#camera-type').click();
    await page.getByRole('option', { name: 'RealSense' }).click();
    await addModal.getByRole('button', { name: 'Discover' }).click();
    await page.waitForTimeout(1000);
    await addModal.locator('button[role="combobox"]:has-text("Select device")').click();
    await page.getByRole('option', { name: 'Mock RealSense Camera' }).first().click();
    await addModal.getByRole('button', { name: 'Add Camera' }).click();
    await page.waitForTimeout(1500);

    // Confirm camera was added
    await expect(page.locator(`td:has-text("${cameraName}")`)).toBeVisible();

    // Click delete button
    await page.getByRole('button', { name: `Delete camera ${cameraName}` }).click();

    // Confirm deletion
    const deleteModal = page.getByRole('dialog', { name: 'Delete Camera' });
    await deleteModal.getByRole('button', { name: 'Delete Camera' }).click();
    await page.waitForTimeout(1000);

    // Camera should be removed
    await expect(page.locator(`td:has-text("${cameraName}")`)).not.toBeVisible();

    // Should show empty state
    await expect(page.getByTestId('cameras-empty-state')).toBeVisible();
  });

  test('should show validation error when adding camera without name', async ({ page }) => {
    // Open modal
    const addButton = page.getByTestId('add-camera-button');
    await addButton.click();
    const modal = page.getByRole('dialog', { name: 'Add Camera' });

    // Select type and device but leave name empty
    await modal.locator('#camera-type').click();
    await page.getByRole('option', { name: 'USB Camera' }).click();
    await modal.getByRole('button', { name: 'Discover' }).click();
    await page.waitForTimeout(1000);
    await modal.locator('button[role="combobox"]:has-text("Select device")').click();
    await page.getByRole('option', { name: 'Mock USB Camera 0' }).first().click();

    // Try to add without name
    await modal.getByRole('button', { name: 'Add Camera' }).click();
    await page.waitForTimeout(500);

    // Should show error toast (modal stays open)
    await expect(modal).toBeVisible();
  });

  test('should require device discovery before adding camera', async ({ page }) => {
    // Open modal
    const addButton = page.getByTestId('add-camera-button');
    await addButton.click();
    const modal = page.getByRole('dialog', { name: 'Add Camera' });

    // Fill name and select type but don't discover
    await modal.locator('#camera-name').fill('Test Camera');
    await modal.locator('#camera-type').click();
    await page.getByRole('option', { name: 'USB Camera' }).click();

    // Try to add without discovering/selecting device
    await modal.getByRole('button', { name: 'Add Camera' }).click();
    await page.waitForTimeout(500);

    // Modal should stay open (validation error)
    await expect(modal).toBeVisible();
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
      const addButton = page.getByTestId('add-camera-button');
      await addButton.click();
      const modal = page.getByRole('dialog', { name: 'Add Camera' });

      // Select camera type
      await modal.locator('#camera-type').click();
      await page.getByRole('option', { name: type }).click();

      // Discover should work
      await modal.getByRole('button', { name: 'Discover' }).click();
      await page.waitForTimeout(1000);

      // Mock device should be available
      await modal
        .locator('button[role="combobox"]:has-text("Select device")')
        .click();
      const option = page.getByRole('option', { name: mockDevice }).first();
      await expect(option).toBeVisible();
      await page.keyboard.press('Escape');
      await page.waitForTimeout(100);

      // Close modal
      await modal.getByRole('button', { name: /^Cancel$/ }).click();
      await expect(modal).toBeHidden();
      await page.waitForTimeout(100);
    }
  });

  test('should persist cameras across page reload', async ({ page }) => {
    const cameraName = 'Persistent Camera';

    // Add camera
    const addButton = page.getByTestId('add-camera-button');
    await addButton.click();
    const modal = page.getByRole('dialog', { name: 'Add Camera' });
    await modal.locator('#camera-name').fill(cameraName);
    await modal.locator('#camera-type').click();
    await page.getByRole('option', { name: 'USB Camera' }).click();
    await modal.getByRole('button', { name: 'Discover' }).click();
    await page.waitForTimeout(1000);
    await modal.locator('button[role="combobox"]:has-text("Select device")').click();
    await page.getByRole('option', { name: 'Mock USB Camera 0' }).first().click();
    await modal.getByRole('button', { name: 'Add Camera' }).click();
    await page.waitForTimeout(1500);

    // Reload page
    await page.reload();
    await page.waitForSelector('h1:has-text("Cameras")');
    await page.waitForTimeout(1000);

    // Camera should still be there
    await expect(page.locator(`td:has-text("${cameraName}")`)).toBeVisible();
  });
});
