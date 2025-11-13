import { test, expect, type APIRequestContext, type Locator, type Page } from '@playwright/test';

type CameraTypeKey = 'usb' | 'genicam' | 'oakd' | 'realsense';

const CAMERA_TYPES: Record<CameraTypeKey, { optionText: string; deviceText: string }> = {
  usb: { optionText: 'USB Camera', deviceText: 'Mock USB Camera 0' },
  genicam: { optionText: 'GenICam Camera', deviceText: 'Mock GenICam Camera' },
  oakd: { optionText: 'OAK-D Camera', deviceText: 'Mock OAK-D Camera' },
  realsense: { optionText: 'Intel RealSense', deviceText: 'Mock RealSense Camera' },
};

async function resetDatabase(request: APIRequestContext): Promise<void> {
  const response = await request.post('/test/reset-database', { failOnStatusCode: false });
  if (!response.ok()) {
    throw new Error(`Failed to reset database: ${response.status()} ${await response.text()}`);
  }
}

async function openAddCameraModal(page: Page): Promise<Locator> {
  await page.getByRole('button', { name: 'Add Camera' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Add Camera' });
  await expect(dialog).toBeVisible();
  return dialog;
}

async function selectCameraTypeAndDevice(
  page: Page,
  dialog: Locator,
  config: { optionText: string; deviceText: string },
): Promise<void> {
  await dialog.locator('#camera-type').click();
  await page.getByRole('option', { name: config.optionText }).click();

  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes('/cameras/discover') &&
        response.request().method() === 'GET' &&
        response.ok(),
    ),
    dialog.getByRole('button', { name: /Discover/ }).click(),
  ]);

  const deviceTrigger = dialog.locator('#available-device');
  await expect(deviceTrigger).toBeVisible();
  await deviceTrigger.click();
  await page.getByRole('option', { name: config.deviceText }).click();
}

async function addCamera(
  page: Page,
  { name, type }: { name: string; type: CameraTypeKey },
): Promise<void> {
  const dialog = await openAddCameraModal(page);
  await dialog.getByLabel('Camera Name').fill(name);
  await selectCameraTypeAndDevice(page, dialog, CAMERA_TYPES[type]);

  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes('/cameras/add') &&
        response.request().method() === 'POST' &&
        response.ok(),
    ),
    page.waitForResponse(
      (response) =>
        response.url().includes('/api/cameras') &&
        response.request().method() === 'GET' &&
        response.ok(),
    ),
    dialog.getByRole('button', { name: 'Add Camera', exact: true }).click(),
  ]);

  await expect(dialog).toBeHidden();
  await expect(page.getByRole('cell', { name, exact: true })).toBeVisible();
}

test.describe('Cameras Page', () => {
  test.beforeEach(async ({ page, request }) => {
    await resetDatabase(request);
    await page.goto('/cameras');
    await expect(page.getByRole('heading', { level: 1, name: 'Cameras' })).toBeVisible();
  });

  test('should load cameras page', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Cameras' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Add Camera' })).toBeVisible();
  });

  test('should show empty state when no cameras configured', async ({ page }) => {
    await expect(page.getByText('No cameras configured')).toBeVisible();
    await expect(page.getByText('Click "Add Camera" to get started')).toBeVisible();
  });

  test('should open add camera modal', async ({ page }) => {
    const dialog = await openAddCameraModal(page);
    await expect(dialog.getByText('Configure a new camera device')).toBeVisible();
    await dialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(dialog).toBeHidden();
  });

  test('should close add camera modal on cancel', async ({ page }) => {
    const dialog = await openAddCameraModal(page);
    await dialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(dialog).toBeHidden();
  });

  test('should discover mock USB cameras', async ({ page }) => {
    const dialog = await openAddCameraModal(page);
    await selectCameraTypeAndDevice(page, dialog, CAMERA_TYPES.usb);
    await dialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(dialog).toBeHidden();
  });

  test('should add a USB camera successfully', async ({ page }) => {
    const name = 'Test USB Camera';
    await addCamera(page, { name, type: 'usb' });
    await expect(page.getByRole('cell', { name: 'USB', exact: true })).toBeVisible();
  });

  test('should show camera in table after adding', async ({ page }) => {
    const name = 'Front Camera';
    await addCamera(page, { name, type: 'genicam' });

    const table = page.getByRole('table');
    await expect(table).toBeVisible();
    const header = table.locator('thead');
    await expect(header).toContainText('Name');
    await expect(header).toContainText('Type');
    await expect(header).toContainText('Identifier');
    await expect(header).toContainText('Status');
    await expect(table.getByRole('cell', { name, exact: true })).toBeVisible();
  });

  test('should edit camera name', async ({ page }) => {
    const originalName = 'Original Camera';
    const newName = 'Updated Camera Name';

    await addCamera(page, { name: originalName, type: 'usb' });

    await page.getByRole('button', { name: `Edit camera ${originalName}` }).click();
    const editDialog = page.getByRole('dialog', { name: 'Edit Camera' });
    await expect(editDialog).toBeVisible();

    await editDialog.getByLabel('Camera Name').fill(newName);

    await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes('/cameras/update/') &&
          response.request().method() === 'POST' &&
          response.ok(),
      ),
      editDialog.getByRole('button', { name: 'Save Changes' }).click(),
    ]);

    await expect(editDialog).toBeHidden();
    await expect(page.getByRole('cell', { name: newName, exact: true })).toBeVisible();
    await expect(page.locator('td').filter({ hasText: originalName })).toHaveCount(0);
  });

  test('should show delete confirmation dialog', async ({ page }) => {
    const cameraName = 'Camera to Delete';
    await addCamera(page, { name: cameraName, type: 'oakd' });

    await page.getByRole('button', { name: `Delete camera ${cameraName}` }).click();
    const deleteDialog = page.getByRole('dialog', { name: 'Delete Camera' });
    await expect(deleteDialog).toBeVisible();
    await expect(deleteDialog.getByText(`Are you sure you want to delete "${cameraName}"`)).toBeVisible();
    await expect(deleteDialog.getByText('cannot be undone')).toBeVisible();
    await deleteDialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(deleteDialog).toBeHidden();
    await expect(page.locator('td').filter({ hasText: cameraName })).toBeVisible();
  });

  test('should delete camera successfully', async ({ page }) => {
    const cameraName = 'Camera to Remove';
    await addCamera(page, { name: cameraName, type: 'realsense' });

    await page.getByRole('button', { name: `Delete camera ${cameraName}` }).click();
    const deleteDialog = page.getByRole('dialog', { name: 'Delete Camera' });
    await expect(deleteDialog).toBeVisible();

    await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes('/cameras/delete/') &&
          response.request().method() === 'POST' &&
          response.ok(),
      ),
      deleteDialog.getByRole('button', { name: 'Delete Camera', exact: true }).click(),
    ]);

    await expect(deleteDialog).toBeHidden();
    await expect(page.getByText('No cameras configured')).toBeVisible();
  });

  test('should show validation error when adding camera without name', async ({ page }) => {
    const dialog = await openAddCameraModal(page);
    await selectCameraTypeAndDevice(page, dialog, CAMERA_TYPES.usb);

    await dialog.getByRole('button', { name: 'Add Camera', exact: true }).click();
    await expect(page.getByText('Please fill in all fields')).toBeVisible();
    await dialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(dialog).toBeHidden();
  });

  test('should require device discovery before adding camera', async ({ page }) => {
    const dialog = await openAddCameraModal(page);
    await dialog.getByLabel('Camera Name').fill('Test Camera');
    await dialog.locator('#camera-type').click();
    await page.getByRole('option', { name: CAMERA_TYPES.usb.optionText }).click();

    await dialog.getByRole('button', { name: 'Add Camera', exact: true }).click();
    await expect(page.getByText('Please fill in all fields')).toBeVisible();
    await dialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(dialog).toBeHidden();
  });

  test('should handle all camera types', async ({ page }) => {
    for (const config of Object.values(CAMERA_TYPES)) {
      const dialog = await openAddCameraModal(page);
      await selectCameraTypeAndDevice(page, dialog, config);
      await dialog.getByRole('button', { name: 'Cancel' }).click();
      await expect(dialog).toBeHidden();
    }
  });

  test('should persist cameras across page reload', async ({ page }) => {
    const cameraName = 'Persistent Camera';
    await addCamera(page, { name: cameraName, type: 'usb' });

    await page.reload();
    await page.waitForSelector('h1:has-text("Cameras")');
    await expect(page.locator('td').filter({ hasText: cameraName })).toBeVisible();
  });
});
