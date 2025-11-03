import { fetchJson } from '../helpers.js';

function normaliseCameras(cameras = []) {
    return cameras.map((camera) => ({
        ...camera,
        id: String(camera.id),
    }));
}

export function registerCalibrationComponents(Alpine) {
    if (!Alpine) {
        return;
    }

    Alpine.data('calibrationApp', (config = {}) => ({
        cameras: normaliseCameras(config.cameras || []),
        step: 'setup',
        setup: {
            cameraId: '',
            patternType: 'ChAruco',
            chessboard: {
                cols: 7,
                rows: 10,
                square_size: 20,
            },
            charuco: {
                squares_x: 7,
                squares_y: 10,
                square_size: 25,
                marker_size: 20,
                dictionary: 'DICT_APRILTAG_36h11',
            },
        },
        capture: {
            count: 0,
            feedSrc: '',
            capturing: false,
            calculating: false,
        },
        results: {
            data: null,
        },
        status: {
            message: '',
            isError: false,
        },

        init() {
            if (this.cameras.length === 1) {
                this.setup.cameraId = this.cameras[0].id;
            }
            this.setup.patternType = 'ChAruco';
        },

        get charucoValid() {
            if (this.setup.patternType !== 'ChAruco') return true;
            const square = Number(this.setup.charuco.square_size);
            const marker = Number(this.setup.charuco.marker_size);
            return marker < square;
        },

        get downloadHref() {
            if (this.setup.patternType === 'Chessboard') {
                const c = this.setup.chessboard;
                return `/calibration/generate_pattern?rows=${c.rows}&cols=${c.cols}&square_size=${c.square_size}`;
            }
            const c = this.setup.charuco;
            return `/calibration/generate_charuco_pattern?squares_x=${c.squares_x}&squares_y=${c.squares_y}&square_size=${c.square_size}&marker_size=${c.marker_size}&dictionary_name=${c.dictionary}`;
        },

        showStatus(message = '', isError = false) {
            this.status.message = message;
            this.status.isError = isError;
        },

        async startCalibration() {
            if (!this.setup.cameraId) {
                this.showStatus('Please select a camera.', true);
                return;
            }
            if (this.setup.patternType === 'ChAruco' && !this.charucoValid) {
                this.showStatus('Marker size must be smaller than square size.', true);
                return;
            }

            const payload = {
                camera_id: Number(this.setup.cameraId),
                pattern_type: this.setup.patternType,
                pattern_params:
                    this.setup.patternType === 'Chessboard'
                        ? {
                              cols: Number(this.setup.chessboard.cols),
                              rows: Number(this.setup.chessboard.rows),
                              square_size: Number(this.setup.chessboard.square_size),
                          }
                        : {
                              squares_x: Number(this.setup.charuco.squares_x),
                              squares_y: Number(this.setup.charuco.squares_y),
                              square_size: Number(this.setup.charuco.square_size),
                              marker_size: Number(this.setup.charuco.marker_size),
                              dictionary_name: this.setup.charuco.dictionary,
                          },
            };

            this.showStatus('Starting calibration session…');
            try {
                const response = await fetchJson('/calibration/start', {
                    method: 'POST',
                    body: JSON.stringify(payload),
                });
                if (!response?.success) {
                    throw new Error(response?.error || 'Failed to start calibration.');
                }

                this.step = 'capture';
                this.capture.count = 0;
                this.capture.feedSrc = `/calibration/calibration_feed/${this.setup.cameraId}?t=${Date.now()}`;
                this.showStatus('Calibration session started. Begin capturing frames.');
            } catch (error) {
                this.showStatus(error.message, true);
            }
        },

        async captureFrame() {
            if (this.capture.capturing) return;
            this.capture.capturing = true;
            try {
                const response = await fetchJson('/calibration/capture', {
                    method: 'POST',
                    body: JSON.stringify({ camera_id: Number(this.setup.cameraId) }),
                });
                if (response?.success) {
                    this.capture.count = response.data?.capture_count ?? this.capture.count + 1;
                    this.showStatus(`Frame captured. Total: ${this.capture.count}`);
                } else {
                    this.showStatus(response?.message || 'Pattern not found in frame.', true);
                }
            } catch (error) {
                this.showStatus(error.message, true);
            } finally {
                this.capture.capturing = false;
            }
        },

        async calculate() {
            if (this.capture.calculating) return;
            this.capture.calculating = true;
            this.showStatus('Calculating… This may take a moment.');
            try {
                const response = await fetchJson('/calibration/calculate', {
                    method: 'POST',
                    body: JSON.stringify({ camera_id: Number(this.setup.cameraId) }),
                });
                if (!response?.success) {
                    throw new Error(response?.error || 'Calculation failed.');
                }
                this.results.data = response.data;
                this.step = 'results';
                this.capture.feedSrc = '';
                this.showStatus('Calculation complete. Review the results below.');
            } catch (error) {
                this.showStatus(error.message, true);
            } finally {
                this.capture.calculating = false;
            }
        },

        reprojectionError() {
            if (!this.results.data) return null;
            return Number(this.results.data.reprojection_error || 0);
        },

        formattedCameraMatrix() {
            if (!this.results.data) return '';
            try {
                const matrix = JSON.parse(this.results.data.camera_matrix);
                return `fx: ${matrix[0][0].toFixed(2)}, fy: ${matrix[1][1].toFixed(2)}\ncx: ${matrix[0][2].toFixed(2)}, cy: ${matrix[1][2].toFixed(2)}`;
            } catch (error) {
                return this.results.data.camera_matrix;
            }
        },

        formattedDistCoeffs() {
            if (!this.results.data) return '';
            try {
                return JSON.stringify(JSON.parse(this.results.data.dist_coeffs), null, 2);
            } catch (error) {
                return this.results.data.dist_coeffs;
            }
        },

        async saveResults() {
            if (!this.results.data) {
                this.showStatus('No results to save.', true);
                return;
            }
            this.showStatus('Saving calibration data…');
            try {
                const payload = {
                    camera_id: Number(this.setup.cameraId),
                    ...this.results.data,
                };
                const response = await fetchJson('/calibration/save', {
                    method: 'POST',
                    body: JSON.stringify(payload),
                });
                if (!response?.success) {
                    throw new Error(response?.error || 'Failed to save calibration.');
                }
                this.showStatus('Calibration saved. The camera will restart to apply changes.');
                window.setTimeout(() => this.resetAll(), 3000);
            } catch (error) {
                this.showStatus(error.message, true);
            }
        },

        resetAll() {
            this.step = 'setup';
            this.capture.count = 0;
            this.capture.feedSrc = '';
            this.capture.capturing = false;
            this.capture.calculating = false;
            this.results.data = null;
            this.showStatus('');
        },

        restart() {
            this.resetAll();
        },
    }));
}
