import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

const SUCCESS_STATUSES = new Set([200, 201, 202, 204, 304])

const waitForEndpoint = (page: Page, endpoint: string, method?: string) =>
  page.waitForResponse((response) => {
    if (!response.url().endsWith(endpoint)) return false
    if (method && response.request().method() !== method) return false
    return SUCCESS_STATUSES.has(response.status())
  })

const loadSettingsPage = async (page: Page) => {
  const responsePromise = waitForEndpoint(page, '/settings/api/settings')
  await page.goto('/settings')
  await responsePromise
  await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeVisible()
}

const reloadSettingsPage = async (page: Page) => {
  const responsePromise = waitForEndpoint(page, '/settings/api/settings')
  await page.reload()
  await responsePromise
  await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeVisible()
}

test.describe('Settings Page', () => {
  test.beforeEach(async ({ page }) => {
    await loadSettingsPage(page)
  })

  test('should load settings page', async ({ page }) => {
    await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeVisible()
    await expect(page.getByRole('tab', { name: 'Global' })).toBeVisible()
    await expect(page.getByRole('tab', { name: 'GenICam' })).toBeVisible()
    await expect(page.getByRole('tab', { name: 'AprilTag Fields' })).toBeVisible()
    await expect(page.getByRole('tab', { name: 'System' })).toBeVisible()
  })

  test('should save and persist team number', async ({ page }) => {
    const teamNumberInput = page.locator('#team-number')
    await teamNumberInput.fill('1234')

    await Promise.all([
      waitForEndpoint(page, '/settings/global/update', 'POST'),
      page.getByRole('button', { name: 'Save Global Settings' }).click(),
    ])

    await reloadSettingsPage(page)
    await expect(teamNumberInput).toHaveValue('1234')
  })

  test('should save and persist hostname', async ({ page }) => {
    const hostnameInput = page.locator('#hostname')
    await hostnameInput.fill('test-arcsight-device')

    await Promise.all([
      waitForEndpoint(page, '/settings/global/update', 'POST'),
      page.getByRole('button', { name: 'Save Global Settings' }).click(),
    ])

    await reloadSettingsPage(page)
    await expect(hostnameInput).toHaveValue('test-arcsight-device')
  })

  test('should toggle IP mode between DHCP and Static', async ({ page }) => {
    const ipSelect = page.locator('#ip-mode')

    await ipSelect.click()
    await page.getByRole('option', { name: 'DHCP' }).click()
    await Promise.all([
      waitForEndpoint(page, '/settings/global/update', 'POST'),
      page.getByRole('button', { name: 'Save Global Settings' }).click(),
    ])

    await reloadSettingsPage(page)
    await expect(ipSelect).toContainText('DHCP')

    await ipSelect.click()
    await page.getByRole('option', { name: 'Static IP' }).click()
    await Promise.all([
      waitForEndpoint(page, '/settings/global/update', 'POST'),
      page.getByRole('button', { name: 'Save Global Settings' }).click(),
    ])

    await reloadSettingsPage(page)
    await expect(ipSelect).toContainText('Static IP')

    await ipSelect.click()
    await page.getByRole('option', { name: 'DHCP' }).click()
    await Promise.all([
      waitForEndpoint(page, '/settings/global/update', 'POST'),
      page.getByRole('button', { name: 'Save Global Settings' }).click(),
    ])
  })

  test('should save all global settings together', async ({ page }) => {
    const teamNumberInput = page.locator('#team-number')
    const hostnameInput = page.locator('#hostname')
    const ipSelect = page.locator('#ip-mode')

    await teamNumberInput.fill('5678')
    await hostnameInput.fill('arcsight-test')
    await ipSelect.click()
    await page.getByRole('option', { name: 'DHCP' }).click()

    await Promise.all([
      waitForEndpoint(page, '/settings/global/update', 'POST'),
      page.getByRole('button', { name: 'Save Global Settings' }).click(),
    ])

    await reloadSettingsPage(page)
    await expect(teamNumberInput).toHaveValue('5678')
    await expect(hostnameInput).toHaveValue('arcsight-test')
    await expect(ipSelect).toContainText('DHCP')
  })

  test('should clear values when saved as empty', async ({ page }) => {
    const teamNumberInput = page.locator('#team-number')

    await teamNumberInput.fill('9999')
    await Promise.all([
      waitForEndpoint(page, '/settings/global/update', 'POST'),
      page.getByRole('button', { name: 'Save Global Settings' }).click(),
    ])

    await teamNumberInput.fill('')
    await Promise.all([
      waitForEndpoint(page, '/settings/global/update', 'POST'),
      page.getByRole('button', { name: 'Save Global Settings' }).click(),
    ])

    await reloadSettingsPage(page)
    await expect(teamNumberInput).toHaveValue('')
  })

  test('should have GenICam configuration tab', async ({ page }) => {
    await page.getByRole('tab', { name: 'GenICam' }).click()
    await expect(page.getByRole('heading', { name: 'GenICam Settings' })).toBeVisible()
    await expect(page.locator('#cti-path')).toBeVisible()
  })

  test('should save and persist GenICam CTI path', async ({ page }) => {
    const ctiInput = page.locator('#cti-path')
    const testPath = '/usr/local/lib/producer.cti'

    await page.getByRole('tab', { name: 'GenICam' }).click()
    await ctiInput.fill(testPath)

    await Promise.all([
      waitForEndpoint(page, '/settings/genicam/update', 'POST'),
      page.getByRole('button', { name: 'Save Path' }).click(),
    ])

    await reloadSettingsPage(page)
    await page.getByRole('tab', { name: 'GenICam' }).click()
    await expect(ctiInput).toHaveValue(testPath)
  })

  test('should clear GenICam CTI path', async ({ page }) => {
    const ctiInput = page.locator('#cti-path')
    const testPath = '/tmp/test.cti'

    await page.getByRole('tab', { name: 'GenICam' }).click()
    await ctiInput.fill(testPath)

    await Promise.all([
      waitForEndpoint(page, '/settings/genicam/update', 'POST'),
      page.getByRole('button', { name: 'Save Path' }).click(),
    ])

    await Promise.all([
      waitForEndpoint(page, '/settings/genicam/clear', 'POST'),
      page.getByRole('button', { name: 'Clear Path' }).click(),
    ])

    await expect(ctiInput).toHaveValue('')

    await reloadSettingsPage(page)
    await page.getByRole('tab', { name: 'GenICam' }).click()
    await expect(ctiInput).toHaveValue('')
  })

  test('should save and persist AprilTag field selection', async ({ page }) => {
    await page.getByRole('tab', { name: 'AprilTag Fields' }).click()

    await page.locator('#field-select').click()
    const initialOptions = page.locator('[role="option"]')
    const optionCount = await initialOptions.count()
    expect(optionCount).toBeGreaterThan(0)

    const firstLabel = (await initialOptions.first().textContent())?.trim() ?? ''
    expect(firstLabel).not.toEqual('')

    await Promise.all([
      waitForEndpoint(page, '/settings/apriltag/select', 'POST'),
      initialOptions.first().click(),
    ])

    await expect(page.locator('#field-select')).toContainText(firstLabel)

    await reloadSettingsPage(page)
    await page.getByRole('tab', { name: 'AprilTag Fields' }).click()
    await expect(page.locator('#field-select')).toContainText(firstLabel)

    if (optionCount > 1) {
      await page.locator('#field-select').click()
      const options = page.locator('[role="option"]')
      const secondLabel = (await options.nth(1).textContent())?.trim() ?? ''
      expect(secondLabel).not.toEqual('')

      await Promise.all([
        waitForEndpoint(page, '/settings/apriltag/select', 'POST'),
        options.nth(1).click(),
      ])

      await expect(page.locator('#field-select')).toContainText(secondLabel)

      await reloadSettingsPage(page)
      await page.getByRole('tab', { name: 'AprilTag Fields' }).click()
      await expect(page.locator('#field-select')).toContainText(secondLabel)
    }
  })

  test('should have system control buttons', async ({ page }) => {
    await page.getByRole('tab', { name: 'System' }).click()
    await expect(page.getByRole('button', { name: 'Restart Application' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Reboot Device' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Factory Reset' })).toBeVisible()
  })

  test('should show confirmation dialog for restart and allow cancel', async ({ page }) => {
    await page.getByRole('tab', { name: 'System' }).click()
    await page.getByRole('button', { name: 'Restart Application' }).click()

    const dialog = page.locator('[role="dialog"]')
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText('temporarily interrupt all camera feeds')

    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('should show confirmation dialog for reboot and allow cancel', async ({ page }) => {
    await page.getByRole('tab', { name: 'System' }).click()
    await page.getByRole('button', { name: 'Reboot Device' }).click()

    const dialog = page.locator('[role="dialog"]')
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText('All processes will be stopped')

    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('should show confirmation dialog for factory reset and allow cancel', async ({ page }) => {
    await page.getByRole('tab', { name: 'System' }).click()
    await page.getByRole('button', { name: 'Factory Reset' }).click()

    const dialog = page.locator('[role="dialog"]')
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText('cannot be undone')

    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('should have export and import database buttons', async ({ page }) => {
    await page.getByRole('tab', { name: 'System' }).click()
    await expect(page.getByRole('button', { name: 'Export Database' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Import Database' })).toBeVisible()
  })

  test('should navigate between settings tabs', async ({ page }) => {
    await page.getByRole('tab', { name: 'Global' }).click()
    await expect(page.getByRole('heading', { name: 'Global Settings' })).toBeVisible()

    await page.getByRole('tab', { name: 'GenICam' }).click()
    await expect(page.getByRole('heading', { name: 'GenICam Settings' })).toBeVisible()

    await page.getByRole('tab', { name: 'AprilTag Fields' }).click()
    await expect(page.getByRole('heading', { name: 'AprilTag Field Layouts' })).toBeVisible()

    await page.getByRole('tab', { name: 'System' }).click()
    await expect(page.getByRole('heading', { name: 'System Controls' })).toBeVisible()
  })
})
