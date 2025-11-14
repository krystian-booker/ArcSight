import { useState, useEffect } from 'react'
import { Camera as CameraIcon, Plus, Edit2, Trash2, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { StatusBadge } from '@/components/shared'
import { toast } from '@/hooks/use-toast'
import { api } from '@/lib/api'
import { useAppStore } from '@/store/useAppStore'
import type { Camera, CameraStatus, DeviceInfo } from '@/types'

export default function Cameras() {
  const cameras = useAppStore((state) => state.cameras)
  const setCameras = useAppStore((state) => state.setCameras)
  const updateCamera = useAppStore((state) => state.updateCamera)
  const deleteCamera = useAppStore((state) => state.deleteCamera)

  const [cameraStatuses, setCameraStatuses] = useState<Record<number, CameraStatus>>({})
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [selectedCamera, setSelectedCamera] = useState<Camera | null>(null)

  // Add camera form state
  const [newCameraName, setNewCameraName] = useState('')
  const [newCameraType, setNewCameraType] = useState<string>('')
  const [availableDevices, setAvailableDevices] = useState<DeviceInfo[]>([])
  const [selectedDevice, setSelectedDevice] = useState<string>('')
  const [isDiscovering, setIsDiscovering] = useState(false)
  const [isLoading, setIsLoading] = useState(false)

  // Edit camera state
  const [editCameraName, setEditCameraName] = useState('')

  // Fetch cameras on mount
  useEffect(() => {
    fetchCameras()
  }, [])

  // Poll camera statuses
  useEffect(() => {
    if (cameras.length === 0) return

    const fetchStatuses = async () => {
      const statusPromises = cameras.map(async (cam) => {
        try {
          const status = await api.get<CameraStatus>(`/cameras/status/${cam.id}`)
          return { id: cam.id, status }
        } catch {
          return { id: cam.id, status: { connected: false, error: 'Failed to fetch status' } }
        }
      })

      const results = await Promise.all(statusPromises)
      const statusMap: Record<number, CameraStatus> = {}
      results.forEach(({ id, status }) => {
        statusMap[id] = status
      })
      setCameraStatuses(statusMap)
    }

    fetchStatuses()
    const interval = setInterval(fetchStatuses, 3000)
    return () => clearInterval(interval)
  }, [cameras])

  const fetchCameras = async () => {
    try {
      const data = await api.get<Camera[]>('/api/cameras')
      setCameras(data)
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to fetch cameras',
      })
    }
  }

  const handleDiscoverDevices = async () => {
    if (!newCameraType) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Please select a camera type first',
      })
      return
    }

    setIsDiscovering(true)
    try {
      const devices = await api.get<DeviceInfo[]>('/cameras/discover', {
        params: { camera_type: newCameraType },
      })
      setAvailableDevices(devices)
      if (devices.length === 0) {
        toast({
          title: 'No devices found',
          description: `No ${newCameraType} cameras detected`,
        })
      }
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to discover devices',
      })
    } finally {
      setIsDiscovering(false)
    }
  }

  const handleAddCamera = async () => {
    if (!newCameraName || !newCameraType || !selectedDevice) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Please fill in all fields',
      })
      return
    }

    setIsLoading(true)
    try {
      const formData = new FormData()
      formData.append('name', newCameraName)
      formData.append('camera_type', newCameraType)
      formData.append('identifier', selectedDevice)

      await api.post('/cameras/add', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      toast({
        title: 'Camera added',
        description: `${newCameraName} successfully configured`,
      })

      setAddModalOpen(false)
      setNewCameraName('')
      setNewCameraType('')
      setSelectedDevice('')
      setAvailableDevices([])
      await fetchCameras()
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to add camera',
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleEditCamera = async () => {
    if (!selectedCamera || !editCameraName) return

    setIsLoading(true)
    try {
      const formData = new FormData()
      formData.append('name', editCameraName)

      await api.post(`/cameras/update/${selectedCamera.id}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      updateCamera(selectedCamera.id, { name: editCameraName })
      toast({
        title: 'Camera updated',
        description: 'Camera name changed successfully',
      })

      setEditModalOpen(false)
      setSelectedCamera(null)
      setEditCameraName('')
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to update camera',
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleDeleteCamera = async () => {
    if (!selectedCamera) return

    setIsLoading(true)
    try {
      await api.post(`/cameras/delete/${selectedCamera.id}`)
      deleteCamera(selectedCamera.id)
      toast({
        title: 'Camera deleted',
        description: `${selectedCamera.name} removed successfully`,
      })

      setDeleteModalOpen(false)
      setSelectedCamera(null)
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to delete camera',
      })
    } finally {
      setIsLoading(false)
    }
  }

  const openEditModal = (camera: Camera) => {
    setSelectedCamera(camera)
    setEditCameraName(camera.name)
    setEditModalOpen(true)
  }

  const openDeleteModal = (camera: Camera) => {
    setSelectedCamera(camera)
    setDeleteModalOpen(true)
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold mb-2">Cameras</h1>
          <p className="text-muted">Manage camera devices and configuration</p>
        </div>
        <Button data-testid="open-add-camera" onClick={() => setAddModalOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Add Camera
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Camera Devices</CardTitle>
          <CardDescription>
            Configured cameras and their connection status
          </CardDescription>
        </CardHeader>
        <CardContent>
          {cameras.length === 0 ? (
            <div className="text-center py-8" data-testid="camera-empty-state">
              <CameraIcon className="h-12 w-12 text-muted mx-auto mb-4 opacity-50" />
              <p className="text-muted">No cameras configured</p>
              <p className="text-sm text-subtle mt-1">
                Click "Add Camera" to get started
              </p>
            </div>
          ) : (
            <Table data-testid="camera-table">
              <TableHeader>
                <TableRow>
                  <TableHead data-testid="camera-header-name">Name</TableHead>
                  <TableHead data-testid="camera-header-type">Type</TableHead>
                  <TableHead data-testid="camera-header-identifier">Identifier</TableHead>
                  <TableHead data-testid="camera-header-status">Status</TableHead>
                  <TableHead data-testid="camera-header-actions" className="text-right">
                    Actions
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cameras.map((camera) => {
                  const status = cameraStatuses[camera.id]
                  return (
                    <TableRow
                      key={camera.id}
                      data-testid="camera-row"
                      data-camera-id={camera.id}
                      data-camera-name={camera.name}
                    >
                      <TableCell className="font-medium" data-testid="camera-name-cell">
                        {camera.name}
                      </TableCell>
                      <TableCell data-testid="camera-type-cell">{camera.camera_type}</TableCell>
                      <TableCell className="font-mono text-xs" data-testid="camera-identifier-cell">
                        {camera.identifier}
                      </TableCell>
                      <TableCell data-testid="camera-status-cell">
                        <StatusBadge
                          status={status?.connected ? 'online' : 'offline'}
                          label={status?.connected ? 'Connected' : 'Disconnected'}
                        />
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Edit ${camera.name}`}
                            data-testid={`camera-edit-${camera.id}`}
                            onClick={() => openEditModal(camera)}
                          >
                            <Edit2 className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Delete ${camera.name}`}
                            data-testid={`camera-delete-${camera.id}`}
                            onClick={() => openDeleteModal(camera)}
                          >
                            <Trash2 className="h-4 w-4 text-[var(--color-danger)]" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Add Camera Modal */}
      <Dialog open={addModalOpen} onOpenChange={setAddModalOpen}>
        <DialogContent className="max-w-md" data-testid="add-camera-dialog">
          <DialogHeader>
            <DialogTitle>Add Camera</DialogTitle>
            <DialogDescription>
              Configure a new camera device
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="camera-name">Camera Name</Label>
              <Input
                id="camera-name"
                value={newCameraName}
                onChange={(e) => setNewCameraName(e.target.value)}
                placeholder="Front Camera"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="camera-type">Camera Type</Label>
              <Select value={newCameraType} onValueChange={setNewCameraType}>
                <SelectTrigger id="camera-type" data-testid="camera-type-select">
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="USB">USB Camera</SelectItem>
                  <SelectItem value="GenICam">GenICam Camera</SelectItem>
                  <SelectItem value="OAK-D">OAK-D Camera</SelectItem>
                  <SelectItem value="RealSense">Intel RealSense</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>Available Devices</Label>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDiscoverDevices}
                  disabled={!newCameraType || isDiscovering}
                  data-testid="discover-devices"
                >
                  <RefreshCw className={`h-4 w-4 mr-2 ${isDiscovering ? 'animate-spin' : ''}`} />
                  {isDiscovering ? 'Discovering...' : 'Discover'}
                </Button>
              </div>

              {availableDevices.length > 0 ? (
                <Select value={selectedDevice} onValueChange={setSelectedDevice}>
                  <SelectTrigger data-testid="device-select">
                    <SelectValue placeholder="Select device" />
                  </SelectTrigger>
                  <SelectContent>
                    {availableDevices.map((device) => (
                      <SelectItem key={device.identifier} value={device.identifier}>
                        {device.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <p className="text-sm text-muted">
                  Click "Discover" to find available devices
                </p>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setAddModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleAddCamera} disabled={isLoading}>
              {isLoading ? 'Adding...' : 'Add Camera'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Camera Modal */}
      <Dialog open={editModalOpen} onOpenChange={setEditModalOpen}>
        <DialogContent className="max-w-md" data-testid="edit-camera-dialog">
          <DialogHeader>
            <DialogTitle>Edit Camera</DialogTitle>
            <DialogDescription>
              Change camera name
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="edit-camera-name">Camera Name</Label>
              <Input
                id="edit-camera-name"
                value={editCameraName}
                onChange={(e) => setEditCameraName(e.target.value)}
                placeholder="Camera name"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setEditModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleEditCamera} disabled={isLoading}>
              {isLoading ? 'Saving...' : 'Save Changes'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Modal */}
      <Dialog open={deleteModalOpen} onOpenChange={setDeleteModalOpen}>
        <DialogContent className="max-w-md" data-testid="delete-camera-dialog">
          <DialogHeader>
            <DialogTitle>Delete Camera</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{selectedCamera?.name}"? This will also remove
              all associated pipelines. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteCamera} disabled={isLoading}>
              {isLoading ? 'Deleting...' : 'Delete Camera'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
