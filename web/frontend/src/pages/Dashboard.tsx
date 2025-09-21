import { useEffect, useState } from 'react'
import type { Camera, CameraListResponse, CameraStatusResponse } from '../types'

export function DashboardPage() {
  const [cameras, setCameras] = useState<Camera[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedCameraId, setSelectedCameraId] = useState<number | null>(null)
  const [feedUrl, setFeedUrl] = useState('')
  const [feedMessage, setFeedMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void fetchCameras()
  }, [])

  useEffect(() => {
    if (selectedCameraId !== null) {
      void updateCameraFeed(selectedCameraId)
    } else {
      setFeedUrl('')
    }
  }, [selectedCameraId])

  async function fetchCameras() {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch('/api/cameras')
      const payload = (await response.json().catch(() => ({}))) as CameraListResponse & { error?: string }
      if (!response.ok) {
        throw new Error(payload.error || 'Failed to load cameras')
      }
      setCameras(payload.cameras ?? [])
      setSelectedCameraId(payload.cameras?.[0]?.id ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load cameras')
      setCameras([])
      setSelectedCameraId(null)
    } finally {
      setLoading(false)
    }
  }

  async function updateCameraFeed(cameraId: number) {
    setFeedMessage('Checking camera status...')
    setFeedUrl('')
    try {
      const response = await fetch(`/api/cameras/status/${cameraId}`)
      const payload = (await response.json().catch(() => ({}))) as CameraStatusResponse
      if (!response.ok || payload.error) {
        throw new Error(payload.error || 'Failed to fetch camera status')
      }

      if (payload.connected) {
        setFeedUrl(`/video_feed/${cameraId}?t=${Date.now()}`)
        setFeedMessage(null)
      } else {
        setFeedMessage('Camera is not connected.')
      }
    } catch (err) {
      setFeedMessage(err instanceof Error ? err.message : 'Failed to load camera feed')
    }
  }

  return (
    <section>
      <div className="flex flex-col gap-6">
        <div>
          <div className="mb-4 flex items-center justify-between">
            <h1 className="text-3xl font-bold">Dashboard</h1>
            <button
              type="button"
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
              onClick={fetchCameras}
            >
              Refresh Cameras
            </button>
          </div>

          <div className="mb-4">
            <label htmlFor="camera-select" className="mb-2 block text-sm font-medium text-gray-300">
              Select Camera
            </label>
            <select
              id="camera-select"
              value={selectedCameraId ?? ''}
              onChange={(event) => {
                const value = event.target.value
                setSelectedCameraId(value ? Number(value) : null)
              }}
              className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              disabled={cameras.length === 0}
            >
              {cameras.length > 0 ? (
                cameras.map((camera) => (
                  <option key={camera.id} value={camera.id}>
                    {camera.name}
                  </option>
                ))
              ) : (
                <option value="">No cameras configured</option>
              )}
            </select>
          </div>

          <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
            <div className="flex h-96 items-center justify-center rounded bg-black">
              {loading ? (
                <p className="text-gray-400">Loading cameras...</p>
              ) : feedUrl ? (
                <img src={feedUrl} alt="Camera Feed" className="max-h-full max-w-full" />
              ) : feedMessage ? (
                <p className="text-sm text-gray-300">{feedMessage}</p>
              ) : error ? (
                <p className="text-sm text-red-400">{error}</p>
              ) : (
                <p className="text-sm text-gray-500">No camera feed available.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
