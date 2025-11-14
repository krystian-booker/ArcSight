import { test, expect, type Locator, type Page } from '@playwright/test'

type CameraTypeOption =
  | {
      typeLabel: 'USB Camera'
      deviceLabel: 'Mock USB Camera 0'
    }
  | {
      typeLabel: 'GenICam Camera'
      deviceLabel: 'Mock GenICam Camera'
    }
  | {
      typeLabel: 'OAK-D Camera'
      deviceLabel: 'Mock OAK-D Camera'
    }
  | {
      typeLabel: 'Intel RealSense'
      deviceLabel: 'Mock RealSense Camera'
    }

type AddCameraOptions = {
  name: string
} & CameraTypeOption

const openAddCameraModal = async (page: Page) => {
  await page.getByTestId('open-add-camera').click()
  const dialog = page.getByTestId('add-camera-dialog')
  await expect(dialog).toBeVisible()
  return dialog
}

const selectCameraType = async (page: Page, dialog: Locator, optionLabel: CameraTypeOption['typeLabel']) => {
  await dialog.getByTestId('camera-type-select').click()
  await page.getByRole('option', { name: optionLabel }).click()
}

const discoverAndSelectDevice = async (
  page: Page,
  dialog: Locator,
  deviceLabel: CameraTypeOption['deviceLabel'],
) => {
  await dialog.getByTestId('discover-devices').click()
  const deviceTrigger = dialog.getByTestId('device-select')
  await expect(deviceTrigger).toBeVisible()
  await deviceTrigger.click()
  await page.getByRole('option', { name: deviceLabel }).click()
}

const addCamera = async (page: Page, options: AddCameraOptions) => {
  const dialog = await openAddCameraModal(page)
  await dialog.getByLabel('Camera Name').fill(options.name)
  await selectCameraType(page, dialog, options.typeLabel)
  await discoverAndSelectDevice(page, dialog, options.deviceLabel)
  await dialog.getByRole('button', { name: 'Add Camera' }).click()
  await expect(dialog).not.toBeVisible()
  return getCameraRow(page, options.name)
}

const getCameraTable = (page: Page) => page.getByTestId('camera-table')

const getCameraRow = async (page: Page, cameraName: string) => {
  const row = getCameraTable(page)
    .getByTestId('camera-row')
    .filter({ hasText: cameraName })
  await expect(row).toHaveCount(1)
  return row.first()
}

test.describe('Cameras Page', () => {
  test.beforeEach(async ({ page, request }) => {
    const resetResponse = await request.post('/test/reset-database')
    expect(resetResponse.ok()).toBeTruthy()
    await page.goto('/cameras')
    await expect(page.getByRole('heading', { name: 'Cameras' })).toBeVisible()
  })

  test('should load cameras page', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Cameras' })).toBeVisible()
    await expect(page.getByTestId('open-add-camera')).toBeVisible()
  })

  test('should show empty state when no cameras configured', async ({ page }) => {
    const emptyState = page.getByTestId('camera-empty-state')
    await expect(emptyState).toBeVisible()
    await expect(emptyState).toContainText('No cameras configured')
    await expect(emptyState).toContainText('Click "Add Camera" to get started')
  })

  test('should open add camera modal', async ({ page }) => {
    const dialog = await openAddCameraModal(page)
    await expect(dialog).toContainText('Add Camera')
    await expect(dialog).toContainText('Configure a new camera device')
    await expect(dialog.getByLabel('Camera Name')).toBeVisible()
    await expect(dialog.getByTestId('camera-type-select')).toBeVisible()
  })

  test('should close add camera modal on cancel', async ({ page }) => {
    const dialog = await openAddCameraModal(page)
    await dialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('should discover mock USB cameras', async ({ page }) => {
    const dialog = await openAddCameraModal(page)
    await selectCameraType(page, dialog, 'USB Camera')
    await dialog.getByTestId('discover-devices').click()
    const deviceTrigger = dialog.getByTestId('device-select')
    await expect(deviceTrigger).toBeVisible()
    await deviceTrigger.click()
    await expect(page.getByRole('option', { name: 'Mock USB Camera 0' })).toBeVisible()
  })

  test('should add a USB camera successfully', async ({ page }) => {
    const cameraName = 'Test USB Camera'
    const row = await addCamera(page, {
      name: cameraName,
      typeLabel: 'USB Camera',
      deviceLabel: 'Mock USB Camera 0',
    })

    await expect(getCameraTable(page)).toBeVisible()
    await expect(row.getByTestId('camera-type-cell')).toHaveText('USB')
    await expect(row.getByTestId('camera-name-cell')).toHaveText(cameraName)
  })

  test('should show camera in table after adding', async ({ page }) => {
    const cameraName = 'Front Camera'
    await addCamera(page, {
      name: cameraName,
      typeLabel: 'GenICam Camera',
      deviceLabel: 'Mock GenICam Camera',
    })

    await expect(getCameraTable(page)).toBeVisible()
    await expect(page.getByTestId('camera-header-name')).toBeVisible()
    await expect(page.getByTestId('camera-header-type')).toBeVisible()
    await expect(page.getByTestId('camera-header-identifier')).toBeVisible()
    await expect(page.getByTestId('camera-header-status')).toBeVisible()
    await expect(page.getByTestId('camera-header-actions')).toBeVisible()
    await getCameraRow(page, cameraName)
  })

  test('should edit camera name', async ({ page }) => {
    const originalName = 'Original Camera'
    const newName = 'Updated Camera Name'

    await addCamera(page, {
      name: originalName,
      typeLabel: 'USB Camera',
      deviceLabel: 'Mock USB Camera 0',
    })

    await page.getByRole('button', { name: `Edit ${originalName}` }).click()
    const editDialog = page.getByTestId('edit-camera-dialog')
    await expect(editDialog).toBeVisible()
    await editDialog.getByLabel('Camera Name').fill(newName)
    await editDialog.getByRole('button', { name: 'Save Changes' }).click()
    await expect(editDialog).not.toBeVisible()

    await getCameraRow(page, newName)
    await expect(
      getCameraTable(page).getByTestId('camera-row').filter({ hasText: originalName }),
    ).toHaveCount(0)
  })

  test('should show delete confirmation dialog', async ({ page }) => {
    const cameraName = 'Camera to Delete'

    await addCamera(page, {
      name: cameraName,
      typeLabel: 'OAK-D Camera',
      deviceLabel: 'Mock OAK-D Camera',
    })

    await page.getByRole('button', { name: `Delete ${cameraName}` }).click()
    const deleteDialog = page.getByTestId('delete-camera-dialog')
    await expect(deleteDialog).toBeVisible()
    await expect(deleteDialog).toContainText('Delete Camera')
    await expect(deleteDialog).toContainText(`Are you sure you want to delete "${cameraName}"`)
    await expect(deleteDialog).toContainText('cannot be undone')

    await deleteDialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(deleteDialog).not.toBeVisible()
    await getCameraRow(page, cameraName)
  })

  test('should delete camera successfully', async ({ page }) => {
    const cameraName = 'Camera to Remove'

    await addCamera(page, {
      name: cameraName,
      typeLabel: 'Intel RealSense',
      deviceLabel: 'Mock RealSense Camera',
    })

    await page.getByRole('button', { name: `Delete ${cameraName}` }).click()
    const deleteDialog = page.getByTestId('delete-camera-dialog')
    await expect(deleteDialog).toBeVisible()
    await deleteDialog.getByRole('button', { name: 'Delete Camera' }).click()
    await expect(deleteDialog).not.toBeVisible()

    await expect(getCameraTable(page).getByTestId('camera-row').filter({ hasText: cameraName })).toHaveCount(0)
    await expect(page.getByTestId('camera-empty-state')).toBeVisible()
  })

  test('should show validation error when adding camera without name', async ({ page }) => {
    const dialog = await openAddCameraModal(page)
    await selectCameraType(page, dialog, 'USB Camera')
    await discoverAndSelectDevice(page, dialog, 'Mock USB Camera 0')
    await dialog.getByRole('button', { name: 'Add Camera' }).click()
    await expect(dialog).toBeVisible()
  })

  test('should require device discovery before adding camera', async ({ page }) => {
    const dialog = await openAddCameraModal(page)
    await dialog.getByLabel('Camera Name').fill('Test Camera')
    await selectCameraType(page, dialog, 'USB Camera')
    await dialog.getByRole('button', { name: 'Add Camera' }).click()
    await expect(dialog).toBeVisible()
  })

  test('should handle all camera types', async ({ page }) => {
    const cameraTypes: CameraTypeOption[] = [
      { typeLabel: 'USB Camera', deviceLabel: 'Mock USB Camera 0' },
      { typeLabel: 'GenICam Camera', deviceLabel: 'Mock GenICam Camera' },
      { typeLabel: 'OAK-D Camera', deviceLabel: 'Mock OAK-D Camera' },
      { typeLabel: 'Intel RealSense', deviceLabel: 'Mock RealSense Camera' },
    ]

    for (const { typeLabel, deviceLabel } of cameraTypes) {
      const dialog = await openAddCameraModal(page)
      await selectCameraType(page, dialog, typeLabel)
      await discoverAndSelectDevice(page, dialog, deviceLabel)
      await dialog.getByRole('button', { name: 'Cancel' }).click()
      await expect(dialog).not.toBeVisible()
    }
  })

  test('should persist cameras across page reload', async ({ page }) => {
    const cameraName = 'Persistent Camera'

    await addCamera(page, {
      name: cameraName,
      typeLabel: 'USB Camera',
      deviceLabel: 'Mock USB Camera 0',
    })

    await page.reload()
    await expect(page.getByRole('heading', { name: 'Cameras' })).toBeVisible()
    await getCameraRow(page, cameraName)
  })
})
