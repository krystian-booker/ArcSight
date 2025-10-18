import {
    getPipelinesForCamera,
    updatePipelineConfig,
    addPipelineToCamera,
    updatePipeline as apiUpdatePipeline,
    deletePipeline as apiDeletePipeline,
    uploadFileToPipeline,
    deleteFileFromPipeline,
    getMlAvailability,
    getPipelineLabels
} from '../api.js';

let currentPipelines = [];
let mlAvailabilityPromise = null;
const labelsCache = new Map();

function getDefaultAvailability() {
    return {
        onnx: { providers: ['CPUExecutionProvider'] },
        tflite: { delegates: ['CPU'] },
        accelerators: { rknn: false },
        platform: {},
    };
}

async function fetchMlAvailability() {
    if (!mlAvailabilityPromise) {
        mlAvailabilityPromise = getMlAvailability()
            .then(data => data || getDefaultAvailability())
            .catch(error => {
                console.error('Failed to fetch ML availability:', error);
                return getDefaultAvailability();
            });
    }
    return mlAvailabilityPromise;
}

async function fetchLabels(pipelineId) {
    if (labelsCache.has(pipelineId)) {
        return labelsCache.get(pipelineId);
    }
    try {
        const response = await getPipelineLabels(pipelineId);
        const labels = response.labels || [];
        labelsCache.set(pipelineId, labels);
        return labels;
    } catch (error) {
        console.error('Failed to fetch pipeline labels:', error);
        labelsCache.set(pipelineId, []);
        return [];
    }
}

function populateSelectOptions(selectElement, options, selectedValue) {
    if (!selectElement) return;
    selectElement.innerHTML = '';
    options.forEach(optionValue => {
        const option = new Option(optionValue, optionValue);
        selectElement.appendChild(option);
    });
    if (selectedValue && options.includes(selectedValue)) {
        selectElement.value = selectedValue;
    } else if (options.length > 0) {
        selectElement.value = options[0];
    }
}

function toggleRuntimeSections(form, modelType) {
    const onnxGroup = form.querySelector('#onnx-runtime-group');
    const tfliteGroup = form.querySelector('#tflite-delegate-group');
    if (modelType === 'tflite') {
        onnxGroup?.classList.add('hidden');
        tfliteGroup?.classList.remove('hidden');
    } else {
        onnxGroup?.classList.remove('hidden');
        tfliteGroup?.classList.add('hidden');
    }
}

function configureAccelerator(form, availability, selectedAccelerator) {
    const group = form.querySelector('#onnx-accelerator-group');
    const select = form.querySelector('#onnx-accelerator');
    if (!group || !select) return;

    const rknnAvailable = availability?.accelerators?.rknn;
    if (rknnAvailable) {
        group.classList.remove('hidden');
        const valid = ['none', 'rknn'];
        if (!valid.includes(selectedAccelerator)) {
            select.value = 'none';
        } else {
            select.value = selectedAccelerator;
        }
    } else {
        group.classList.add('hidden');
        select.value = 'none';
    }
}

async function populateLabelSelect(form, pipelineId, selectedClasses) {
    const select = form.querySelector('#target-class-filter');
    if (!select) return;
    const labels = await fetchLabels(pipelineId);
    select.innerHTML = '';
    labels.forEach(label => {
        const option = new Option(label, label);
        if (selectedClasses && selectedClasses.includes(label)) {
            option.selected = true;
        }
        select.appendChild(option);
    });
}

function getSelectedPipeline() {
    const pipelineSelect = document.getElementById('pipeline-select');
    const selectedOption = pipelineSelect.options[pipelineSelect.selectedIndex];
    if (!selectedOption || !selectedOption.value) return null;
    return currentPipelines.find(p => p.id == selectedOption.value);
}

export function updatePipelineForm(pipelineName) {
    document.querySelectorAll('.pipeline-form').forEach(form => {
        if (form.id === `form-${pipelineName}`) {
            form.classList.remove('hidden');
        } else {
            form.classList.add('hidden');
        }
    });
}

export async function loadPipelineConfig(pipelineData) {
    let config = {};
    try {
        config = pipelineData.config ? JSON.parse(pipelineData.config) : {};
    } catch (e) {
        console.error("Error parsing pipeline config:", e);
        config = {}; // Fallback to default
    }

    if (pipelineData.pipeline_type === 'AprilTag') {
        const form = document.getElementById('form-AprilTag');
        const setSliderValue = (baseId, value) => {
            const slider = form.querySelector(`#${baseId}`);
            const number = form.querySelector(`#${baseId}-value`);
            if (slider) slider.value = value;
            if (number) number.value = value;
        };
        form.querySelector('#target-family').value = config.family || 'tag36h11';
        form.querySelector('#tag-size').value = config.tag_size_m || 0.165;
        form.querySelector('#refine-edges').checked = config.refine_edges !== undefined ? config.refine_edges : true;
        setSliderValue('threads', config.threads || 2);
        setSliderValue('decimate', config.decimate || 1.0);
        setSliderValue('blur', config.blur || 0.0);
        setSliderValue('decision-margin', config.decision_margin || 35);
        setSliderValue('pose-iterations', config.pose_iterations || 40);
    } else if (pipelineData.pipeline_type === 'Coloured Shape') {
        const form = document.getElementById('form-Coloured Shape');
        const setSliderValue = (baseId, value) => {
            form.querySelector(`#${baseId}`).value = value;
            form.querySelector(`#${baseId}-value`).value = value;
        };
        setSliderValue('hue-min', config.hue_min !== undefined ? config.hue_min : 0);
        setSliderValue('hue-max', config.hue_max !== undefined ? config.hue_max : 179);
        setSliderValue('saturation-min', config.saturation_min !== undefined ? config.saturation_min : 0);
        setSliderValue('saturation-max', config.saturation_max !== undefined ? config.saturation_max : 255);
        setSliderValue('value-min', config.value_min !== undefined ? config.value_min : 0);
        setSliderValue('value-max', config.value_max !== undefined ? config.value_max : 255);
        setSliderValue('min-area', config.min_area !== undefined ? config.min_area : 100);
        setSliderValue('max-area', config.max_area !== undefined ? config.max_area : 10000);
        setSliderValue('min-aspect-ratio', config.min_aspect_ratio !== undefined ? config.min_aspect_ratio : 0.5);
        setSliderValue('max-aspect-ratio', config.max_aspect_ratio !== undefined ? config.max_aspect_ratio : 2.0);
        setSliderValue('min-fullness', config.min_fullness !== undefined ? config.min_fullness : 0.4);
    } else if (pipelineData.pipeline_type === 'Object Detection (ML)') {
        const form = document.getElementById('form-Object Detection (ML)');
        const availability = await fetchMlAvailability();
        const setSliderValue = (baseId, value) => {
            const slider = form.querySelector(`#${baseId}`);
            const number = form.querySelector(`#${baseId}-value`);
            if (slider) slider.value = value;
            if (number) number.value = value;
        };
        const modelFilenameDiv = form.querySelector('#model-file-filename');
        const deleteModelBtn = form.querySelector('#delete-model-btn');
        if (config.model_filename) {
            modelFilenameDiv.textContent = config.model_filename;
            deleteModelBtn.classList.remove('hidden');
        } else {
            modelFilenameDiv.textContent = '';
            deleteModelBtn.classList.add('hidden');
        }
        const labelsFilenameDiv = form.querySelector('#labels-file-filename');
        const deleteLabelsBtn = form.querySelector('#delete-labels-btn');
        if (config.labels_filename) {
            labelsFilenameDiv.textContent = config.labels_filename;
            deleteLabelsBtn.classList.remove('hidden');
        } else {
            labelsFilenameDiv.textContent = '';
            deleteLabelsBtn.classList.add('hidden');
        }
        const modelType = (config.model_type || 'yolo').toLowerCase();
        const modelTypeInput = form.querySelector('#ml-model-type');
        if (modelTypeInput) modelTypeInput.value = modelType.toUpperCase();
        toggleRuntimeSections(form, modelType);
        if (modelType === 'tflite') {
            const delegates = availability?.tflite?.delegates || ['CPU'];
            populateSelectOptions(
                form.querySelector('#tflite-delegate'),
                delegates,
                config.tflite_delegate || delegates[0]
            );
            const acceleratorSelect = form.querySelector('#onnx-accelerator');
            if (acceleratorSelect) acceleratorSelect.value = 'none';
            form.querySelector('#onnx-accelerator-group')?.classList.add('hidden');
        } else {
            const providers = availability?.onnx?.providers || ['CPUExecutionProvider'];
            populateSelectOptions(
                form.querySelector('#onnx-provider'),
                providers,
                config.onnx_provider || providers[0]
            );
            configureAccelerator(form, availability, config.accelerator || 'none');
        }
        setSliderValue('confidence-threshold', config.confidence_threshold !== undefined ? config.confidence_threshold : 0.5);
        setSliderValue('nms-iou-threshold', config.nms_iou_threshold !== undefined ? config.nms_iou_threshold : 0.45);
        const imgSizeInput = form.querySelector('#img-size');
        if (imgSizeInput) imgSizeInput.value = config.img_size || 640;
        const maxDetectionsInput = form.querySelector('#max-detections');
        if (maxDetectionsInput) maxDetectionsInput.value = config.max_detections || 100;
        await populateLabelSelect(form, pipelineData.id, config.target_classes || []);
    }

    try {
        pipelineData.config = JSON.stringify(config);
    } catch (error) {
        console.error('Failed to serialise pipeline config for caching:', error);
    }
}

export async function updatePipelineDetails(updateFeedSourceCallback) {
    const pipelineSelect = document.getElementById('pipeline-select');
    const pipelineTypeSelect = document.getElementById('pipeline-type-select');
    const selectedOption = pipelineSelect.options[pipelineSelect.selectedIndex];

    if (selectedOption && selectedOption.value) {
        const pipelineType = selectedOption.dataset.type;
        pipelineTypeSelect.value = pipelineType;
        updatePipelineForm(pipelineType);

        const pipelineData = currentPipelines.find(p => p.id == selectedOption.value);
        if (pipelineData) {
            await loadPipelineConfig(pipelineData);
        }
    } else {
        document.querySelectorAll('.pipeline-form').forEach(form => form.classList.add('hidden'));
    }
    if (updateFeedSourceCallback) updateFeedSourceCallback();
}

export async function updatePipelineList(cameraId, updateFeedSourceCallback) {
    const pipelineSelect = document.getElementById('pipeline-select');
    const pipelineTypeSelect = document.getElementById('pipeline-type-select');

    if (!cameraId) {
        pipelineSelect.innerHTML = '<option value="">No camera selected</option>';
        pipelineTypeSelect.disabled = true;
        if (updateFeedSourceCallback) updateFeedSourceCallback();
        return;
    }

    pipelineTypeSelect.disabled = false;

    try {
        const pipelines = await getPipelinesForCamera(cameraId);
        currentPipelines = pipelines;
        pipelineSelect.innerHTML = '';

        if (pipelines.length > 0) {
            pipelines.forEach(pipeline => {
                const option = new Option(pipeline.name, pipeline.id);
                option.dataset.type = pipeline.pipeline_type;
                pipelineSelect.appendChild(option);
            });
        } else {
            pipelineSelect.innerHTML = '<option value="">No pipelines configured</option>';
        }
        await updatePipelineDetails(updateFeedSourceCallback);
    } catch (error) {
        console.error("Failed to update pipeline list:", error);
    }
}

export async function savePipelineConfig() {
    const pipeline = getSelectedPipeline();
    if (!pipeline) return;

    let config;
    try {
        config = pipeline.config ? JSON.parse(pipeline.config) : {};
    } catch (error) {
        console.error('Failed to parse existing pipeline config, using defaults:', error);
        config = {};
    }

    if (pipeline.pipeline_type === 'AprilTag') {
        const form = document.getElementById('form-AprilTag');
        config = {
            family: form.querySelector('#target-family').value,
            tag_size_m: parseFloat(form.querySelector('#tag-size').value),
            threads: parseInt(form.querySelector('#threads-value').value, 10),
            decimate: parseFloat(form.querySelector('#decimate-value').value),
            blur: parseFloat(form.querySelector('#blur-value').value),
            refine_edges: form.querySelector('#refine-edges').checked,
            decision_margin: parseInt(form.querySelector('#decision-margin-value').value, 10),
            pose_iterations: parseInt(form.querySelector('#pose-iterations-value').value, 10),
        };
    } else if (pipeline.pipeline_type === 'Coloured Shape') {
        const form = document.getElementById('form-Coloured Shape');
        config = {
            'hue_min': parseInt(form.querySelector('#hue-min-value').value, 10),
            'hue_max': parseInt(form.querySelector('#hue-max-value').value, 10),
            'saturation_min': parseInt(form.querySelector('#saturation-min-value').value, 10),
            'saturation_max': parseInt(form.querySelector('#saturation-max-value').value, 10),
            'value_min': parseInt(form.querySelector('#value-min-value').value, 10),
            'value_max': parseInt(form.querySelector('#value-max-value').value, 10),
            'min_area': parseInt(form.querySelector('#min-area-value').value, 10),
            'max_area': parseInt(form.querySelector('#max-area-value').value, 10),
            'min_aspect_ratio': parseFloat(form.querySelector('#min-aspect-ratio-value').value),
            'max_aspect_ratio': parseFloat(form.querySelector('#max-aspect-ratio-value').value),
            'min_fullness': parseFloat(form.querySelector('#min-fullness-value').value),
        };
    } else if (pipeline.pipeline_type === 'Object Detection (ML)') {
        const form = document.getElementById('form-Object Detection (ML)');
        const selectedClasses = Array.from(form.querySelector('#target-class-filter').selectedOptions).map(opt => opt.value);

        const modelTypeRaw = form.querySelector('#ml-model-type')?.value || 'YOLO';
        const modelType = modelTypeRaw.toLowerCase();
        const confidence = parseFloat(form.querySelector('#confidence-threshold-value').value);
        const nmsIou = parseFloat(form.querySelector('#nms-iou-threshold-value').value);
        const imgSize = parseInt(form.querySelector('#img-size').value, 10);
        const maxDetections = parseInt(form.querySelector('#max-detections').value, 10);
        const modelFilenameText = form.querySelector('#model-file-filename').textContent?.trim() || null;
        const labelsFilenameText = form.querySelector('#labels-file-filename').textContent?.trim() || null;

        config.model_filename = modelFilenameText || null;
        config.labels_filename = labelsFilenameText || null;
        config.confidence_threshold = Number.isFinite(confidence) ? confidence : 0.5;
        config.nms_iou_threshold = Number.isFinite(nmsIou) ? nmsIou : 0.45;
        config.target_classes = selectedClasses;
        config.img_size = Number.isInteger(imgSize) ? imgSize : 640;
        config.max_detections = Number.isInteger(maxDetections) ? maxDetections : 100;
        config.model_type = modelType;

        if (modelType === 'tflite') {
            const delegateSelect = form.querySelector('#tflite-delegate');
            config.tflite_delegate = delegateSelect && delegateSelect.value ? delegateSelect.value : 'CPU';
            delete config.onnx_provider;
            config.accelerator = 'none';
        } else {
            const providerSelect = form.querySelector('#onnx-provider');
            config.onnx_provider = providerSelect && providerSelect.value ? providerSelect.value : 'CPUExecutionProvider';
            const acceleratorSelect = form.querySelector('#onnx-accelerator');
            config.accelerator = acceleratorSelect && acceleratorSelect.value ? acceleratorSelect.value : 'none';
            delete config.tflite_delegate;
        }
    }

    try {
        await updatePipelineConfig(pipeline.id, config);
        pipeline.config = JSON.stringify(config);
        console.log(`Pipeline ${pipeline.id} config saved.`);
    } catch (error) {
        console.error('Error saving pipeline config:', error);
    }
}

export async function addPipeline(cameraId, updateFeedSourceCallback) {
    if (!cameraId) return;
    const pipelineName = prompt("Enter pipeline name", "default");
    if (!pipelineName) return;

    try {
        await addPipelineToCamera(cameraId, pipelineName, 'AprilTag');
        await updatePipelineList(cameraId, updateFeedSourceCallback);
    } catch (error) {
        console.error("Failed to add pipeline:", error);
    }
}

export async function updatePipeline() {
    const pipeline = getSelectedPipeline();
    if (!pipeline) return;

    const newName = prompt("Enter new name", pipeline.name);
    if (!newName) return;

    try {
        await apiUpdatePipeline(pipeline.id, newName, pipeline.pipeline_type);
        const pipelineSelect = document.getElementById('pipeline-select');
        const selectedOption = pipelineSelect.options[pipelineSelect.selectedIndex];
        if (selectedOption) {
            selectedOption.textContent = newName;
            const updatedPipeline = currentPipelines.find(p => p.id == pipeline.id);
            if (updatedPipeline) updatedPipeline.name = newName;
        }
    } catch (error) {
        console.error("Failed to update pipeline:", error);
    }
}

export async function updatePipelineType(updateFeedSourceCallback) {
    const pipeline = getSelectedPipeline();
    if (!pipeline) return;

    const pipelineTypeSelect = document.getElementById('pipeline-type-select');
    const newType = pipelineTypeSelect.value;
    const isConfirmed = confirm('Changing the pipeline will erase all current pipeline settings. Are you sure?');
    if (!isConfirmed) {
        pipelineTypeSelect.value = pipeline.pipeline_type; // Revert selection
        return;
    }

    try {
        await apiUpdatePipeline(pipeline.id, pipeline.name, newType);
        const pipelineSelect = document.getElementById('pipeline-select');
        const selectedOption = pipelineSelect.options[pipelineSelect.selectedIndex];
        if (selectedOption) {
            selectedOption.dataset.type = newType;
            const updatedPipeline = currentPipelines.find(p => p.id == pipeline.id);
            if (updatedPipeline) updatedPipeline.pipeline_type = newType;
        }
        await updatePipelineDetails(updateFeedSourceCallback);
    } catch (error) {
        console.error("Failed to update pipeline type:", error);
    }
}

export async function deletePipeline(cameraId, updateFeedSourceCallback) {
    const pipeline = getSelectedPipeline();
    if (!pipeline) return;

    if (confirm('Are you sure you want to delete this pipeline?')) {
        try {
            await apiDeletePipeline(pipeline.id);
            await updatePipelineList(cameraId, updateFeedSourceCallback);
        } catch (error) {
            console.error("Failed to delete pipeline:", error);
        }
    }
}

export async function uploadFile(event) {
    const pipeline = getSelectedPipeline();
    if (!pipeline) return;

    const fileInput = event.target;
    const file = fileInput.files[0];
    const fileType = fileInput.dataset.type;

    if (file) {
        try {
            const data = await uploadFileToPipeline(pipeline.id, file, fileType);
            if (data.success) {
                if (data.config) {
                    pipeline.config = JSON.stringify(data.config);
                    const index = currentPipelines.findIndex(p => p.id === pipeline.id);
                    if (index >= 0) currentPipelines[index] = { ...currentPipelines[index], config: pipeline.config };
                }
                if (fileType === 'labels') {
                    labelsCache.delete(pipeline.id);
                }
                await loadPipelineConfig(pipeline);
                document.getElementById(`delete-${fileType}-btn`).classList.remove('hidden');
                if (fileInput) fileInput.value = '';
            }
        } catch (error) {
            console.error('Error uploading file:', error);
        }
    }
}

export async function deleteFile(type) {
    const pipeline = getSelectedPipeline();
    if (!pipeline) return;

    try {
        const data = await deleteFileFromPipeline(pipeline.id, type);
        if (data.success) {
            if (data.config) {
                pipeline.config = JSON.stringify(data.config);
                const index = currentPipelines.findIndex(p => p.id === pipeline.id);
                if (index >= 0) currentPipelines[index] = { ...currentPipelines[index], config: pipeline.config };
            }
            if (type === 'labels') {
                labelsCache.delete(pipeline.id);
            }
            const fileInput = document.getElementById(`${type}-file-upload`);
            if (fileInput) fileInput.value = '';
            await loadPipelineConfig(pipeline);
        }
    } catch (error) {
        console.error('Error deleting file:', error);
    }
}
