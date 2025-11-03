/**
 * SettingsPage - Application settings and device control
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { settingsService } from '@/services';
import { Panel, Button, Input, Modal, Badge } from '@/components/common';
import { useToast } from '@/context';

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [showRestartModal, setShowRestartModal] = useState(false);
  const [showRebootModal, setShowRebootModal] = useState(false);
  const [showFactoryResetModal, setShowFactoryResetModal] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  // Fetch AprilTag fields
  const { data: fieldsData } = useQuery({
    queryKey: ['settings', 'apriltag-fields'],
    queryFn: settingsService.getAprilTagFields,
  });

  // Global settings form state
  const [teamNumber, setTeamNumber] = useState('');
  const [hostname, setHostname] = useState('');
  const [ipMode, setIpMode] = useState<'dhcp' | 'static'>('dhcp');

  // GenICam CTI path state
  const [ctiPath, setCtiPath] = useState('');

  // Update global settings mutation
  const updateGlobalMutation = useMutation({
    mutationFn: settingsService.updateGlobalSettings,
    onSuccess: () => {
      showToast('Global settings updated successfully', 'success');
    },
    onError: () => {
      showToast('Failed to update global settings', 'error');
    },
  });

  // Update GenICam settings mutation
  const updateGenICamMutation = useMutation({
    mutationFn: settingsService.updateGenICamSettings,
    onSuccess: () => {
      showToast('GenICam CTI path updated successfully', 'success');
    },
    onError: () => {
      showToast('Failed to update GenICam settings', 'error');
    },
  });

  // Clear GenICam settings mutation
  const clearGenICamMutation = useMutation({
    mutationFn: settingsService.clearGenICamSettings,
    onSuccess: () => {
      setCtiPath('');
      showToast('GenICam CTI path cleared', 'success');
    },
    onError: () => {
      showToast('Failed to clear GenICam settings', 'error');
    },
  });

  // Select AprilTag field mutation
  const selectFieldMutation = useMutation({
    mutationFn: settingsService.selectAprilTagField,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'apriltag-fields'] });
      showToast('AprilTag field selected', 'success');
    },
    onError: () => {
      showToast('Failed to select AprilTag field', 'error');
    },
  });

  // Delete AprilTag field mutation
  const deleteFieldMutation = useMutation({
    mutationFn: settingsService.deleteAprilTagField,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'apriltag-fields'] });
      showToast('AprilTag field deleted', 'success');
    },
    onError: () => {
      showToast('Failed to delete AprilTag field', 'error');
    },
  });

  // Upload AprilTag field mutation
  const uploadFieldMutation = useMutation({
    mutationFn: (file: File) =>
      settingsService.uploadAprilTagField(file, (progress) => setUploadProgress(progress)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'apriltag-fields'] });
      showToast('AprilTag field uploaded successfully', 'success');
      setUploadProgress(0);
    },
    onError: () => {
      showToast('Failed to upload AprilTag field', 'error');
      setUploadProgress(0);
    },
  });

  // Restart application mutation
  const restartMutation = useMutation({
    mutationFn: settingsService.restartApplication,
    onSuccess: () => {
      showToast('Application restart initiated', 'info');
      setShowRestartModal(false);
    },
    onError: () => {
      showToast('Failed to restart application', 'error');
    },
  });

  // Reboot device mutation
  const rebootMutation = useMutation({
    mutationFn: settingsService.rebootDevice,
    onSuccess: () => {
      showToast('Device reboot initiated', 'info');
      setShowRebootModal(false);
    },
    onError: () => {
      showToast('Failed to reboot device', 'error');
    },
  });

  // Factory reset mutation
  const factoryResetMutation = useMutation({
    mutationFn: settingsService.factoryReset,
    onSuccess: () => {
      showToast('Factory reset complete', 'info');
      setShowFactoryResetModal(false);
      queryClient.clear(); // Clear all cached data
    },
    onError: () => {
      showToast('Failed to perform factory reset', 'error');
    },
  });

  // Handle global settings submit
  const handleGlobalSettingsSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateGlobalMutation.mutate({
      team_number: teamNumber ? parseInt(teamNumber, 10) : undefined,
      hostname: hostname || undefined,
      ip_mode: ipMode,
    });
  };

  // Handle GenICam settings submit
  const handleGenICamSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateGenICamMutation.mutate(ctiPath);
  };

  // Handle AprilTag field upload
  const handleFieldUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadFieldMutation.mutate(file);
    }
  };

  return (
    <div className="p-lg max-w-arc mx-auto space-y-lg">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-arc-text">Settings</h1>
        <p className="text-sm text-arc-muted mt-2xs">
          Configure application settings and manage device
        </p>
      </div>

      {/* Global Settings */}
      <Panel title="Global Settings">
        <form onSubmit={handleGlobalSettingsSubmit} className="space-y-md">
          <Input
            label="Team Number"
            type="number"
            value={teamNumber}
            onChange={(e) => setTeamNumber(e.target.value)}
            placeholder="Enter team number"
          />

          <Input
            label="Hostname"
            value={hostname}
            onChange={(e) => setHostname(e.target.value)}
            placeholder="Enter hostname"
          />

          <div>
            <label className="mb-2xs block text-sm font-medium text-arc-text">
              IP Mode
            </label>
            <div className="flex gap-md">
              <label className="flex items-center gap-xs cursor-pointer">
                <input
                  type="radio"
                  value="dhcp"
                  checked={ipMode === 'dhcp'}
                  onChange={(e) => setIpMode(e.target.value as 'dhcp' | 'static')}
                  className="text-arc-primary focus:ring-arc-teal"
                />
                <span className="text-sm text-arc-text">DHCP</span>
              </label>
              <label className="flex items-center gap-xs cursor-pointer">
                <input
                  type="radio"
                  value="static"
                  checked={ipMode === 'static'}
                  onChange={(e) => setIpMode(e.target.value as 'dhcp' | 'static')}
                  className="text-arc-primary focus:ring-arc-teal"
                />
                <span className="text-sm text-arc-text">Static</span>
              </label>
            </div>
          </div>

          <Button type="submit" loading={updateGlobalMutation.isPending}>
            Save Global Settings
          </Button>
        </form>
      </Panel>

      {/* GenICam Settings */}
      <Panel title="GenICam Settings">
        <form onSubmit={handleGenICamSubmit} className="space-y-md">
          <Input
            label="CTI File Path"
            value={ctiPath}
            onChange={(e) => setCtiPath(e.target.value)}
            placeholder="/path/to/cti/file.cti"
            helperText="Path to GenICam CTI file for industrial camera support"
          />

          <div className="flex gap-sm">
            <Button type="submit" loading={updateGenICamMutation.isPending}>
              Update CTI Path
            </Button>
            <Button
              variant="secondary"
              onClick={() => clearGenICamMutation.mutate()}
              loading={clearGenICamMutation.isPending}
            >
              Clear Path
            </Button>
          </div>
        </form>
      </Panel>

      {/* AprilTag Field Layouts */}
      <Panel title="AprilTag Field Layouts">
        <div className="space-y-md">
          {/* Current field */}
          {fieldsData && (
            <div className="mb-md">
              <p className="text-sm text-arc-muted mb-xs">Current Field:</p>
              <Badge variant="info" size="lg">
                {fieldsData.selected_field || 'None selected'}
              </Badge>
            </div>
          )}

          {/* Available fields */}
          <div>
            <p className="text-sm font-medium text-arc-text mb-sm">Available Fields:</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-sm">
              {fieldsData?.available_fields.map((field) => (
                <div
                  key={field}
                  className="flex items-center justify-between p-sm bg-arc-surface rounded-arc-sm border border-arc-border"
                >
                  <span className="text-sm text-arc-text">{field}</span>
                  <div className="flex gap-xs">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => selectFieldMutation.mutate(field)}
                      disabled={field === fieldsData.selected_field}
                    >
                      {field === fieldsData.selected_field ? 'Selected' : 'Select'}
                    </Button>
                    {fieldsData.custom_fields.includes(field) && (
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() => deleteFieldMutation.mutate(field)}
                      >
                        Delete
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Upload custom field */}
          <div>
            <label className="block">
              <span className="text-sm font-medium text-arc-text mb-xs block">
                Upload Custom Field
              </span>
              <input
                type="file"
                accept=".json"
                onChange={handleFieldUpload}
                className="block w-full text-sm text-arc-text
                  file:mr-md file:py-xs file:px-sm
                  file:rounded-arc-sm file:border-0
                  file:text-sm file:font-medium
                  file:bg-arc-primary file:text-white
                  hover:file:bg-opacity-90 file:cursor-pointer
                  cursor-pointer"
              />
            </label>
            {uploadProgress > 0 && uploadProgress < 100 && (
              <div className="mt-sm">
                <div className="w-full bg-arc-surface h-2 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-arc-primary transition-all duration-arc"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <p className="text-xs text-arc-muted mt-xs">Uploading: {uploadProgress}%</p>
              </div>
            )}
          </div>
        </div>
      </Panel>

      {/* Database Management */}
      <Panel title="Database Management">
        <div className="space-y-sm">
          <Button
            variant="secondary"
            onClick={() => settingsService.exportDatabase()}
            fullWidth
          >
            Export Database
          </Button>

          <label className="block">
            <Button variant="secondary" fullWidth>
              Import Database
            </Button>
            <input
              type="file"
              accept=".db"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  settingsService.importDatabase(file).then(() => {
                    showToast('Database imported successfully', 'success');
                    queryClient.clear();
                  });
                }
              }}
              className="hidden"
            />
          </label>
        </div>
      </Panel>

      {/* Device Control */}
      <Panel title="Device Control">
        <div className="space-y-sm">
          <Button
            variant="secondary"
            onClick={() => setShowRestartModal(true)}
            fullWidth
          >
            Restart Application
          </Button>

          <Button
            variant="secondary"
            onClick={() => setShowRebootModal(true)}
            fullWidth
          >
            Reboot Device
          </Button>

          <Button
            variant="danger"
            onClick={() => setShowFactoryResetModal(true)}
            fullWidth
          >
            Factory Reset
          </Button>
        </div>
      </Panel>

      {/* Restart Modal */}
      <Modal
        isOpen={showRestartModal}
        onClose={() => setShowRestartModal(false)}
        title="Restart Application"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowRestartModal(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={() => restartMutation.mutate()}
              loading={restartMutation.isPending}
            >
              Restart
            </Button>
          </>
        }
      >
        <p className="text-arc-text">
          Are you sure you want to restart the application? This will disconnect all active
          connections.
        </p>
      </Modal>

      {/* Reboot Modal */}
      <Modal
        isOpen={showRebootModal}
        onClose={() => setShowRebootModal(false)}
        title="Reboot Device"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowRebootModal(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={() => rebootMutation.mutate()}
              loading={rebootMutation.isPending}
            >
              Reboot
            </Button>
          </>
        }
      >
        <p className="text-arc-text">
          Are you sure you want to reboot the device? This will take a few minutes.
        </p>
      </Modal>

      {/* Factory Reset Modal */}
      <Modal
        isOpen={showFactoryResetModal}
        onClose={() => setShowFactoryResetModal(false)}
        title="Factory Reset"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowFactoryResetModal(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={() => factoryResetMutation.mutate()}
              loading={factoryResetMutation.isPending}
            >
              Factory Reset
            </Button>
          </>
        }
      >
        <div className="space-y-sm">
          <p className="text-arc-text font-medium">
            WARNING: This will delete all settings, cameras, pipelines, and calibration data!
          </p>
          <p className="text-arc-subtle text-sm">This action cannot be undone.</p>
        </div>
      </Modal>
    </div>
  );
}
