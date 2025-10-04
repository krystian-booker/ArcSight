async function fetchJson(url, options = {}) {
    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ error: `HTTP error! status: ${response.status}` }));
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        return response.json();
    } catch (error) {
        console.error(`Fetch error for ${url}:`, error);
        throw error;
    }
}

export async function getCameraStatus(cameraId) {
    return fetchJson(`/cameras/status/${cameraId}`);
}

export async function getPipelinesForCamera(cameraId) {
    return fetchJson(`/api/cameras/${cameraId}/pipelines`);
}

export async function updatePipelineConfig(pipelineId, config) {
    return fetchJson(`/api/pipelines/${pipelineId}/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
    });
}

export async function addPipelineToCamera(cameraId, name, type) {
    return fetchJson(`/api/cameras/${cameraId}/pipelines`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, pipeline_type: type })
    });
}

export async function updatePipeline(pipelineId, name, type) {
    return fetchJson(`/api/pipelines/${pipelineId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, pipeline_type: type })
    });
}

export async function deletePipeline(pipelineId) {
    return fetchJson(`/api/pipelines/${pipelineId}`, {
        method: 'DELETE'
    });
}

export async function getCameraControls(cameraId) {
    return fetchJson(`/cameras/controls/${cameraId}`);
}

export async function updateCameraControls(cameraId, controls) {
    return fetchJson(`/cameras/update_controls/${cameraId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(controls)
    });
}

export async function getCameraResults(cameraId) {
    return fetchJson(`/cameras/results/${cameraId}`);
}

export async function uploadFileToPipeline(pipelineId, file, type) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('type', type);

    // fetchJson is not used here because we are not sending JSON
    const response = await fetch(`/api/pipelines/${pipelineId}/files`, {
        method: 'POST',
        body: formData
    });
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: `HTTP error! status: ${response.status}` }));
        throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
    }
    return response.json();
}

export async function deleteFileFromPipeline(pipelineId, type) {
    return fetchJson(`/api/pipelines/${pipelineId}/files`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type })
    });
}