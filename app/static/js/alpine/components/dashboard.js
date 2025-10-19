import { fetchJson, postJson, debounce, safeJsonParse } from '../helpers.js';

const APRILTAG_DEFAULTS = {
    family: 'tag36h11',
    tag_size_m: 0.165,
    threads: 1,
    decimate: 1,
    blur: 0,
    refine_edges: true,
    decision_margin: 35,
    pose_iterations: 40,
    decode_sharpening: 0.25,
    min_weight: 0,
    edge_threshold: 0,
    multi_tag_enabled: false,
    field_layout: '',
    ransac_reproj_threshold: 1.2,
    ransac_confidence: 0.999,
    min_inliers: 12,
    use_prev_guess: true,
    publish_field_pose: true,
    output_quaternion: true,
    multi_tag_error_threshold: 6.0,
};

const COLOURED_DEFAULTS = {
    hue_min: 0,
    hue_max: 179,
    saturation_min: 0,
    saturation_max: 255,
    value_min: 0,
    value_max: 255,
    min_area: 100,
    max_area: 10000,
    min_aspect_ratio: 0.5,
    max_aspect_ratio: 2.0,
    min_fullness: 0.4,
};

const ML_DEFAULTS = {
    model_type: 'yolo',
    confidence_threshold: 0.5,
    nms_iou_threshold: 0.45,
    target_classes: [],
    onnx_provider: 'CPUExecutionProvider',
    accelerator: 'none',
    max_detections: 100,
    img_size: 640,
    model_filename: '',
    labels_filename: '',
    tflite_delegate: null,
};

function cloneDefaults(template) {
    return JSON.parse(JSON.stringify(template));
}

function toStringId(value) {
    if (value === null || value === undefined || value === '') {
        return '';
    }
    return String(value);
}

function toNumber(value, fallback) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}

export function registerDashboardComponents(Alpine) {
    if (!Alpine) {
        return;
    }

    Alpine.data('dashboardApp', (config = {}) => ({
        cameras: config.cameras || [],
        endpoints: Object.assign(
            {
                cameraStatus: (cameraId) => `/cameras/status/${cameraId}`,
                cameraControls: (cameraId) => `/cameras/controls/${cameraId}`,
                updateCameraControls: (cameraId) => `/cameras/update_controls/${cameraId}`,
                pipelinesForCamera: (cameraId) => `/api/cameras/${cameraId}/pipelines`,
                updatePipeline: (pipelineId) => `/api/pipelines/${pipelineId}`,
                pipelineConfig: (pipelineId) => `/api/pipelines/${pipelineId}/config`,
                pipelineFiles: (pipelineId) => `/api/pipelines/${pipelineId}/files`,
                mlAvailability: '/api/pipelines/ml/availability',
                pipelineLabels: (pipelineId) => `/api/pipelines/${pipelineId}/labels`,
                cameraResults: (cameraId) => `/cameras/results/${cameraId}`,
            },
            config.endpoints || {},
        ),
        selectedCameraId: toStringId(config.selectedCameraId ?? ''),
        pipelines: [],
        selectedPipelineId: '',
        pipelineType: '',
        feedType: 'default',
        feedSrc: '',
        feedError: '',
        isCameraConnected: false,
        controls: {
            orientation: 0,
            exposure_mode: 'auto',
            exposure_value: 500,
            gain_mode: 'auto',
            gain_value: 50,
        },
        pipelineForms: {
            apriltag: cloneDefaults(APRILTAG_DEFAULTS),
            coloured: cloneDefaults(COLOURED_DEFAULTS),
            ml: cloneDefaults(ML_DEFAULTS),
        },
        mlAvailability: null,
        labelOptions: [],
        isLoadingControls: false,
        isLoadingPipelines: false,
        isSavingControls: false,
        isSavingPipeline: false,
        isUploadingFile: false,
        pipelineTypes: ['AprilTag', 'Coloured Shape', 'Object Detection (ML)'],
        pipelineModal: {
            open: false,
            mode: 'add',
            name: '',
            type: 'AprilTag',
            saving: false,
        },
        deleteModal: {
            open: false,
            pipelineId: '',
            name: '',
            saving: false,
        },
        results: {
            apriltag: [],
            ml: [],
            multiTag: null,
        },
        resultsError: '',
        resultsInterval: null,
        debouncedPipelineSave: null,
        debouncedControlSave: null,

        toast(type, message) {
            Alpine.store('toasts').push(message, type);
        },

        get hasCamera() {
            return Boolean(this.selectedCameraId);
        },

        get selectedCamera() {
            return this.cameras.find((camera) => toStringId(camera.id) === this.selectedCameraId) || null;
        },

        get pipeline() {
            return this.pipelines.find((pipeline) => pipeline.id === this.selectedPipelineId) || null;
        },

        get canUseProcessedFeed() {
            return Boolean(this.selectedPipelineId);
        },

        get exposureManual() {
            return this.controls.exposure_mode === 'manual';
        },

        get gainManual() {
            return this.controls.gain_mode === 'manual';
        },

        init() {
            this.selectedCameraId = toStringId(this.selectedCameraId);
            this.debouncedPipelineSave = debounce(() => this.savePipelineConfig(), 600);
            this.debouncedControlSave = debounce(() => this.saveControls(), 400);

            if (this.hasCamera) {
                this.refreshCameraData();
            }

            this.$watch('selectedCameraId', async (value, previous) => {
                if (value === previous) return;
                await this.onCameraChanged();
            });

            this.$watch('selectedPipelineId', async (value, previous) => {
                if (value === previous) return;
                await this.onPipelineChanged();
            });

            this.$watch('feedType', () => {
                this.updateFeedSource();
            });
        },

        async onCameraChanged() {
            this.stopResultsPolling();
            this.selectedCameraId = toStringId(this.selectedCameraId);
            if (!this.hasCamera) {
                this.pipelines = [];
                this.selectedPipelineId = '';
                this.pipelineType = '';
                this.resetResults();
                this.feedSrc = '';
                this.feedError = 'Select a camera to view the feed.';
                return;
            }
            await this.refreshCameraData();
        },

        async refreshCameraData() {
            await Promise.all([this.refreshPipelines(), this.refreshControls()]);
            await this.updateFeedSource();
            this.restartResultsPolling();
        },

        async refreshControls() {
            if (!this.hasCamera) return;
            this.isLoadingControls = true;
            try {
                const data = await fetchJson(this.endpoints.cameraControls(this.selectedCameraId));
                this.controls.orientation = data.orientation ?? 0;
                this.controls.exposure_mode = data.exposure_mode || 'auto';
                this.controls.exposure_value = data.exposure_value ?? 500;
                this.controls.gain_mode = data.gain_mode || 'auto';
                this.controls.gain_value = data.gain_value ?? 50;
            } catch (error) {
                this.toast('error', `Failed to load camera controls: ${error.message}`);
            } finally {
                this.isLoadingControls = false;
            }
        },

        queueControlsSave() {
            if (this.debouncedControlSave) {
                this.debouncedControlSave();
            }
        },

        async saveControls() {
            if (!this.hasCamera) return;
            const payload = {
                orientation: Number(this.controls.orientation) || 0,
                exposure_mode: this.controls.exposure_mode,
                exposure_value: Number(this.controls.exposure_value) || 0,
                gain_mode: this.controls.gain_mode,
                gain_value: Number(this.controls.gain_value) || 0,
            };
            this.isSavingControls = true;
            try {
                await fetchJson(this.endpoints.updateCameraControls(this.selectedCameraId), {
                    method: 'POST',
                    body: JSON.stringify(payload),
                });
                await this.updateFeedSource();
            } catch (error) {
                this.toast('error', error.payload?.error || error.message || 'Failed to save controls');
            } finally {
                this.isSavingControls = false;
            }
        },

        async refreshPipelines() {
            if (!this.hasCamera) return;
            this.isLoadingPipelines = true;
            try {
                const data = await fetchJson(this.endpoints.pipelinesForCamera(this.selectedCameraId));
                const existingSelection = this.selectedPipelineId;
                this.pipelines = (data || []).map((pipeline) => ({
                    ...pipeline,
                    id: toStringId(pipeline.id),
                    configData: safeJsonParse(pipeline.config || '{}', {}),
                }));
                const stillExists = existingSelection && this.pipelines.some((pipeline) => pipeline.id === existingSelection);
                if (!stillExists) {
                    this.selectedPipelineId = '';
                }
                if (!this.pipelines.length) {
                    this.pipelineType = '';
                    this.labelOptions = [];
                }
            } catch (error) {
                this.toast('error', `Failed to load pipelines: ${error.message}`);
                this.pipelines = [];
                this.selectedPipelineId = '';
                this.pipelineType = '';
                this.labelOptions = [];
            } finally {
                this.isLoadingPipelines = false;
            }
        },

        async onPipelineChanged() {
            const pipeline = this.pipeline;
            if (!pipeline) {
                this.pipelineType = '';
                this.resetPipelineForms();
                this.labelOptions = [];
                this.resetResults();
                await this.updateFeedSource();
                return;
            }

            this.pipelineType = pipeline.pipeline_type;
            this.loadFormsFromConfig(pipeline.configData || {});

            if (this.pipelineType === 'Object Detection (ML)') {
                await this.ensureMlAvailability();
                await this.loadLabels(false);
            } else {
                this.labelOptions = [];
            }

            await this.updateFeedSource();
        },

        resetPipelineForms() {
            this.pipelineForms.apriltag = cloneDefaults(APRILTAG_DEFAULTS);
            this.pipelineForms.coloured = cloneDefaults(COLOURED_DEFAULTS);
            this.pipelineForms.ml = cloneDefaults(ML_DEFAULTS);
        },

        loadFormsFromConfig(config) {
            if (!config) return;
            if (this.pipelineType === 'AprilTag') {
                this.pipelineForms.apriltag = {
                    ...cloneDefaults(APRILTAG_DEFAULTS),
                    ...config,
                };
            } else if (this.pipelineType === 'Coloured Shape') {
                this.pipelineForms.coloured = {
                    ...cloneDefaults(COLOURED_DEFAULTS),
                    ...config,
                };
            } else if (this.pipelineType === 'Object Detection (ML)') {
                this.pipelineForms.ml = {
                    ...cloneDefaults(ML_DEFAULTS),
                    ...config,
                    target_classes: Array.isArray(config.target_classes) ? config.target_classes : [],
                    model_type: (config.model_type || 'yolo').toLowerCase(),
                };
            }
        },

        queuePipelineSave() {
            if (this.debouncedPipelineSave) {
                this.debouncedPipelineSave();
            }
        },

        openPipelineModal(mode, pipeline = null) {
            const defaultType = (pipeline?.pipeline_type) || this.pipelineTypes[0];
            this.pipelineModal = {
                open: true,
                mode,
                name: (pipeline?.name) || '',
                type: defaultType,
                saving: false,
            };
        },

        closePipelineModal() {
            this.pipelineModal.open = false;
            this.pipelineModal.saving = false;
        },

        addPipeline() {
            if (!this.hasCamera) {
                return;
            }
            this.openPipelineModal('add');
        },

        renamePipeline() {
            if (!this.pipeline) {
                return;
            }
            this.openPipelineModal('edit', this.pipeline);
        },

        async submitPipelineModal() {
            if (!this.pipelineModal.open) {
                return;
            }
            const name = this.pipelineModal.name.trim();
            const type = this.pipelineModal.type;
            if (!name) {
                this.toast('error', 'Pipeline name is required');
                return;
            }
            if (!this.hasCamera) {
                this.toast('error', 'Select a camera first');
                return;
            }

            this.pipelineModal.saving = true;

            if (this.pipelineModal.mode === 'add') {
                try {
                    const response = await postJson(this.endpoints.pipelinesForCamera(this.selectedCameraId), {
                        name,
                        pipeline_type: type,
                    });
                    if (response?.pipeline) {
                        await this.refreshPipelines();
                        this.selectedPipelineId = toStringId(response.pipeline.id);
                        await this.onPipelineChanged();
                        this.toast('success', 'Pipeline created');
                    } else {
                        await this.refreshPipelines();
                        this.toast('success', 'Pipeline created');
                    }
                    this.closePipelineModal();
                } catch (error) {
                    this.toast('error', error.payload?.error || error.message || 'Failed to add pipeline');
                } finally {
                    this.pipelineModal.saving = false;
                }
                return;
            }

            const pipeline = this.pipeline;
            if (!pipeline) {
                this.pipelineModal.saving = false;
                return;
            }

            try {
                await fetchJson(this.endpoints.updatePipeline(pipeline.id), {
                    method: 'PUT',
                    body: JSON.stringify({
                        name,
                        pipeline_type: type,
                    }),
                });
                pipeline.name = name;
                pipeline.pipeline_type = type;
                this.pipelineType = type;
                this.closePipelineModal();
                await this.onPipelineChanged();
                this.toast('success', 'Pipeline updated');
            } catch (error) {
                this.toast('error', error.payload?.error || error.message || 'Failed to update pipeline');
                this.pipelineModal.saving = false;
            }
        },

        deletePipeline() {
            if (!this.pipeline) {
                return;
            }
            this.deleteModal = {
                open: true,
                pipelineId: this.pipeline.id,
                name: this.pipeline.name,
                saving: false,
            };
        },

        closeDeleteModal() {
            this.deleteModal.open = false;
            this.deleteModal.saving = false;
        },

        async confirmDeletePipeline() {
            if (!this.deleteModal.open || !this.deleteModal.pipelineId) {
                return;
            }
            this.deleteModal.saving = true;
            try {
                await fetchJson(this.endpoints.updatePipeline(this.deleteModal.pipelineId), {
                    method: 'DELETE',
                });
                this.closeDeleteModal();
                await this.refreshPipelines();
                await this.onPipelineChanged();
                this.toast('success', 'Pipeline deleted');
            } catch (error) {
                this.toast('error', error.payload?.error || error.message || 'Failed to delete pipeline');
                this.deleteModal.saving = false;
            }
        },

        async savePipelineConfig() {
            const pipeline = this.pipeline;
            if (!pipeline) return;
            const payload = this.buildPipelineConfigPayload();
            if (!payload) return;

            this.isSavingPipeline = true;
            try {
                await fetchJson(this.endpoints.pipelineConfig(pipeline.id), {
                    method: 'PUT',
                    body: JSON.stringify(payload),
                });
                pipeline.configData = payload;
            } catch (error) {
                const message = error.payload?.details || error.payload?.error || error.message || 'Failed to save pipeline settings';
                this.toast('error', message);
            } finally {
                this.isSavingPipeline = false;
            }
        },

        buildPipelineConfigPayload() {
            if (!this.pipeline) return null;

            if (this.pipelineType === 'AprilTag') {
                const form = this.pipelineForms.apriltag;
                return {
                    family: form.family || 'tag36h11',
                    tag_size_m: toNumber(form.tag_size_m, 0.165),
                    threads: toNumber(form.threads, 1),
                    decimate: toNumber(form.decimate, 1),
                    blur: toNumber(form.blur, 0),
                    refine_edges: Boolean(form.refine_edges),
                    decision_margin: toNumber(form.decision_margin, 35),
                    pose_iterations: toNumber(form.pose_iterations, 40),
                    decode_sharpening: toNumber(form.decode_sharpening, 0.25),
                    multi_tag_enabled: Boolean(form.multi_tag_enabled),
                    field_layout: form.field_layout ? String(form.field_layout) : '',
                    ransac_reproj_threshold: toNumber(form.ransac_reproj_threshold, 1.2),
                    ransac_confidence: toNumber(form.ransac_confidence, 0.999),
                    min_inliers: Math.max(0, Math.round(toNumber(form.min_inliers, 12))),
                    use_prev_guess: Boolean(form.use_prev_guess),
                    publish_field_pose: Boolean(form.publish_field_pose),
                    output_quaternion: Boolean(form.output_quaternion),
                    multi_tag_error_threshold: toNumber(form.multi_tag_error_threshold, 6),
                };
            }

            if (this.pipelineType === 'Coloured Shape') {
                const form = this.pipelineForms.coloured;
                return {
                    hue_min: Number(form.hue_min) || 0,
                    hue_max: Number(form.hue_max) || 179,
                    saturation_min: Number(form.saturation_min) || 0,
                    saturation_max: Number(form.saturation_max) || 255,
                    value_min: Number(form.value_min) || 0,
                    value_max: Number(form.value_max) || 255,
                    min_area: Number(form.min_area) || 100,
                    max_area: Number(form.max_area) || 10000,
                    min_aspect_ratio: Number(form.min_aspect_ratio) || 0.5,
                    max_aspect_ratio: Number(form.max_aspect_ratio) || 2.0,
                    min_fullness: Number(form.min_fullness) || 0.4,
                };
            }

            if (this.pipelineType === 'Object Detection (ML)') {
                const form = this.pipelineForms.ml;
                const payload = {
                    model_type: (form.model_type || 'yolo').toLowerCase(),
                    confidence_threshold: Number(form.confidence_threshold) || 0.5,
                    nms_iou_threshold: Number(form.nms_iou_threshold) || 0.45,
                    target_classes: Array.isArray(form.target_classes) ? form.target_classes : [],
                    max_detections: Number(form.max_detections) || 100,
                    img_size: Number(form.img_size) || 640,
                    accelerator: form.accelerator || 'none',
                    model_filename: form.model_filename || '',
                    labels_filename: form.labels_filename || '',
                };

                if (payload.model_type === 'tflite') {
                    payload.tflite_delegate = form.tflite_delegate || 'CPU';
                    payload.onnx_provider = undefined;
                } else {
                    payload.onnx_provider = form.onnx_provider || 'CPUExecutionProvider';
                    payload.tflite_delegate = undefined;
                }
                return payload;
            }

            return null;
        },

        async onPipelineTypeChange(newType) {
            if (!this.pipeline || newType === this.pipelineType) return;
            if (!window.confirm('Changing the pipeline type will reset its configuration. Continue?')) {
                // Revert selection
                this.pipelineType = this.pipeline.pipeline_type;
                return;
            }
            await this.updatePipelineType(newType);
        },

        async updatePipelineType(newType) {
            const pipeline = this.pipeline;
            if (!pipeline) return;

            try {
                await fetchJson(this.endpoints.updatePipeline(pipeline.id), {
                    method: 'PUT',
                    body: JSON.stringify({
                        name: pipeline.name,
                        pipeline_type: newType,
                    }),
                });
                pipeline.pipeline_type = newType;
                pipeline.configData = {};
                this.pipelineType = newType;
                this.resetPipelineForms();
                await this.savePipelineConfig();
                await this.onPipelineChanged();
            } catch (error) {
                this.toast('error', error.payload?.error || error.message || 'Failed to update pipeline type');
                this.pipelineType = pipeline.pipeline_type;
            }
        },

        async uploadPipelineFile(event, type) {
            const pipeline = this.pipeline;
            if (!pipeline) return;
            const input = event.target;
            const file = input.files?.[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);
            formData.append('type', type);

            this.isUploadingFile = true;
            try {
                const response = await fetch(this.endpoints.pipelineFiles(pipeline.id), {
                    method: 'POST',
                    body: formData,
                });
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload?.details || payload?.error || 'File upload failed');
                }
                pipeline.configData = payload.config || pipeline.configData;
                this.loadFormsFromConfig(pipeline.configData);
                if (type === 'labels') {
                    await this.loadLabels(true);
                }
                this.toast('success', `${type === 'model' ? 'Model' : 'Labels'} uploaded successfully`);
            } catch (error) {
                this.toast('error', error.message || 'Failed to upload file');
            } finally {
                this.isUploadingFile = false;
                input.value = '';
            }
        },

        async deletePipelineFile(type) {
            const pipeline = this.pipeline;
            if (!pipeline) return;
            if (!window.confirm(`Remove ${type} file from pipeline "${pipeline.name}"?`)) return;

            try {
                const response = await fetchJson(this.endpoints.pipelineFiles(pipeline.id), {
                    method: 'DELETE',
                    body: JSON.stringify({ type }),
                });
                pipeline.configData = response?.config || pipeline.configData;
                this.loadFormsFromConfig(pipeline.configData);
                if (type === 'labels') {
                    await this.loadLabels(true);
                }
                this.toast('success', `${type === 'model' ? 'Model' : 'Labels'} removed`);
            } catch (error) {
                this.toast('error', error.payload?.error || error.message || 'Failed to delete file');
            }
        },

        async ensureMlAvailability() {
            if (this.mlAvailability) return;
            try {
                const availability = await fetchJson(this.endpoints.mlAvailability);
                this.mlAvailability = availability || {};
            } catch (error) {
                console.warn('Failed to fetch ML availability:', error);
                this.mlAvailability = {};
            }
        },

        async loadLabels(force = false) {
            const pipeline = this.pipeline;
            if (!pipeline || this.pipelineType !== 'Object Detection (ML)') return;
            if (!force && this.labelOptions.length) return;

            try {
                const payload = await fetchJson(this.endpoints.pipelineLabels(pipeline.id));
                this.labelOptions = payload?.labels || [];
                // Ensure selected classes are still valid
                if (this.pipelineForms.ml.target_classes?.length) {
                    this.pipelineForms.ml.target_classes = this.pipelineForms.ml.target_classes.filter((item) =>
                        this.labelOptions.includes(item),
                    );
                }
            } catch (error) {
                console.warn('Failed to load labels:', error);
                this.labelOptions = [];
            }
        },

        async updateFeedSource() {
            if (!this.hasCamera) {
                this.feedSrc = '';
                this.feedError = 'Select a camera to view the feed.';
                this.isCameraConnected = false;
                return;
            }

            if (this.feedType === 'processed' && !this.canUseProcessedFeed) {
                this.feedType = 'default';
                return;
            }

            try {
                const status = await fetchJson(this.endpoints.cameraStatus(this.selectedCameraId));
                this.isCameraConnected = Boolean(status?.connected);
            } catch (error) {
                this.isCameraConnected = false;
            }

            if (!this.isCameraConnected) {
                this.feedSrc = '';
                this.feedError = 'Camera is not connected.';
                return;
            }

            const cacheBuster = Date.now();
            if (this.feedType === 'processed' && this.selectedPipelineId) {
                this.feedSrc = `/processed_video_feed/${this.selectedPipelineId}?t=${cacheBuster}`;
            } else {
                this.feedSrc = `/video_feed/${this.selectedCameraId}?t=${cacheBuster}`;
            }
            this.feedError = '';
        },

        restartResultsPolling() {
            this.stopResultsPolling();
            if (!this.hasCamera) return;
            this.fetchResults();
            this.resultsInterval = window.setInterval(() => this.fetchResults(), 1000);
        },

        stopResultsPolling() {
            if (this.resultsInterval) {
                clearInterval(this.resultsInterval);
                this.resultsInterval = null;
            }
        },

        resetResults() {
            this.results = {
                apriltag: [],
                ml: [],
                multiTag: null,
            };
            this.resultsError = '';
        },

        async fetchResults() {
            if (!this.hasCamera) return;
            try {
                const data = await fetchJson(this.endpoints.cameraResults(this.selectedCameraId));
                const pipelineResults = data?.[this.selectedPipelineId];
                if (!pipelineResults) {
                    this.resetResults();
                    return;
                }

                if (this.pipelineType === 'AprilTag') {
                    this.results.apriltag = pipelineResults.detections || [];
                    this.results.multiTag = pipelineResults.multi_tag_pose || null;
                    this.results.ml = [];
                } else if (this.pipelineType === 'Object Detection (ML)') {
                    this.results.ml = pipelineResults.detections || [];
                    this.results.apriltag = [];
                    this.results.multiTag = null;
                } else {
                    this.resetResults();
                }
                this.resultsError = '';
            } catch (error) {
                this.resultsError = error.message || 'Failed to fetch pipeline results';
                this.resetResults();
            }
        },

        formatNumber(value, digits = 2) {
            return Number.isFinite(value) ? value.toFixed(digits) : 'N/A';
        },

        onExposureModeChange(value) {
            this.controls.exposure_mode = value;
            this.queueControlsSave();
        },

        onGainModeChange(value) {
            this.controls.gain_mode = value;
            this.queueControlsSave();
        },
    }));
}
