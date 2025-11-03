/**
 * DashboardPage - Main dashboard with video feeds and pipeline controls
 */

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cameraService, pipelineService } from '@/services';
import {
  Panel,
  Badge,
  VideoPlayer,
  CameraSelector,
  PipelineSelector,
  Button,
  Spinner,
} from '@/components/common';
import { useToast } from '@/context';
import type { Pipeline } from '@/types';

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const [selectedCamera, setSelectedCamera] = useState<number | undefined>();
  const [selectedPipeline, setSelectedPipeline] = useState<number | undefined>();
  const [showProcessed, setShowProcessed] = useState(true);

  // Fetch cameras
  const { data: cameras } = useQuery({
    queryKey: ['cameras'],
    queryFn: cameraService.listCameras,
    refetchInterval: 5000,
  });

  // Fetch pipelines
  const { data: pipelines } = useQuery({
    queryKey: ['pipelines'],
    queryFn: () => pipelineService.listPipelines(),
    refetchInterval: 5000,
  });

  // Fetch pipeline results for selected pipeline
  const { data: pipelineResults, isLoading: resultsLoading } = useQuery({
    queryKey: ['pipeline-results', selectedPipeline],
    queryFn: () => {
      if (!selectedPipeline) return null;
      return pipelineService.getPipelineResults(selectedPipeline);
    },
    enabled: !!selectedPipeline,
    refetchInterval: 500, // Update frequently for real-time data
  });

  // Auto-select first camera and pipeline on load
  useEffect(() => {
    if (cameras && cameras.length > 0 && !selectedCamera) {
      setSelectedCamera(cameras[0].id);
    }
  }, [cameras, selectedCamera]);

  useEffect(() => {
    if (pipelines && pipelines.length > 0 && !selectedPipeline) {
      setSelectedPipeline(pipelines[0].id);
    }
  }, [pipelines, selectedPipeline]);

  // Get selected pipeline details
  const pipeline = pipelines?.find((p: Pipeline) => p.id === selectedPipeline);

  // Start pipeline mutation
  const startPipelineMutation = useMutation({
    mutationFn: (pipelineId: number) => pipelineService.startPipeline(pipelineId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
      showToast('Pipeline started', 'success');
    },
    onError: () => {
      showToast('Failed to start pipeline', 'error');
    },
  });

  // Stop pipeline mutation
  const stopPipelineMutation = useMutation({
    mutationFn: (pipelineId: number) => pipelineService.stopPipeline(pipelineId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
      showToast('Pipeline stopped', 'success');
    },
    onError: () => {
      showToast('Failed to stop pipeline', 'error');
    },
  });

  // Render pipeline results based on type
  const renderResults = () => {
    if (!pipelineResults || !pipelineResults.detections) {
      return (
        <p className="text-sm text-arc-subtle text-center py-md">
          No detection data available
        </p>
      );
    }

    const { detections } = pipelineResults;

    if (pipeline?.pipeline_type === 'apriltag') {
      return (
        <div className="space-y-xs">
          <p className="text-xs text-arc-muted mb-sm">
            Detected Tags: {detections.length}
          </p>
          {detections.map((detection: any, idx: number) => (
            <div
              key={idx}
              className="p-sm bg-arc-surface rounded text-xs font-mono space-y-3xs"
            >
              <div className="flex justify-between">
                <span className="text-arc-muted">ID:</span>
                <Badge size="sm" variant="info">
                  {detection.tag_id}
                </Badge>
              </div>
              {detection.pose && (
                <>
                  <div className="flex justify-between">
                    <span className="text-arc-muted">X:</span>
                    <span className="text-arc-text">{detection.pose.x?.toFixed(2)} m</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-arc-muted">Y:</span>
                    <span className="text-arc-text">{detection.pose.y?.toFixed(2)} m</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-arc-muted">Z:</span>
                    <span className="text-arc-text">{detection.pose.z?.toFixed(2)} m</span>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      );
    }

    if (pipeline?.pipeline_type === 'coloured_shape') {
      return (
        <div className="space-y-xs">
          <p className="text-xs text-arc-muted mb-sm">
            Detected Shapes: {detections.length}
          </p>
          {detections.map((detection: any, idx: number) => (
            <div
              key={idx}
              className="p-sm bg-arc-surface rounded text-xs space-y-3xs"
            >
              <div className="flex justify-between">
                <span className="text-arc-muted">Color:</span>
                <Badge size="sm" variant="info">
                  {detection.color}
                </Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-arc-muted">Shape:</span>
                <span className="text-arc-text">{detection.shape}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-arc-muted">Area:</span>
                <span className="text-arc-text">{detection.area}</span>
              </div>
            </div>
          ))}
        </div>
      );
    }

    if (pipeline?.pipeline_type === 'object_detection_ml') {
      return (
        <div className="space-y-xs">
          <p className="text-xs text-arc-muted mb-sm">
            Detected Objects: {detections.length}
          </p>
          {detections.map((detection: any, idx: number) => (
            <div
              key={idx}
              className="p-sm bg-arc-surface rounded text-xs space-y-3xs"
            >
              <div className="flex justify-between">
                <span className="text-arc-muted">Class:</span>
                <Badge size="sm" variant="info">
                  {detection.class_name}
                </Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-arc-muted">Confidence:</span>
                <span className="text-arc-text">
                  {(detection.confidence * 100).toFixed(1)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      );
    }

    return null;
  };

  return (
    <div className="p-lg h-full flex flex-col">
      {/* Header */}
      <div className="mb-lg">
        <h1 className="text-2xl font-bold text-arc-text">Dashboard</h1>
        <p className="text-sm text-arc-muted mt-2xs">
          Monitor camera feeds and pipeline detections in real-time
        </p>
      </div>

      {/* Main Content */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-4 gap-lg min-h-0">
        {/* Video Feed - Takes 3 columns on large screens */}
        <div className="lg:col-span-3 flex flex-col min-h-0">
          <Panel title="Video Feed" className="flex-1 flex flex-col" noPadding>
            <div className="flex-1 bg-arc-surface relative">
              {selectedCamera && selectedPipeline ? (
                <>
                  {/* Toggle between raw and processed */}
                  <div className="absolute top-md right-md z-10 flex gap-xs">
                    <Button
                      size="sm"
                      variant={!showProcessed ? 'primary' : 'secondary'}
                      onClick={() => setShowProcessed(false)}
                    >
                      Raw
                    </Button>
                    <Button
                      size="sm"
                      variant={showProcessed ? 'primary' : 'secondary'}
                      onClick={() => setShowProcessed(true)}
                    >
                      Processed
                    </Button>
                  </div>

                  {/* Video player */}
                  <VideoPlayer
                    cameraId={showProcessed ? undefined : selectedCamera}
                    pipelineId={showProcessed ? selectedPipeline : undefined}
                    streamType={showProcessed ? 'processed' : 'raw'}
                    className="w-full h-full"
                  />
                </>
              ) : (
                <div className="flex items-center justify-center h-full text-arc-muted">
                  {!selectedCamera && <p>Select a camera to view feed</p>}
                  {selectedCamera && !selectedPipeline && <p>Select a pipeline to view processed feed</p>}
                </div>
              )}
            </div>
          </Panel>
        </div>

        {/* Control Panel - Takes 1 column on large screens */}
        <div className="lg:col-span-1 flex flex-col gap-lg">
          {/* Camera Selection */}
          <Panel title="Camera">
            <CameraSelector
              value={selectedCamera}
              onChange={setSelectedCamera}
              includeNone={false}
            />
          </Panel>

          {/* Pipeline Selection */}
          <Panel title="Pipeline">
            <div className="space-y-sm">
              <PipelineSelector
                value={selectedPipeline}
                onChange={setSelectedPipeline}
                cameraId={selectedCamera}
                includeNone={false}
              />

              {pipeline && (
                <div className="pt-sm space-y-xs">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-arc-muted">Type:</span>
                    <Badge variant="info" size="sm">
                      {pipeline.pipeline_type}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-arc-muted">Status:</span>
                    <Badge
                      variant={pipeline.is_active ? 'success' : 'default'}
                      size="sm"
                      dot
                    >
                      {pipeline.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </div>

                  {/* Pipeline Controls */}
                  <div className="pt-sm">
                    {pipeline.is_active ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        fullWidth
                        onClick={() => stopPipelineMutation.mutate(pipeline.id)}
                        loading={stopPipelineMutation.isPending}
                      >
                        Stop Pipeline
                      </Button>
                    ) : (
                      <Button
                        variant="primary"
                        size="sm"
                        fullWidth
                        onClick={() => startPipelineMutation.mutate(pipeline.id)}
                        loading={startPipelineMutation.isPending}
                      >
                        Start Pipeline
                      </Button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </Panel>

          {/* Detection Results */}
          {selectedPipeline && (
            <Panel title="Detections" className="flex-1">
              {resultsLoading ? (
                <div className="flex items-center justify-center py-lg">
                  <Spinner />
                </div>
              ) : (
                renderResults()
              )}
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
