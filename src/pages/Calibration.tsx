import { useState, useEffect } from 'react'
import { Download, Camera as CameraIcon, CheckCircle2 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
import { MJPEGStream } from '@/components/shared'
import { toast } from '@/hooks/use-toast'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/useAppStore'
import type { Camera, CalibrationResult } from '@/types'

type CalibrationStep = 'setup' | 'capture' | 'results'

const SETTINGS_STORAGE_KEY = 'calibration.settings.v1'
const MIN_CORNERS = 3

const clampIntString = (value: string, min: number, max: number): string => {
  const parsed = parseInt(value, 10)
  if (Number.isNaN(parsed)) {
    return min.toString()
  }
  const clamped = Math.min(Math.max(parsed, min), max)
  return clamped.toString()
}

const clampFloatString = (value: string, min: number, max: number): string => {
  const parsed = parseFloat(value)
  if (Number.isNaN(parsed)) {
    return min.toString()
  }
  const clamped = Math.min(Math.max(parsed, min), max)
  return clamped.toString()
}

export default function Calibration() {
  const cameras = useAppStore((state) => state.cameras)

  const [step, setStep] = useState<CalibrationStep>('setup')
  const [selectedCameraId, setSelectedCameraId] = useState<string>('')
  const [patternType, setPatternType] = useState<'chessboard' | 'charuco'>('charuco')
  const [innerCornersWidth, setInnerCornersWidth] = useState('7')
  const [innerCornersHeight, setInnerCornersHeight] = useState('5')
  const [squareSize, setSquareSize] = useState('25')
  const [markerDict, setMarkerDict] = useState('DICT_6X6_250')
  const [capturedFrames, setCapturedFrames] = useState(0)
  const [isCapturing, setIsCapturing] = useState(false)
  const [isCalculating, setIsCalculating] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [calibrationResult, setCalibrationResult] = useState<CalibrationResult | null>(null)

  // Calculate max dimensions for A4 paper (210mm x 297mm)
  const getMaxWidth = () => {
    const size = Math.max(5, Math.min(50, parseFloat(squareSize) || 25))
    return Math.max(MIN_CORNERS, Math.floor(210 / size) - 1)
  }
  const getMaxHeight = () => {
    const size = Math.max(5, Math.min(50, parseFloat(squareSize) || 25))
    return Math.max(MIN_CORNERS, Math.floor(297 / size) - 1)
  }

  // Fetch cameras on mount
  useEffect(() => {
    const fetchCameras = async () => {
      try {
        const data = await api.get<Camera[]>('/api/cameras')
        useAppStore.getState().setCameras(data)
      } catch (error) {
        toast({
          variant: 'destructive',
          title: 'Error',
          description: 'Failed to fetch cameras',
        })
      }
    }
    fetchCameras()
  }, [])

  // Load persisted settings on mount
  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const stored = window.localStorage.getItem(SETTINGS_STORAGE_KEY)
      if (!stored) return
      const parsed = JSON.parse(stored) as Partial<{
        patternType: string
        innerCornersWidth: number
        innerCornersHeight: number
        squareSize: number
        markerDict: string
      }>

      if (parsed.squareSize) {
        const clampedSize = clampFloatString(parsed.squareSize.toString(), 5, 50)
        setSquareSize(clampedSize)

        const numericSize = parseFloat(clampedSize)
        const widthMax = Math.max(MIN_CORNERS, Math.floor(210 / numericSize) - 1)
        const heightMax = Math.max(MIN_CORNERS, Math.floor(297 / numericSize) - 1)

        if (parsed.innerCornersWidth) {
          setInnerCornersWidth(
            clampIntString(parsed.innerCornersWidth.toString(), MIN_CORNERS, widthMax),
          )
        }
        if (parsed.innerCornersHeight) {
          setInnerCornersHeight(
            clampIntString(parsed.innerCornersHeight.toString(), MIN_CORNERS, heightMax),
          )
        }
      }

      if (parsed.patternType === 'chessboard' || parsed.patternType === 'charuco') {
        setPatternType(parsed.patternType)
      }

      if (parsed.markerDict) {
        setMarkerDict(parsed.markerDict)
      }
    } catch (error) {
      console.warn('Failed to load calibration settings', error)
    }
  }, [])

  // Persist settings whenever they change
  useEffect(() => {
    if (typeof window === 'undefined') return

    const widthNum = parseInt(innerCornersWidth, 10)
    const heightNum = parseInt(innerCornersHeight, 10)
    const squareNum = parseFloat(squareSize)

    if ([widthNum, heightNum, squareNum].some((v) => Number.isNaN(v))) {
      return
    }

    const payload = {
      patternType,
      innerCornersWidth: widthNum,
      innerCornersHeight: heightNum,
      squareSize: squareNum,
      markerDict,
    }

    try {
      window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(payload))
    } catch (error) {
      console.warn('Failed to persist calibration settings', error)
    }
  }, [patternType, innerCornersWidth, innerCornersHeight, squareSize, markerDict])

  // Clamp and normalise inputs whenever they change
  useEffect(() => {
    const clampedSize = clampFloatString(squareSize || MIN_CORNERS.toString(), 5, 50)
    if (clampedSize !== squareSize) {
      setSquareSize(clampedSize)
      return
    }

    const numericSize = parseFloat(clampedSize)
    if (Number.isNaN(numericSize)) {
      setSquareSize('25')
      return
    }

    const widthMax = Math.max(MIN_CORNERS, Math.floor(210 / numericSize) - 1)
    const heightMax = Math.max(MIN_CORNERS, Math.floor(297 / numericSize) - 1)

    const clampedWidth = clampIntString(innerCornersWidth || MIN_CORNERS.toString(), MIN_CORNERS, widthMax)
    if (clampedWidth !== innerCornersWidth) {
      setInnerCornersWidth(clampedWidth)
    }

    const clampedHeight = clampIntString(innerCornersHeight || MIN_CORNERS.toString(), MIN_CORNERS, heightMax)
    if (clampedHeight !== innerCornersHeight) {
      setInnerCornersHeight(clampedHeight)
    }
  }, [squareSize, innerCornersWidth, innerCornersHeight])

  const handleDownloadPattern = async () => {
    const endpoint =
      patternType === 'chessboard'
        ? '/calibration/generate_pattern'
        : '/calibration/generate_charuco_pattern'

    const params = new URLSearchParams({
      inner_corners_width: innerCornersWidth,
      inner_corners_height: innerCornersHeight,
      square_size_mm: squareSize,
      ...(patternType === 'charuco' && { marker_dict: markerDict }),
    })

    window.location.href = `${endpoint}?${params.toString()}`
    toast({
      title: 'Downloading pattern',
      description: 'Pattern PDF is being generated',
    })
  }

  const handleStartCalibration = async () => {
    if (!selectedCameraId) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Please select a camera',
      })
      return
    }

    try {
      await api.post('/calibration/start', {
        camera_id: parseInt(selectedCameraId),
        pattern_type: patternType,
        inner_corners_width: parseInt(innerCornersWidth),
        inner_corners_height: parseInt(innerCornersHeight),
        square_size_mm: parseFloat(squareSize),
        ...(patternType === 'charuco' && { marker_dict: markerDict }),
      })

      setStep('capture')
      setCapturedFrames(0)
      toast({
        title: 'Calibration started',
        description: 'Position the pattern in view and capture frames',
      })
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to start calibration',
      })
    }
  }

  const handleCaptureFrame = async () => {
    if (!selectedCameraId) return

    setIsCapturing(true)
    try {
      await api.post('/calibration/capture', {
        camera_id: parseInt(selectedCameraId),
      })

      setCapturedFrames((prev) => prev + 1)
      toast({
        title: 'Frame captured',
        description: `Total frames: ${capturedFrames + 1}`,
      })
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to capture frame',
      })
    } finally {
      setIsCapturing(false)
    }
  }

  const handleCalculate = async () => {
    if (!selectedCameraId) return

    setIsCalculating(true)
    try {
      const result = await api.post<CalibrationResult>('/calibration/calculate', {
        camera_id: parseInt(selectedCameraId),
      })

      setCalibrationResult(result)
      setStep('results')
      toast({
        title: 'Calibration complete',
        description: `Reprojection error: ${result.reprojection_error.toFixed(3)} pixels`,
      })
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to calculate calibration',
      })
    } finally {
      setIsCalculating(false)
    }
  }

  const handleSave = async () => {
    if (!selectedCameraId || !calibrationResult) return

    setIsSaving(true)
    try {
      await api.post('/calibration/save', {
        camera_id: parseInt(selectedCameraId),
      })

      toast({
        title: 'Calibration saved',
        description: 'Camera intrinsics stored to database',
      })

      // Reset to setup
      setStep('setup')
      setCapturedFrames(0)
      setCalibrationResult(null)
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to save calibration',
      })
    } finally {
      setIsSaving(false)
    }
  }

  const selectedCamera = cameras.find((c) => c.id === parseInt(selectedCameraId))

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-semibold mb-2">Camera Calibration</h1>
        <p className="text-muted">
          Calibrate camera intrinsics for accurate pose estimation
        </p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center justify-center gap-4" data-testid="step-indicator">
        {(
          [
            { id: 'setup', label: 'Setup', index: 1 },
            { id: 'capture', label: 'Capture', index: 2 },
            { id: 'results', label: 'Results', index: 3 },
          ] as const
        ).map((item, idx, arr) => (
          <div key={item.id} className="flex items-center gap-4">
            <div
              data-testid={`step-${item.id}`}
              className={cn(
                'flex items-center gap-2 text-muted-foreground transition-colors',
                step === item.id && 'text-primary',
              )}
            >
              <div
                className={cn(
                  'flex h-8 w-8 items-center justify-center rounded-full bg-surface-alt text-sm font-semibold',
                  step === item.id && 'bg-primary text-primary-foreground',
                )}
              >
                {item.index}
              </div>
              <span className="text-sm font-medium">{item.label}</span>
            </div>
            {idx < arr.length - 1 && <div className="h-px w-12 bg-border" />}
          </div>
        ))}
      </div>

      {/* Step 1: Setup */}
      {step === 'setup' && (
        <Card>
          <CardHeader>
            <CardTitle>Calibration Setup</CardTitle>
            <CardDescription>
              Select camera and configure calibration pattern
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="camera">Camera</Label>
                <Select value={selectedCameraId} onValueChange={setSelectedCameraId}>
                  <SelectTrigger id="camera">
                    <SelectValue placeholder="Select camera" />
                  </SelectTrigger>
                  <SelectContent>
                    {cameras.map((camera) => (
                      <SelectItem key={camera.id} value={camera.id.toString()}>
                        {camera.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="pattern-type">Pattern Type</Label>
                <Select value={patternType} onValueChange={(v) => setPatternType(v as 'chessboard' | 'charuco')}>
                  <SelectTrigger id="pattern-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="chessboard">Chessboard</SelectItem>
                    <SelectItem value="charuco">ChAruco</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="width">Inner Corners (Width)</Label>
                <Input
                  id="width"
                  type="number"
                  min={MIN_CORNERS}
                  max={getMaxWidth()}
                  value={innerCornersWidth}
                  onChange={(e) => setInnerCornersWidth(e.target.value)}
                />
                <p className="text-xs text-muted">
                  Max {getMaxWidth()} for {squareSize}mm squares on A4
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="height">Inner Corners (Height)</Label>
                <Input
                  id="height"
                  type="number"
                  min={MIN_CORNERS}
                  max={getMaxHeight()}
                  value={innerCornersHeight}
                  onChange={(e) => setInnerCornersHeight(e.target.value)}
                />
                <p className="text-xs text-muted">
                  Max {getMaxHeight()} for {squareSize}mm squares on A4
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="square-size">Square Size (mm)</Label>
                <Input
                  id="square-size"
                  type="number"
                  min={5}
                  max={50}
                  step={0.1}
                  value={squareSize}
                  onChange={(e) => setSquareSize(e.target.value)}
                />
                <p className="text-xs text-muted">
                  5mm - 50mm (affects max board size)
                </p>
              </div>

              {patternType === 'charuco' && (
                <div className="space-y-2">
                  <Label htmlFor="marker-dict">Marker Dictionary</Label>
                  <Select value={markerDict} onValueChange={setMarkerDict}>
                    <SelectTrigger id="marker-dict">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="DICT_4X4_50">4x4 (50)</SelectItem>
                      <SelectItem value="DICT_5X5_50">5x5 (50)</SelectItem>
                      <SelectItem value="DICT_6X6_250">6x6 (250)</SelectItem>
                      <SelectItem value="DICT_7X7_1000">7x7 (1000)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>

            <div className="flex gap-2">
              <Button variant="outline" onClick={handleDownloadPattern}>
                <Download className="h-4 w-4 mr-2" />
                Download Pattern
              </Button>
              <Button onClick={handleStartCalibration} disabled={!selectedCameraId}>
                Start Calibration
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 2: Capture */}
      {step === 'capture' && selectedCamera && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle data-testid="capture-feed-title">Calibration Feed</CardTitle>
              <CardDescription>
                Position pattern in different angles and distances
              </CardDescription>
            </CardHeader>
            <CardContent>
              <MJPEGStream
                src={`/calibration/calibration_feed/${selectedCamera.id}`}
                alt="Calibration Feed"
                className="aspect-video w-full"
                data-testid="calibration-feed"
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle data-testid="capture-frames-title">Capture Frames</CardTitle>
              <CardDescription>
                Capture at least 5 frames from different positions
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="text-center py-8" data-testid="capture-summary">
                <div className="text-4xl font-bold mb-2" data-testid="captured-count">
                  {capturedFrames}
                </div>
                <p className="text-muted">Frames captured</p>
              </div>

              <Button
                className="w-full"
                onClick={handleCaptureFrame}
                disabled={isCapturing}
              >
                <CameraIcon className="h-4 w-4 mr-2" />
                {isCapturing ? 'Capturing...' : 'Capture Frame'}
              </Button>

              <Button
                className="w-full"
                variant="outline"
                onClick={handleCalculate}
                disabled={capturedFrames < 5 || isCalculating}
              >
                {isCalculating ? 'Calculating...' : 'Calculate Intrinsics'}
              </Button>

              <p className="text-xs text-muted text-center">
                {capturedFrames < 5
                  ? `Capture ${5 - capturedFrames} more frames to calculate`
                  : 'Ready to calculate intrinsics'}
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Step 3: Results */}
      {step === 'results' && calibrationResult && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-[var(--color-success)]" />
              Calibration Results
            </CardTitle>
            <CardDescription>
              Camera intrinsics successfully calculated
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
              <Label className="text-base">Reprojection Error</Label>
              <p className="text-2xl font-bold mt-1">
                {calibrationResult.reprojection_error.toFixed(3)} pixels
              </p>
              <p className="text-sm text-muted mt-1">
                {calibrationResult.reprojection_error < 0.5
                  ? 'Excellent calibration quality'
                  : calibrationResult.reprojection_error < 1.0
                  ? 'Good calibration quality'
                  : 'Fair calibration quality - consider recalibrating'}
              </p>
            </div>

            <div>
              <Label className="text-base">Camera Matrix</Label>
              <div className="mt-2 font-mono text-sm bg-surface-alt p-3 rounded">
                {calibrationResult.camera_matrix.map((row, i) => (
                  <div key={i}>
                    [{row.map((val) => val.toFixed(2)).join(', ')}]
                  </div>
                ))}
              </div>
            </div>

            <div>
              <Label className="text-base">Distortion Coefficients</Label>
              <div className="mt-2 font-mono text-sm bg-surface-alt p-3 rounded">
                [{calibrationResult.dist_coeffs.map((val) => val.toFixed(4)).join(', ')}]
              </div>
            </div>

            <div className="flex gap-2">
              <Button onClick={handleSave} disabled={isSaving}>
                {isSaving ? 'Saving...' : 'Save to Database'}
              </Button>
              <Button variant="outline" onClick={() => setStep('setup')}>
                Start New Calibration
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
