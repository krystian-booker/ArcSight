/**
 * CalibrationPage - Camera calibration workflow
 */

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { calibrationService } from '@/services';
import {
  Panel,
  Button,
  Input,
  Select,
  VideoPlayer,
  CameraSelector,
  Badge,
} from '@/components/common';
import { useToast } from '@/context';
import type { PatternType } from '@/types';

export default function CalibrationPage() {
  const { showToast } = useToast();

  // Calibration state
  const [selectedCamera, setSelectedCamera] = useState<number | undefined>();
  const [patternType, setPatternType] = useState<PatternType>('chessboard');
  const [rows, setRows] = useState('7');
  const [cols, setCols] = useState('9');
  const [squareSize, setSquareSize] = useState('25');
  const [markerSize, setMarkerSize] = useState('19');
  const [dictionary, setDictionary] = useState('DICT_4X4_50');

  const [isSessionActive, setIsSessionActive] = useState(false);
  const [capturedFrames, setCapturedFrames] = useState(0);
  const [calibrationResult, setCalibrationResult] = useState<any>(null);

  // Generate pattern mutation
  const generatePatternMutation = useMutation({
    mutationFn: async () => {
      if (patternType === 'chessboard') {
        await calibrationService.generateChessboardPattern({
          rows: parseInt(rows),
          cols: parseInt(cols),
          square_size_mm: parseInt(squareSize),
        });
      } else {
        await calibrationService.generateCharucoPattern({
          rows: parseInt(rows),
          cols: parseInt(cols),
          square_size_mm: parseInt(squareSize),
          marker_size_mm: parseInt(markerSize),
          dictionary,
        });
      }
    },
    onSuccess: () => {
      showToast('Pattern generated and downloaded', 'success');
    },
    onError: () => {
      showToast('Failed to generate pattern', 'error');
    },
  });

  // Start calibration mutation
  const startCalibrationMutation = useMutation({
    mutationFn: async () => {
      if (!selectedCamera) throw new Error('No camera selected');

      return calibrationService.startCalibration({
        camera_id: selectedCamera,
        pattern_type: patternType,
        rows: parseInt(rows),
        cols: parseInt(cols),
        square_size_mm: parseInt(squareSize),
        marker_size_mm: patternType === 'charuco' ? parseInt(markerSize) : undefined,
        dictionary: patternType === 'charuco' ? dictionary : undefined,
      });
    },
    onSuccess: () => {
      setIsSessionActive(true);
      setCapturedFrames(0);
      setCalibrationResult(null);
      showToast('Calibration session started', 'success');
    },
    onError: () => {
      showToast('Failed to start calibration', 'error');
    },
  });

  // Capture frame mutation
  const captureFrameMutation = useMutation({
    mutationFn: async () => {
      if (!selectedCamera) throw new Error('No camera selected');
      return calibrationService.captureCalibrationFrame(selectedCamera);
    },
    onSuccess: (data) => {
      setCapturedFrames(data.total_frames_captured);
      showToast(
        data.pattern_detected
          ? `Frame ${data.total_frames_captured} captured successfully`
          : 'Pattern not detected - try a different angle',
        data.pattern_detected ? 'success' : 'warning'
      );
    },
    onError: () => {
      showToast('Failed to capture frame', 'error');
    },
  });

  // Calculate calibration mutation
  const calculateCalibrationMutation = useMutation({
    mutationFn: async () => {
      if (!selectedCamera) throw new Error('No camera selected');
      return calibrationService.calculateCalibration(selectedCamera);
    },
    onSuccess: (data) => {
      setCalibrationResult(data);
      showToast(
        `Calibration calculated (error: ${data.reprojection_error.toFixed(3)})`,
        'success'
      );
    },
    onError: () => {
      showToast('Failed to calculate calibration', 'error');
    },
  });

  // Save calibration mutation
  const saveCalibrationMutation = useMutation({
    mutationFn: async () => {
      if (!selectedCamera) throw new Error('No camera selected');
      return calibrationService.saveCalibration(selectedCamera);
    },
    onSuccess: () => {
      setIsSessionActive(false);
      showToast('Calibration saved successfully', 'success');
    },
    onError: () => {
      showToast('Failed to save calibration', 'error');
    },
  });

  return (
    <div className="p-lg max-w-arc mx-auto space-y-lg">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-arc-text">Camera Calibration</h1>
        <p className="text-sm text-arc-muted mt-2xs">
          Calibrate camera intrinsics for accurate pose estimation
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-lg">
        {/* Configuration Panel */}
        <div className="lg:col-span-1 space-y-lg">
          {/* Camera Selection */}
          <Panel title="Camera Selection">
            <CameraSelector
              value={selectedCamera}
              onChange={setSelectedCamera}
              includeNone={false}
              disabled={isSessionActive}
            />
          </Panel>

          {/* Pattern Configuration */}
          <Panel title="Pattern Configuration">
            <div className="space-y-md">
              <Select
                label="Pattern Type"
                value={patternType}
                onChange={(e) => setPatternType(e.target.value as PatternType)}
                options={[
                  { value: 'chessboard', label: 'Chessboard' },
                  { value: 'charuco', label: 'ChArUco Board' },
                ]}
                disabled={isSessionActive}
              />

              <div className="grid grid-cols-2 gap-sm">
                <Input
                  label="Rows"
                  type="number"
                  value={rows}
                  onChange={(e) => setRows(e.target.value)}
                  min={3}
                  disabled={isSessionActive}
                />
                <Input
                  label="Columns"
                  type="number"
                  value={cols}
                  onChange={(e) => setCols(e.target.value)}
                  min={3}
                  disabled={isSessionActive}
                />
              </div>

              <Input
                label="Square Size (mm)"
                type="number"
                value={squareSize}
                onChange={(e) => setSquareSize(e.target.value)}
                min={1}
                disabled={isSessionActive}
              />

              {patternType === 'charuco' && (
                <>
                  <Input
                    label="Marker Size (mm)"
                    type="number"
                    value={markerSize}
                    onChange={(e) => setMarkerSize(e.target.value)}
                    min={1}
                    disabled={isSessionActive}
                  />

                  <Select
                    label="ArUco Dictionary"
                    value={dictionary}
                    onChange={(e) => setDictionary(e.target.value)}
                    options={[
                      { value: 'DICT_4X4_50', label: '4x4 (50 markers)' },
                      { value: 'DICT_5X5_50', label: '5x5 (50 markers)' },
                      { value: 'DICT_6X6_50', label: '6x6 (50 markers)' },
                      { value: 'DICT_7X7_50', label: '7x7 (50 markers)' },
                    ]}
                    disabled={isSessionActive}
                  />
                </>
              )}

              <Button
                variant="secondary"
                fullWidth
                onClick={() => generatePatternMutation.mutate()}
                loading={generatePatternMutation.isPending}
                disabled={isSessionActive}
              >
                Generate & Download Pattern
              </Button>
            </div>
          </Panel>

          {/* Session Status */}
          {isSessionActive && (
            <Panel title="Session Status">
              <div className="space-y-sm">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-arc-muted">Status:</span>
                  <Badge variant="success" dot>
                    Active
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-arc-muted">Frames Captured:</span>
                  <Badge variant="info">{capturedFrames}</Badge>
                </div>
                {calibrationResult && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-arc-muted">Reprojection Error:</span>
                    <Badge
                      variant={
                        calibrationResult.reprojection_error < 0.5
                          ? 'success'
                          : calibrationResult.reprojection_error < 1.0
                          ? 'warning'
                          : 'danger'
                      }
                    >
                      {calibrationResult.reprojection_error.toFixed(3)}
                    </Badge>
                  </div>
                )}
              </div>
            </Panel>
          )}
        </div>

        {/* Video Feed and Actions */}
        <div className="lg:col-span-2 space-y-lg">
          {/* Video Feed */}
          <Panel title="Calibration Feed" noPadding>
            {selectedCamera ? (
              <div className="aspect-video bg-arc-surface">
                <VideoPlayer
                  cameraId={selectedCamera}
                  streamType="calibration"
                  className="w-full h-full"
                />
              </div>
            ) : (
              <div className="aspect-video flex items-center justify-center bg-arc-surface text-arc-muted">
                Select a camera to begin
              </div>
            )}
          </Panel>

          {/* Actions */}
          <Panel title="Calibration Actions">
            {!isSessionActive ? (
              <Button
                onClick={() => startCalibrationMutation.mutate()}
                loading={startCalibrationMutation.isPending}
                disabled={!selectedCamera}
                fullWidth
              >
                Start Calibration Session
              </Button>
            ) : (
              <div className="space-y-sm">
                <Button
                  onClick={() => captureFrameMutation.mutate()}
                  loading={captureFrameMutation.isPending}
                  fullWidth
                >
                  Capture Frame ({capturedFrames} captured)
                </Button>

                <Button
                  variant="secondary"
                  onClick={() => calculateCalibrationMutation.mutate()}
                  loading={calculateCalibrationMutation.isPending}
                  disabled={capturedFrames < 10}
                  fullWidth
                >
                  Calculate Calibration
                </Button>

                {calibrationResult && (
                  <Button
                    variant="primary"
                    onClick={() => saveCalibrationMutation.mutate()}
                    loading={saveCalibrationMutation.isPending}
                    fullWidth
                  >
                    Save Calibration
                  </Button>
                )}
              </div>
            )}
          </Panel>

          {/* Instructions */}
          <Panel title="Instructions">
            <div className="space-y-sm text-sm text-arc-text">
              <ol className="list-decimal list-inside space-y-xs">
                <li>Print the calibration pattern and mount it on a flat surface</li>
                <li>Select your camera and configure the pattern parameters</li>
                <li>Start a calibration session</li>
                <li>Capture 15-20 frames from different angles and distances</li>
                <li>Ensure the pattern is fully visible in each frame</li>
                <li>Calculate calibration once you have enough frames</li>
                <li>Review the reprojection error (lower is better, {'<'}0.5 is excellent)</li>
                <li>Save the calibration to apply it to the camera</li>
              </ol>
              <p className="text-arc-subtle text-xs pt-sm">
                Tip: Vary the pattern's position (center, corners, tilted) for best results
              </p>
            </div>
          </Panel>

          {/* Calibration Results */}
          {calibrationResult && (
            <Panel title="Calibration Results">
              <div className="space-y-sm">
                <div className="grid grid-cols-2 gap-md text-sm">
                  <div>
                    <p className="text-arc-muted mb-3xs">Focal Length X:</p>
                    <p className="text-arc-text font-mono">
                      {calibrationResult.camera_matrix[0][0].toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <p className="text-arc-muted mb-3xs">Focal Length Y:</p>
                    <p className="text-arc-text font-mono">
                      {calibrationResult.camera_matrix[1][1].toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <p className="text-arc-muted mb-3xs">Principal Point X:</p>
                    <p className="text-arc-text font-mono">
                      {calibrationResult.camera_matrix[0][2].toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <p className="text-arc-muted mb-3xs">Principal Point Y:</p>
                    <p className="text-arc-text font-mono">
                      {calibrationResult.camera_matrix[1][2].toFixed(2)}
                    </p>
                  </div>
                </div>
                <div className="pt-sm border-t border-arc-border">
                  <p className="text-arc-muted mb-xs text-sm">Distortion Coefficients:</p>
                  <p className="text-arc-text font-mono text-xs">
                    [{calibrationResult.dist_coeffs.map((v: number) => v.toFixed(4)).join(', ')}]
                  </p>
                </div>
              </div>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
