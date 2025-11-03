/**
 * CameraSelector component for selecting a camera from the list
 */

import { useQuery } from '@tanstack/react-query';
import { cameraService } from '@/services';
import Select from './Select';
import Spinner from './Spinner';
import type { Camera } from '@/types';

interface CameraSelectorProps {
  value?: number;
  onChange: (cameraId: number | undefined) => void;
  label?: string;
  error?: string;
  placeholder?: string;
  includeNone?: boolean;
  disabled?: boolean;
}

export default function CameraSelector({
  value,
  onChange,
  label = 'Camera',
  error,
  placeholder = 'Select a camera',
  includeNone = true,
  disabled = false,
}: CameraSelectorProps) {
  const { data: cameras, isLoading, isError } = useQuery({
    queryKey: ['cameras'],
    queryFn: cameraService.listCameras,
    refetchInterval: 5000, // Refresh every 5 seconds to get latest camera status
  });

  // Handle selection change
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const selectedValue = e.target.value;
    if (selectedValue === '') {
      onChange(undefined);
    } else {
      onChange(parseInt(selectedValue, 10));
    }
  };

  // Show loading state
  if (isLoading) {
    return (
      <div className="w-full">
        {label && (
          <label className="mb-2xs block text-sm font-medium text-arc-text">
            {label}
          </label>
        )}
        <div className="flex items-center gap-sm p-sm bg-arc-surface rounded-arc-sm border border-arc-border">
          <Spinner size="sm" />
          <span className="text-sm text-arc-muted">Loading cameras...</span>
        </div>
      </div>
    );
  }

  // Show error state
  if (isError) {
    return (
      <div className="w-full">
        {label && (
          <label className="mb-2xs block text-sm font-medium text-arc-text">
            {label}
          </label>
        )}
        <div className="p-sm bg-arc-danger bg-opacity-10 rounded-arc-sm border border-arc-danger text-arc-danger text-sm">
          Failed to load cameras
        </div>
      </div>
    );
  }

  // Build options list
  const options = [
    ...(includeNone ? [{ value: '', label: placeholder }] : []),
    ...(cameras || []).map((camera: Camera) => ({
      value: camera.id.toString(),
      label: `${camera.name} (${camera.camera_type})`,
    })),
  ];

  return (
    <Select
      label={label}
      value={value?.toString() || ''}
      onChange={handleChange}
      options={options}
      error={error}
      disabled={disabled || !cameras || cameras.length === 0}
      placeholder={cameras && cameras.length === 0 ? 'No cameras available' : placeholder}
    />
  );
}
