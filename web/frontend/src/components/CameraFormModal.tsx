import type { FormEvent } from 'react'
import { useEffect, useState } from 'react'
import type { Camera, DiscoverResponse } from '../types'
import { Modal } from './Modal'

type Mode = 'add' | 'edit'

interface CameraFormModalProps {
  open: boolean
  mode: Mode
  onClose: () => void
  onSubmit: (payload: { name: string; type?: string; identifier?: string }) => Promise<void>
  genicamEnabled: boolean
  existingIdentifiers: string[]
  camera?: Camera
}

export function CameraFormModal({
  open,
  mode,
  onClose,
  onSubmit,
  genicamEnabled,
  existingIdentifiers,
  camera,
}: CameraFormModalProps) {
  const [name, setName] = useState('')
  const [cameraType, setCameraType] = useState('')
  const [availableUsb, setAvailableUsb] = useState<DiscoverResponse['usb']>([])
  const [availableGenicam, setAvailableGenicam] = useState<DiscoverResponse['genicam']>([])
  const [selectedIdentifier, setSelectedIdentifier] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }

    if (mode === 'edit' && camera) {
      setName(camera.name)
      setCameraType(camera.camera_type)
      setSelectedIdentifier(camera.identifier)
    } else {
      setName('')
      setCameraType('')
      setSelectedIdentifier('')
      setAvailableUsb([])
      setAvailableGenicam([])
    }
    setError(null)
  }, [open, mode, camera])

  useEffect(() => {
    if (mode === 'add' && cameraType) {
      void discoverCameras(cameraType)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraType, mode])

  async function discoverCameras(type: string) {
    setLoading(true)
    setError(null)
    try {
      const query = existingIdentifiers.join(',')
      const response = await fetch(`/api/cameras/discover?existing=${encodeURIComponent(query)}`)
      const payload = (await response.json().catch(() => ({}))) as DiscoverResponse
      if (!response.ok) {
        throw new Error('Failed to discover cameras')
      }
      setAvailableUsb(payload.usb ?? [])
      setAvailableGenicam(payload.genicam ?? [])
      if (type === 'USB') {
        setSelectedIdentifier(payload.usb?.[0]?.identifier ?? '')
      } else if (type === 'GenICam') {
        setSelectedIdentifier(payload.genicam?.[0]?.identifier ?? '')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to discover cameras')
    } finally {
      setLoading(false)
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)

    if (!name.trim()) {
      setError('Camera name is required')
      return
    }

    if (mode === 'add') {
      if (!cameraType) {
        setError('Camera type is required')
        return
      }
      if (!selectedIdentifier) {
        setError('Please select a camera source')
        return
      }
    }

    setLoading(true)
    try {
      await onSubmit({
        name: name.trim(),
        type: mode === 'add' ? cameraType : undefined,
        identifier: mode === 'add' ? selectedIdentifier : undefined,
      })
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save camera')
    } finally {
      setLoading(false)
    }
  }

  const showGenicamOption = genicamEnabled

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={mode === 'add' ? 'Add New Camera' : 'Edit Camera'}
      footer={
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md bg-gray-600 px-4 py-2 text-sm font-medium text-white hover:bg-gray-500"
            disabled={loading}
          >
            Cancel
          </button>
          <button
            type="submit"
            form="camera-form"
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-60"
            disabled={loading}
          >
            {loading ? 'Saving...' : 'Save'}
          </button>
        </div>
      }
    >
      <form id="camera-form" onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-300" htmlFor="camera-name">
            Camera Name
          </label>
          <input
            id="camera-name"
            name="camera-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="mt-2 w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            required
          />
        </div>

        {mode === 'add' && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300" htmlFor="camera-type">
                Camera Type
              </label>
              <select
                id="camera-type"
                value={cameraType}
                onChange={(event) => setCameraType(event.target.value)}
                className="mt-2 w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                required
              >
                <option value="">-- Select a Type --</option>
                <option value="USB">Generic USB Camera</option>
                {showGenicamOption && <option value="GenICam">GenICam</option>}
              </select>
            </div>

            {cameraType === 'USB' && (
              <div>
                <label className="block text-sm font-medium text-gray-300" htmlFor="usb-camera">
                  Select USB Camera
                </label>
                <select
                  id="usb-camera"
                  value={selectedIdentifier}
                  onChange={(event) => setSelectedIdentifier(event.target.value)}
                  className="mt-2 w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  disabled={loading || availableUsb.length === 0}
                  required
                >
                  {availableUsb.length > 0 ? (
                    availableUsb.map((item) => (
                      <option key={item.identifier} value={item.identifier}>
                        {item.name}
                      </option>
                    ))
                  ) : (
                    <option value="">No available cameras found</option>
                  )}
                </select>
              </div>
            )}

            {cameraType === 'GenICam' && (
              <div>
                <label className="block text-sm font-medium text-gray-300" htmlFor="genicam-camera">
                  Select GenICam Camera
                </label>
                <select
                  id="genicam-camera"
                  value={selectedIdentifier}
                  onChange={(event) => setSelectedIdentifier(event.target.value)}
                  className="mt-2 w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  disabled={loading || availableGenicam.length === 0}
                  required
                >
                  {availableGenicam.length > 0 ? (
                    availableGenicam.map((item) => (
                      <option key={item.identifier} value={item.identifier}>
                        {item.name}
                      </option>
                    ))
                  ) : (
                    <option value="">No available cameras found</option>
                  )}
                </select>
              </div>
            )}
          </div>
        )}

        {error && <div className="text-sm text-red-400">{error}</div>}
      </form>
    </Modal>
  )
}
