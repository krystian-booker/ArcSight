/**
 * PipelineSelector component for selecting a pipeline from the list
 */

import { useQuery } from '@tanstack/react-query';
import { pipelineService } from '@/services';
import Select from './Select';
import Spinner from './Spinner';
import type { Pipeline } from '@/types';

interface PipelineSelectorProps {
  value?: number;
  onChange: (pipelineId: number | undefined) => void;
  cameraId?: number; // Optional: filter pipelines by camera
  label?: string;
  error?: string;
  placeholder?: string;
  includeNone?: boolean;
  disabled?: boolean;
}

export default function PipelineSelector({
  value,
  onChange,
  cameraId,
  label = 'Pipeline',
  error,
  placeholder = 'Select a pipeline',
  includeNone = true,
  disabled = false,
}: PipelineSelectorProps) {
  const { data: pipelines, isLoading, isError } = useQuery({
    queryKey: ['pipelines'],
    queryFn: () => pipelineService.listPipelines(),
    refetchInterval: 5000, // Refresh every 5 seconds
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
          <span className="text-sm text-arc-muted">Loading pipelines...</span>
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
          Failed to load pipelines
        </div>
      </div>
    );
  }

  // Filter pipelines by camera if cameraId is provided
  const filteredPipelines = cameraId
    ? (pipelines || []).filter((p: Pipeline) => p.camera_id === cameraId)
    : pipelines || [];

  // Build options list
  const options = [
    ...(includeNone ? [{ value: '', label: placeholder }] : []),
    ...filteredPipelines.map((pipeline: Pipeline) => ({
      value: pipeline.id.toString(),
      label: `${pipeline.name} (${pipeline.pipeline_type})`,
    })),
  ];

  const noPipelinesAvailable = filteredPipelines.length === 0;
  const placeholderText = noPipelinesAvailable
    ? cameraId
      ? 'No pipelines for this camera'
      : 'No pipelines available'
    : placeholder;

  return (
    <Select
      label={label}
      value={value?.toString() || ''}
      onChange={handleChange}
      options={options}
      error={error}
      disabled={disabled || noPipelinesAvailable}
      placeholder={placeholderText}
    />
  );
}
