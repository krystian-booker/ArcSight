import {
    getCameraControls,
    updateCameraControls,
    getCameraResults
} from '../api.js';
import { updateFeedSource } from '../components/cameraFeed.js';
import {
    updatePipelineList,
    updatePipelineDetails,
    savePipelineConfig,
    addPipeline,
    updatePipeline,
    updatePipelineType,
    deletePipeline,
    uploadFile,
    deleteFile
} from '../components/pipelineManager.js';

document.addEventListener('DOMContentLoaded', function() {
    // --- DOM Elements ---
    const cameraSelect = document.getElementById('camera-select');
    const pipelineSelect = document.getElementById('pipeline-select');
    const pipelineTypeSelect = document.getElementById('pipeline-type-select');
    const addPipelineBtn = document.getElementById('add-pipeline-btn');
    const editPipelineBtn = document.getElementById('edit-pipeline-btn');
    const deletePipelineBtn = document.getElementById('delete-pipeline-btn');
    const feedContainer = document.querySelector('.camera-feed-container');
    const feedTypeRadios = document.querySelectorAll('input[name="feed-type"]');
    const processedFeedRadio = document.querySelector('input[value="processed"]');
    
    let resultsInterval;

    // --- Debounce Helper ---
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    const debouncedSave = debounce(() => savePipelineConfig(), 500);
    const debouncedControlSave = debounce(() => saveControls(), 500);

    // --- Camera Control Functions ---
    async function populateCameraControls(cameraId) {
        if (!cameraId) {
            document.getElementById('orientation-select').disabled = true;
            document.getElementById('exposure-mode-select').disabled = true;
            document.getElementById('exposure-slider').disabled = true;
            document.getElementById('exposure-value').disabled = true;
            document.getElementById('gain-mode-select').disabled = true;
            document.getElementById('gain-slider').disabled = true;
            document.getElementById('gain-value').disabled = true;
            return;
        }

        document.getElementById('orientation-select').disabled = false;
        document.getElementById('exposure-mode-select').disabled = false;
        document.getElementById('gain-mode-select').disabled = false;

        try {
            const data = await getCameraControls(cameraId);
            document.getElementById('orientation-select').value = data.orientation;
            
            const exposureModeSelect = document.getElementById('exposure-mode-select');
            const exposureSlider = document.getElementById('exposure-slider');
            const exposureValue = document.getElementById('exposure-value');
            exposureModeSelect.value = data.exposure_mode;
            exposureSlider.value = data.exposure_value;
            exposureValue.value = data.exposure_value;
            exposureSlider.disabled = data.exposure_mode === 'auto';
            exposureValue.disabled = data.exposure_mode === 'auto';

            const gainModeSelect = document.getElementById('gain-mode-select');
            const gainSlider = document.getElementById('gain-slider');
            const gainValue = document.getElementById('gain-value');
            gainModeSelect.value = data.gain_mode;
            gainSlider.value = data.gain_value;
            gainValue.value = data.gain_value;
            gainSlider.disabled = data.gain_mode === 'auto';
            gainValue.disabled = data.gain_mode === 'auto';
        } catch (error) {
            console.error('Error fetching camera controls:', error);
        }
    }

    async function saveControls() {
        const cameraId = cameraSelect.value;
        if (!cameraId) return;

        const controls = {
            orientation: parseInt(document.getElementById('orientation-select').value, 10),
            exposure_mode: document.getElementById('exposure-mode-select').value,
            exposure_value: parseInt(document.getElementById('exposure-value').value, 10),
            gain_mode: document.getElementById('gain-mode-select').value,
            gain_value: parseInt(document.getElementById('gain-value').value, 10),
        };

        try {
            const data = await updateCameraControls(cameraId, controls);
            if (data.success) {
                console.log('Camera controls saved successfully');
                await updateFeedSource(cameraSelect, pipelineSelect, feedContainer, processedFeedRadio);
            }
        } catch (error) {
            console.error('Error saving camera controls:', error);
        }
    }
    
    // --- Results Update Functions ---
    function updateAprilTagTable(results) {
        const tbody = document.getElementById('apriltag-targets-tbody');
        if (!tbody) return;
        tbody.innerHTML = '';
        if (!results || !results.detections || results.detections.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-gray-500 py-4">No targets detected</td></tr>';
            return;
        }
        results.detections.forEach(tag => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">${tag.id || 'N/A'}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${tag.x_m !== undefined ? tag.x_m.toFixed(3) : 'N/A'}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${tag.y_m !== undefined ? tag.y_m.toFixed(3) : 'N/A'}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${tag.z_m !== undefined ? tag.z_m.toFixed(3) : 'N/A'}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${tag.yaw_deg !== undefined ? tag.yaw_deg.toFixed(2) : 'N/A'}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${tag.pitch_deg !== undefined ? tag.pitch_deg.toFixed(2) : 'N/A'}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${tag.roll_deg !== undefined ? tag.roll_deg.toFixed(2) : 'N/A'}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${tag.pose_error !== undefined ? tag.pose_error.toFixed(4) : 'N/A'}</td>
            `;
            tbody.appendChild(row);
        });
    }

    function updateObjectDetectionTable(results) {
        const tbody = document.getElementById('ml-targets-tbody');
        if (!tbody) return;
        tbody.innerHTML = '';
        if (!results || !results.detections || results.detections.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-gray-500 py-4">No targets detected</td></tr>';
            return;
        }
        results.detections.forEach(det => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">${det.label}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">N/A</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">N/A</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">N/A</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${det.confidence.toFixed(3)}</td>
            `;
            tbody.appendChild(row);
        });
    }

    async function startResultsUpdates(cameraId) {
        if (resultsInterval) clearInterval(resultsInterval);
        if (!cameraId) return;

        resultsInterval = setInterval(async () => {
            try {
                const data = await getCameraResults(cameraId);
                const selectedPipelineId = pipelineSelect.value;
                if (selectedPipelineId && data[selectedPipelineId]) {
                    const pipelineResults = data[selectedPipelineId];
                    const pipelineType = pipelineSelect.options[pipelineSelect.selectedIndex].dataset.type;
                    if (pipelineType === 'AprilTag') updateAprilTagTable(pipelineResults);
                    else if (pipelineType === 'Object Detection (ML)') updateObjectDetectionTable(pipelineResults);
                } else {
                    updateAprilTagTable(null);
                    updateObjectDetectionTable(null);
                }
            } catch (error) {
                console.error('Error fetching results:', error);
                updateAprilTagTable(null);
                updateObjectDetectionTable(null);
            }
        }, 1000);
    }
    
    // --- Event Handlers ---
    const handleUpdateFeedSource = () => updateFeedSource(cameraSelect, pipelineSelect, feedContainer, processedFeedRadio);
    const handleUpdatePipelineDetails = () => updatePipelineDetails(handleUpdateFeedSource);
    const handleUpdatePipelineList = (cameraId) => updatePipelineList(cameraId, handleUpdateFeedSource);

    async function handleCameraChange() {
        const cameraId = cameraSelect.value;
        await handleUpdatePipelineList(cameraId);
        await populateCameraControls(cameraId);
        await startResultsUpdates(cameraId);
    }

    // --- Initialization ---
    async function initialize() {
        // Initial state setup
        const initialCameraId = cameraSelect.value;
        if (initialCameraId) {
            await handleUpdatePipelineList(initialCameraId);
            await populateCameraControls(initialCameraId);
            await startResultsUpdates(initialCameraId);
        } else {
            handleUpdateFeedSource();
        }

        // --- Event Listeners ---
        cameraSelect.addEventListener('change', handleCameraChange);
        pipelineSelect.addEventListener('change', handleUpdatePipelineDetails);
        feedTypeRadios.forEach(radio => radio.addEventListener('change', handleUpdateFeedSource));

        addPipelineBtn.addEventListener('click', () => addPipeline(cameraSelect.value, handleUpdateFeedSource));
        editPipelineBtn.addEventListener('click', updatePipeline);
        deletePipelineBtn.addEventListener('click', () => deletePipeline(cameraSelect.value, handleUpdateFeedSource));
        pipelineTypeSelect.addEventListener('change', () => updatePipelineType(handleUpdateFeedSource));

        // Camera Controls
        document.getElementById('orientation-select').addEventListener('change', debouncedControlSave);
        document.getElementById('exposure-mode-select').addEventListener('change', () => {
            const isManual = document.getElementById('exposure-mode-select').value === 'manual';
            document.getElementById('exposure-slider').disabled = !isManual;
            document.getElementById('exposure-value').disabled = !isManual;
            debouncedControlSave();
        });
        document.getElementById('exposure-slider').addEventListener('input', () => {
            document.getElementById('exposure-value').value = document.getElementById('exposure-slider').value;
            debouncedControlSave();
        });
        document.getElementById('exposure-value').addEventListener('change', () => {
             document.getElementById('exposure-slider').value = document.getElementById('exposure-value').value;
            debouncedControlSave();
        });

        document.getElementById('gain-mode-select').addEventListener('change', () => {
            const isManual = document.getElementById('gain-mode-select').value === 'manual';
            document.getElementById('gain-slider').disabled = !isManual;
            document.getElementById('gain-value').disabled = !isManual;
            debouncedControlSave();
        });
        document.getElementById('gain-slider').addEventListener('input', () => {
            document.getElementById('gain-value').value = document.getElementById('gain-slider').value;
            debouncedControlSave();
        });
        document.getElementById('gain-value').addEventListener('change', () => {
            document.getElementById('gain-slider').value = document.getElementById('gain-value').value;
            debouncedControlSave();
        });

        // Pipeline Form Controls
        document.querySelectorAll('.pipeline-form input, .pipeline-form select').forEach(input => {
            const eventType = input.type === 'range' ? 'input' : 'change';
            input.addEventListener(eventType, debouncedSave);
        });

        // File I/O
        document.getElementById('model-file-upload').addEventListener('change', uploadFile);
        document.getElementById('labels-file-upload').addEventListener('change', uploadFile);
        
        const deleteFileModal = document.getElementById('delete-file-modal');
        const confirmDeleteBtn = document.getElementById('confirm-delete-file');
        const cancelDeleteBtn = document.getElementById('cancel-delete-file');
        let fileToDeleteType = null;

        document.getElementById('delete-model-btn').addEventListener('click', (e) => {
            e.preventDefault();
            fileToDeleteType = 'model';
            deleteFileModal.classList.remove('hidden');
        });
        document.getElementById('delete-labels-btn').addEventListener('click', (e) => {
            e.preventDefault();
            fileToDeleteType = 'labels';
            deleteFileModal.classList.remove('hidden');
        });
        cancelDeleteBtn.addEventListener('click', () => deleteFileModal.classList.add('hidden'));
        confirmDeleteBtn.addEventListener('click', async () => {
            if (fileToDeleteType) {
                await deleteFile(fileToDeleteType);
            }
            deleteFileModal.classList.add('hidden');
        });
    }

    initialize();
});