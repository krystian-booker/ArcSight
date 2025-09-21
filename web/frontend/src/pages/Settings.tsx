import type { ChangeEvent, FormEvent } from 'react'
import { useEffect, useRef, useState } from 'react'
import { FactoryResetModal } from '../components/FactoryResetModal'
import type { SettingsResponse } from '../types'

export function SettingsPage() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [globalMessage, setGlobalMessage] = useState<string | null>(null)
  const [genicamMessage, setGenicamMessage] = useState<string | null>(null)
  const [globalSaving, setGlobalSaving] = useState(false)
  const [genicamSaving, setGenicamSaving] = useState(false)
  const [factoryModalOpen, setFactoryModalOpen] = useState(false)
  const [globalForm, setGlobalForm] = useState({ team_number: '', ip_mode: 'DHCP', hostname: '' })
  const [genicamPath, setGenicamPath] = useState('')
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    void fetchSettings()
  }, [])

  async function fetchSettings() {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch('/api/settings')
      const payload = (await response.json().catch(() => ({}))) as SettingsResponse & { error?: string }
      if (!response.ok) {
        throw new Error(payload.error || 'Failed to load settings')
      }
      const data: SettingsResponse = {
        team_number: payload.team_number || '',
        ip_mode: payload.ip_mode || 'DHCP',
        hostname: payload.hostname || 'vision-tools',
        genicam_cti_path: payload.genicam_cti_path || '',
      }
      setSettings(data)
      setGlobalForm({
        team_number: data.team_number,
        ip_mode: data.ip_mode || 'DHCP',
        hostname: data.hostname || 'vision-tools',
      })
      setGenicamPath('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings')
    } finally {
      setLoading(false)
    }
  }

  async function handleGlobalSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setGlobalSaving(true)
    setGlobalMessage(null)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('team_number', globalForm.team_number)
      formData.append('ip_mode', globalForm.ip_mode)
      formData.append('hostname', globalForm.hostname)

      const response = await fetch('/settings/global/update', {
        method: 'POST',
        body: formData,
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error((payload as { error?: string }).error || 'Failed to save global settings')
      }
      setGlobalMessage('Global settings saved successfully.')
      await fetchSettings()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save global settings')
    } finally {
      setGlobalSaving(false)
    }
  }

  async function handleGenicamSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setGenicamSaving(true)
    setGenicamMessage(null)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('genicam-cti-path', genicamPath)

      const response = await fetch('/config/genicam/update', {
        method: 'POST',
        body: formData,
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error((payload as { error?: string }).error || 'Failed to update GenICam settings')
      }
      setGenicamMessage('GenICam settings updated successfully.')
      await fetchSettings()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update GenICam settings')
    } finally {
      setGenicamSaving(false)
    }
  }

  async function postToAction(url: string, successMessage?: string) {
    try {
      const response = await fetch(url, {
        method: 'POST',
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error((payload as { error?: string }).error || 'Action failed')
      }
      if (successMessage) {
        setGlobalMessage(successMessage)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed')
    }
  }

  function handleImportClick() {
    fileInputRef.current?.click()
  }

  async function handleImportChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return

    const formData = new FormData()
    formData.append('database', file)
    try {
      const response = await fetch('/control/import-db', {
        method: 'POST',
        body: formData,
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error((payload as { error?: string }).error || 'Failed to import configuration')
      }
      setGlobalMessage('Configuration imported successfully.')
      await fetchSettings()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import configuration')
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  async function handleFactoryReset() {
    setFactoryModalOpen(false)
    await postToAction('/control/factory-reset', 'Device reset to factory defaults.')
    await fetchSettings()
  }

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Settings</h1>
        <p className="text-sm text-gray-400">Manage application preferences and device controls.</p>
      </div>

      {loading ? (
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-6 text-sm text-gray-300">Loading settings...</div>
      ) : (
        <div className="space-y-6">
          {error && <div className="rounded-md border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-300">{error}</div>}
          {globalMessage && (
            <div className="rounded-md border border-green-500/40 bg-green-500/10 p-4 text-sm text-green-300">{globalMessage}</div>
          )}
          {genicamMessage && (
            <div className="rounded-md border border-indigo-500/40 bg-indigo-500/10 p-4 text-sm text-indigo-200">{genicamMessage}</div>
          )}

          <div className="rounded-lg border border-gray-800 bg-gray-900 p-6">
            <h2 className="text-2xl font-semibold">Global Settings</h2>
            <form onSubmit={handleGlobalSubmit} className="mt-4 space-y-4">
              <div>
                <label htmlFor="team-number" className="block text-sm font-medium text-gray-300">
                  Team Number
                </label>
                <input
                  id="team-number"
                  name="team_number"
                  type="number"
                  value={globalForm.team_number}
                  onChange={(event) => setGlobalForm((prev) => ({ ...prev, team_number: event.target.value }))}
                  className="mt-2 w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div>
                <span className="block text-sm font-medium text-gray-300">IP Assignment Mode</span>
                <div className="mt-2 flex gap-6">
                  {['DHCP', 'Static'].map((mode) => (
                    <label key={mode} className="flex items-center gap-2 text-sm text-gray-300">
                      <input
                        type="radio"
                        name="ip_mode"
                        value={mode}
                        checked={globalForm.ip_mode === mode}
                        onChange={(event) => setGlobalForm((prev) => ({ ...prev, ip_mode: event.target.value }))}
                        className="border-gray-600 bg-gray-800 text-indigo-600 focus:ring-indigo-500"
                      />
                      {mode}
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label htmlFor="hostname" className="block text-sm font-medium text-gray-300">
                  Hostname
                </label>
                <input
                  id="hostname"
                  name="hostname"
                  type="text"
                  value={globalForm.hostname}
                  onChange={(event) => setGlobalForm((prev) => ({ ...prev, hostname: event.target.value }))}
                  className="mt-2 w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={globalSaving}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-60"
                >
                  {globalSaving ? 'Saving...' : 'Save Global Settings'}
                </button>
              </div>
            </form>
          </div>

          <div className="rounded-lg border border-gray-800 bg-gray-900 p-6 space-y-4">
            <div>
              <h2 className="text-2xl font-semibold">GenICam Settings</h2>
              <p className="text-sm text-gray-400">Current: {settings?.genicam_cti_path || 'Not set'}</p>
            </div>
            <form onSubmit={handleGenicamSubmit} className="space-y-4">
              <div>
                <label htmlFor="genicam-cti-path" className="block text-sm font-medium text-gray-300">
                  GenTL Producer Path (.cti file)
                </label>
                <input
                  id="genicam-cti-path"
                  type="text"
                  value={genicamPath}
                  placeholder="C:\\path\\to\\your\\genicam.cti"
                  onChange={(event) => setGenicamPath(event.target.value)}
                  className="mt-2 w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
                <p className="mt-2 text-xs text-gray-400">
                  Enter the full path to the .cti file from your camera's SDK. Leave blank to clear the current configuration.
                </p>
              </div>
              <div className="flex justify-end gap-3">
                <button
                  type="submit"
                  disabled={genicamSaving}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-60"
                >
                  {genicamSaving ? 'Saving...' : 'Save GenICam Settings'}
                </button>
              </div>
            </form>
          </div>

          <div className="rounded-lg border border-gray-800 bg-gray-900 p-6 space-y-4">
            <h2 className="text-2xl font-semibold">Device Control</h2>
            <div className="grid gap-4 md:grid-cols-2">
              <button
                type="button"
                onClick={() => postToAction('/control/restart-app', 'Application restart triggered.')}
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
              >
                Restart Vision-Tools
              </button>
              <button
                type="button"
                onClick={() => postToAction('/control/reboot', 'Device restart requested.')}
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
              >
                Restart Device
              </button>
              <a
                href="/control/export-db"
                className="rounded-md bg-green-600 px-4 py-2 text-center text-sm font-semibold text-white hover:bg-green-700"
              >
                Export Configuration
              </a>
              <button
                type="button"
                onClick={handleImportClick}
                className="rounded-md bg-yellow-600 px-4 py-2 text-sm font-semibold text-white hover:bg-yellow-700"
              >
                Import Configuration
              </button>
            </div>
            <div>
              <button
                type="button"
                onClick={() => setFactoryModalOpen(true)}
                className="w-full rounded-md bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700"
              >
                Factory Reset
              </button>
            </div>
          </div>
        </div>
      )}

      <input ref={fileInputRef} type="file" className="hidden" onChange={handleImportChange} />

      <FactoryResetModal
        open={factoryModalOpen}
        onCancel={() => setFactoryModalOpen(false)}
        onConfirm={handleFactoryReset}
      />
    </section>
  )
}
