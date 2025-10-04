import { getCameraStatus } from '../api.js';

export async function updateFeedSource(cameraSelect, pipelineSelect, feedContainer, processedFeedRadio) {
    const cameraId = cameraSelect.value;
    const pipelineId = pipelineSelect.value;

    const isPipelineSelected = pipelineId && pipelineSelect.options.length > 0 && pipelineSelect.options[pipelineSelect.selectedIndex]?.value;
    processedFeedRadio.disabled = !isPipelineSelected;

    let selectedFeedType = document.querySelector('input[name="feed-type"]:checked').value;

    if (selectedFeedType === 'processed' && processedFeedRadio.disabled) {
        document.querySelector('input[value="default"]').checked = true;
        selectedFeedType = 'default';
    }

    if (!cameraId) {
        feedContainer.innerHTML = '<p class="text-gray-500">No camera selected.</p>';
        const cameraFeed = document.getElementById('camera-feed');
        if (cameraFeed) cameraFeed.src = "";
        return;
    }

    let newFeedUrl = '';
    if (selectedFeedType === 'processed' && isPipelineSelected) {
        newFeedUrl = `/processed_video_feed/${pipelineId}?t=${new Date().getTime()}`;
    } else {
        newFeedUrl = `/video_feed/${cameraId}?t=${new Date().getTime()}`;
    }

    try {
        const data = await getCameraStatus(cameraId);
        const imgElement = `<img id="camera-feed" src="${newFeedUrl}" alt="Camera Feed" class="w-full h-full object-contain rounded">`;
        if (data.connected) {
            feedContainer.innerHTML = imgElement;
        } else {
            feedContainer.innerHTML = '<p class="text-red-500">Camera is not connected.</p>';
        }
    } catch (error) {
        console.error('Error checking camera status:', error);
        feedContainer.innerHTML = '<p class="text-red-500">Error checking camera status.</p>';
    }
}