import { useCallback, useEffect, useMemo, useState } from 'react'
import type { Camera, CameraListResponse } from '../types'
import { CameraFormModal } from '../components/CameraFormModal'
import { CameraTable } from '../components/CameraTable'
import type { CameraStatusState } from '../components/CameraTable'
import { GenicamNodeViewer } from '../components/GenicamNodeViewer'

export function CamerasPage() {
  const [cameras, setCameras] = useState<Camera[]>([])
  const [statuses, setStatuses] = useState<Record<number, CameraStatusState>>({})
  const [loading, setLoading] = useState(true)
  const [genicamEnabled, setGenicamEnabled] = useState(false)
  const [expanded, setExpanded] = useState<Record<number, boolean>>({})
  const [modalOpen, setModalOpen] = useState(false)
  const [modalMode, setModalMode] = useState<'add' | 'edit'>('add')
  const [selectedCamera, setSelectedCamera] = useState<Camera | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)

  const fetchCameraList = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch('/api/cameras')
      const payload = (await response.json().catch(() => ({}))) as CameraListResponse & { error?: string }
      if (!response.ok) {
        throw new Error(payload.error || 'Failed to load cameras')
      }
      setCameras(payload.cameras ?? [])
      setGenicamEnabled(Boolean(payload.genicam_enabled))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load cameras')
      setCameras([])
      setGenicamEnabled(false)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchCameraList()
  }, [fetchCameraList])

  const refreshStatuses = useCallback(async () => {
    if (cameras.length === 0) {
      return
    }

    const updates = await Promise.all(
      cameras.map(async (camera) => {
        try {
          const response = await fetch(`/api/cameras/status/${camera.id}`)
          const payload = (await response.json().catch(() => ({}))) as { connected?: boolean; error?: string }
          if (!response.ok || payload.error) {
            throw new Error(payload.error || 'Failed to fetch status')
          }
          return [camera.id, payload.connected ? 'connected' : 'disconnected'] as const
        } catch {
          return [camera.id, 'error'] as const
        }
      }),
    )

    setStatuses((prev) => {
      const next = { ...prev }
      updates.forEach(([id, status]) => {
        next[id] = status
      })
      return next
    })
  }, [cameras])

  useEffect(() => {
    if (cameras.length === 0) {
      setStatuses({})
      return
    }

    void refreshStatuses()
    const interval = window.setInterval(() => {
      void refreshStatuses()
    }, 5000)

    return () => {
      window.clearInterval(interval)
    }
  }, [cameras, refreshStatuses])

  const existingIdentifiers = useMemo(() => cameras.map((camera) => camera.identifier), [cameras])

  function openAddModal() {
    setModalMode('add')
    setSelectedCamera(undefined)
    setModalOpen(true)
  }

  function openEditModal(camera: Camera) {
    setModalMode('edit')
    setSelectedCamera(camera)
    setModalOpen(true)
  }

  function toggleNodes(camera: Camera) {
    setExpanded((prev) => ({
      ...prev,
      [camera.id]: !prev[camera.id],
    }))
  }

  async function handleDelete(camera: Camera) {
    const confirmed = window.confirm(`Are you sure you want to delete ${camera.name}?`)
    if (!confirmed) {
      return
    }

    try {
      const response = await fetch(`/cameras/delete/${camera.id}`, {
        method: 'POST',
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error((payload as { error?: string }).error || 'Failed to delete camera')
      }
      await fetchCameraList()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : 'Failed to delete camera')
    }
  }

  async function handleModalSubmit(payload: { name: string; type?: string; identifier?: string }) {
    if (modalMode === 'add') {
      const formData = new FormData()
      formData.append('camera-name', payload.name)
      formData.append('camera-type', payload.type ?? '')
      if (payload.type === 'USB') {
        formData.append('usb-camera-select', payload.identifier ?? '')
      } else if (payload.type === 'GenICam') {
        formData.append('genicam-camera-select', payload.identifier ?? '')
      }

      const response = await fetch('/cameras/add', {
        method: 'POST',
        body: formData,
      })
      if (!response.ok) {
        const result = await response.json().catch(() => ({}))
        throw new Error((result as { error?: string }).error || 'Failed to add camera')
      }
    } else if (modalMode === 'edit' && selectedCamera) {
      const formData = new FormData()
      formData.append('camera-name', payload.name)
      const response = await fetch(`/cameras/update/${selectedCamera.id}`, {
        method: 'POST',
        body: formData,
      })
      if (!response.ok) {
        const result = await response.json().catch(() => ({}))
        throw new Error((result as { error?: string }).error || 'Failed to update camera')
      }
    }

    await fetchCameraList()
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold">Cameras</h1>
          <p className="text-sm text-gray-400">Manage configured cameras and inspect GenICam nodes.</p>
        </div>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={fetchCameraList}
            className="rounded-md bg-gray-700 px-4 py-2 text-sm font-medium text-white hover:bg-gray-600"
          >
            Refresh
          </button>
          <button
            type="button"
            onClick={openAddModal}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            Add Camera
          </button>
        </div>
      </div>

      {error && <div className="rounded-md border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-300">{error}</div>}

      <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
        {loading ? (
          <p className="text-sm text-gray-400">Loading cameras...</p>
        ) : (
          <CameraTable
            cameras={cameras}
            statuses={statuses}
            onEdit={openEditModal}
            onDelete={handleDelete}
            onToggleNodes={toggleNodes}
            renderNodeSection={(camera) =>
              expanded[camera.id] ? <GenicamNodeViewer cameraId={camera.id} isOpen /> : null
            }
          />
        )}
      </div>

      <CameraFormModal
        open={modalOpen}
        mode={modalMode}
        camera={selectedCamera}
        onClose={() => setModalOpen(false)}
        onSubmit={handleModalSubmit}
        genicamEnabled={genicamEnabled}
        existingIdentifiers={existingIdentifiers}
      />
    </section>
  )
}
