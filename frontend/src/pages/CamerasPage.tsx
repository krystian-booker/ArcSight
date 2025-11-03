/**
 * CamerasPage - Camera management and configuration
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cameraService } from '@/services';
import { Panel, Button, Input, Select, Badge, VideoPlayer, Modal } from '@/components/common';
import { useToast } from '@/context';
import type { Camera } from '@/types';

export default function CamerasPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedCamera, setSelectedCamera] = useState<Camera | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  // Add camera form state
  const [newCamera, setNewCamera] = useState({
    name: '',
    type: 'USB',
    identifier: '',
  });

  // Fetch cameras list
  const { data: cameras, isLoading } = useQuery({
    queryKey: ['cameras'],
    queryFn: cameraService.listCameras,
    refetchInterval: 5000,
  });

  // Fetch camera status
  const { data: cameraStatuses } = useQuery({
    queryKey: ['cameras', 'status'],
    queryFn: cameraService.getAllCameraStatus,
    refetchInterval: 2000,
  });

  // Discover cameras mutation
  const discoverMutation = useMutation({
    mutationFn: cameraService.discoverCameras,
    onSuccess: () => {
      showToast('Camera discovery complete', 'success');
    },
    onError: () => {
      showToast('Failed to discover cameras', 'error');
    },
  });

  // Add camera mutation
  const addCameraMutation = useMutation({
    mutationFn: cameraService.addCamera,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cameras'] });
      setShowAddModal(false);
      setNewCamera({ name: '', type: 'USB', identifier: '' });
      showToast('Camera added successfully', 'success');
    },
    onError: () => {
      showToast('Failed to add camera', 'error');
    },
  });

  // Start camera mutation
  const startCameraMutation = useMutation({
    mutationFn: cameraService.startCamera,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cameras'] });
      showToast('Camera started', 'success');
    },
    onError: () => {
      showToast('Failed to start camera', 'error');
    },
  });

  // Stop camera mutation
  const stopCameraMutation = useMutation({
    mutationFn: cameraService.stopCamera,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cameras'] });
      showToast('Camera stopped', 'success');
    },
    onError: () => {
      showToast('Failed to stop camera', 'error');
    },
  });

  // Handle add camera
  const handleAddCamera = (e: React.FormEvent) => {
    e.preventDefault();
    addCameraMutation.mutate({
      camera_type: newCamera.type,
      identifier: newCamera.identifier,
      name: newCamera.name,
    });
  };

  // Get camera status
  const getCameraStatus = (cameraId: number) => {
    return cameraStatuses?.find((s) => s.id === cameraId);
  };

  return (
    <div className="p-lg max-w-arc mx-auto space-y-lg">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-arc-text">Cameras</h1>
          <p className="text-sm text-arc-muted mt-2xs">
            Manage camera devices and view live feeds
          </p>
        </div>
        <div className="flex gap-sm">
          <Button
            variant="secondary"
            onClick={() => discoverMutation.mutate()}
            loading={discoverMutation.isPending}
          >
            Discover Cameras
          </Button>
          <Button onClick={() => setShowAddModal(true)}>
            Add Camera
          </Button>
        </div>
      </div>

      {/* Cameras List */}
      {isLoading ? (
        <Panel>
          <div className="text-center py-xl text-arc-muted">
            Loading cameras...
          </div>
        </Panel>
      ) : cameras && cameras.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-lg">
          {cameras.map((camera) => {
            const status = getCameraStatus(camera.id);
            const isActive = status?.is_active || false;

            return (
              <Panel
                key={camera.id}
                title={
                  <div className="flex items-center justify-between w-full">
                    <span>{camera.name}</span>
                    <Badge variant={isActive ? 'success' : 'default'} dot>
                      {isActive ? 'Active' : 'Inactive'}
                    </Badge>
                  </div>
                }
                noPadding
              >
                <div className="p-lg space-y-md">
                  {/* Camera Info */}
                  <div className="grid grid-cols-2 gap-sm text-sm">
                    <div>
                      <span className="text-arc-muted">Type:</span>
                      <span className="ml-xs text-arc-text">{camera.camera_type}</span>
                    </div>
                    <div>
                      <span className="text-arc-muted">ID:</span>
                      <span className="ml-xs text-arc-text">{camera.identifier}</span>
                    </div>
                    {status?.fps && (
                      <div>
                        <span className="text-arc-muted">FPS:</span>
                        <span className="ml-xs text-arc-text">{status.fps.toFixed(1)}</span>
                      </div>
                    )}
                    {status?.resolution && (
                      <div>
                        <span className="text-arc-muted">Resolution:</span>
                        <span className="ml-xs text-arc-text">
                          {status.resolution.width}x{status.resolution.height}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Video Preview */}
                  {isActive && (
                    <div className="aspect-video bg-arc-surface rounded-arc-sm overflow-hidden">
                      <VideoPlayer
                        cameraId={camera.id}
                        streamType="raw"
                        className="w-full h-full"
                      />
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex gap-sm">
                    {isActive ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => stopCameraMutation.mutate(camera.id)}
                        loading={stopCameraMutation.isPending}
                        fullWidth
                      >
                        Stop
                      </Button>
                    ) : (
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => startCameraMutation.mutate(camera.id)}
                        loading={startCameraMutation.isPending}
                        fullWidth
                      >
                        Start
                      </Button>
                    )}
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => {
                        setSelectedCamera(camera);
                        setShowDeleteModal(true);
                      }}
                      fullWidth
                    >
                      Configure
                    </Button>
                  </div>
                </div>
              </Panel>
            );
          })}
        </div>
      ) : (
        <Panel>
          <div className="text-center py-xl">
            <p className="text-arc-muted mb-md">No cameras configured</p>
            <Button onClick={() => setShowAddModal(true)}>
              Add Your First Camera
            </Button>
          </div>
        </Panel>
      )}

      {/* Add Camera Modal */}
      <Modal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        title="Add Camera"
        size="md"
      >
        <form onSubmit={handleAddCamera} className="space-y-md">
          <Input
            label="Camera Name"
            value={newCamera.name}
            onChange={(e) => setNewCamera({ ...newCamera, name: e.target.value })}
            placeholder="e.g., Front Camera"
            required
          />

          <Select
            label="Camera Type"
            value={newCamera.type}
            onChange={(e) => setNewCamera({ ...newCamera, type: e.target.value })}
            options={[
              { value: 'USB', label: 'USB Camera' },
              { value: 'GenICam', label: 'GenICam / GigE' },
              { value: 'OAK-D', label: 'OAK-D' },
              { value: 'RealSense', label: 'Intel RealSense' },
            ]}
            required
          />

          <Input
            label="Camera Identifier"
            value={newCamera.identifier}
            onChange={(e) => setNewCamera({ ...newCamera, identifier: e.target.value })}
            placeholder="e.g., 0 for USB, serial for others"
            helperText="Device ID (0, 1, 2...) for USB cameras, or serial number for others"
            required
          />

          <div className="flex gap-sm justify-end pt-md">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setShowAddModal(false)}
            >
              Cancel
            </Button>
            <Button type="submit" loading={addCameraMutation.isPending}>
              Add Camera
            </Button>
          </div>
        </form>
      </Modal>

      {/* Delete/Configure Modal */}
      <Modal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
          setSelectedCamera(null);
        }}
        title={`Configure ${selectedCamera?.name}`}
        size="md"
      >
        {selectedCamera && (
          <div className="space-y-md">
            <div className="p-md bg-arc-surface rounded-arc-sm">
              <p className="text-sm text-arc-muted mb-xs">Camera Details</p>
              <p className="text-arc-text">
                Type: <span className="font-medium">{selectedCamera.camera_type}</span>
              </p>
              <p className="text-arc-text">
                ID: <span className="font-medium">{selectedCamera.identifier}</span>
              </p>
            </div>

            <div className="pt-md border-t border-arc-border">
              <p className="text-sm text-arc-subtle mb-md">
                Advanced configuration options coming soon...
              </p>
              <Button
                variant="secondary"
                onClick={() => {
                  setShowDeleteModal(false);
                  setSelectedCamera(null);
                }}
                fullWidth
              >
                Close
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
