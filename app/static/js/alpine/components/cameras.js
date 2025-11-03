import { fetchJson } from '../helpers.js';

function normaliseCameras(cameras = []) {
    return cameras.map((camera) => ({
        ...camera,
        id: String(camera.id),
    }));
}

export function registerCamerasComponents(Alpine) {
    if (!Alpine) {
        return;
    }

    Alpine.data('camerasApp', (config = {}) => ({
        cameras: [],
        genicamEnabled: Boolean(config.genicam_enabled),
        camerasLoading: false,
        camerasError: '',
        status: {},
        nodePanels: {},
        realsensePanels: {},
        statusInterval: null,
        addModal: {
            open: false,
            loading: false,
            error: '',
            name: '',
            camera_type: '',
            options: { usb: [], genicam: [], oakd: [], realsense: [] },
            selections: { usb: '', genicam: '', oakd: '', realsense: '' },
        },
        editModal: {
            open: false,
            camera_id: '',
            name: '',
        },

        init() {
            this.$watch('addModal.camera_type', (value) => this.onAddCameraTypeChange(value));
            this.bootstrapCameras();
            document.addEventListener('visibilitychange', () => {
                if (document.visibilityState === 'visible') {
                    this.startStatusPolling();
                } else {
                    this.stopStatusPolling();
                }
            });
        },

        bootstrapCameras() {
            this.reloadCameras();
        },

        onCamerasUpdated() {
            // Preserve existing panel states before reset
            const oldNodePanels = this.nodePanels;
            const oldRealsensePanels = this.realsensePanels;

            this.status = {};
            this.nodePanels = {};
            this.realsensePanels = {};
            this.cameras.forEach((camera) => {
                this.status[camera.id] = { loading: true, connected: null };
                // Only preserve panels that were already open, don't create new ones
                if (camera.camera_type === 'GenICam' && oldNodePanels[camera.id]) {
                    this.nodePanels[camera.id] = oldNodePanels[camera.id];
                }
                if (camera.camera_type === 'RealSense' && oldRealsensePanels[camera.id]) {
                    this.realsensePanels[camera.id] = oldRealsensePanels[camera.id];
                }
            });
            if (document.visibilityState !== 'hidden') {
                this.startStatusPolling();
            }
        },

        async reloadCameras() {
            if (this.camerasLoading) {
                return;
            }
            this.camerasLoading = true;
            this.camerasError = '';
            try {
                const response = await fetchJson('/api/cameras');
                const cameras = response.data;
                this.cameras = normaliseCameras(cameras);
                this.onCamerasUpdated();
            } catch (error) {
                this.camerasError = error.message || 'Failed to load cameras';
                if (!this.cameras.length) {
                    this.status = {};
                    this.nodePanels = {};
                    this.stopStatusPolling();
                }
            } finally {
                this.camerasLoading = false;
            }
        },

        createNodePanelState() {
            return {
                open: false,
                loading: false,
                error: '',
                nodes: [],
                filter: {
                    query: '',
                    showAll: false,
                },
            };
        },

        startStatusPolling() {
            this.stopStatusPolling();
            if (!this.cameras.length) {
                return;
            }
            this.refreshStatuses();
            this.statusInterval = window.setInterval(() => this.refreshStatuses(), 5000);
        },

        stopStatusPolling() {
            if (this.statusInterval) {
                clearInterval(this.statusInterval);
                this.statusInterval = null;
            }
        },

        async refreshStatuses() {
            await Promise.all(
                this.cameras.map(async (camera) => {
                    try {
                        const response = await fetchJson(`/cameras/status/${camera.id}`);
                        this.status[camera.id] = {
                            loading: false,
                            connected: Boolean(response?.data?.connected),
                        };
                    } catch (error) {
                        this.status[camera.id] = {
                            loading: false,
                            connected: null,
                            error: error.message,
                        };
                    }
                }),
            );
        },

        ensureNodePanel(cameraId) {
            if (!this.nodePanels[cameraId]) {
                this.nodePanels[cameraId] = this.createNodePanelState();
            }
            return this.nodePanels[cameraId];
        },

        toggleNodePanel(cameraId) {
            const panel = this.ensureNodePanel(cameraId);
            panel.open = !panel.open;
            if (panel.open && !panel.nodes.length) {
                this.loadNodeMap(cameraId);
            }
        },

        async loadNodeMap(cameraId, { force = false } = {}) {
            const panel = this.ensureNodePanel(cameraId);
            if (panel.loading) return;
            if (!force && panel.nodes.length) return;

            panel.loading = true;
            panel.error = '';
            try {
                const response = await fetchJson(`/cameras/genicam/nodes/${cameraId}`);
                panel.nodes = (response?.data?.nodes || []).map((node) => ({
                    ...node,
                    workingValue: node.value,
                    saving: false,
                    feedback: '',
                    feedbackType: 'success',
                }));
            } catch (error) {
                panel.error = error.message || 'Failed to load nodes';
                panel.nodes = [];
            } finally {
                panel.loading = false;
            }
        },

        filteredNodes(cameraId) {
            const panel = this.ensureNodePanel(cameraId);
            const nodes = panel.nodes || [];
            if (!nodes.length) return [];

            const query = panel.filter.query.trim().toLowerCase();
            return nodes.filter((node) => {
                if (!panel.filter.showAll) {
                    const hasDescription = node.description && node.description.trim() !== '';
                    if (!hasDescription) return false;
                    if (node.value === null || node.value === undefined || node.value === '') return false;
                    if (node.access_mode === 'RO') return false;
                }

                if (!query) return true;
                const haystack = `${node.name} ${node.display_name || ''} ${node.description || ''}`.toLowerCase();
                return haystack.includes(query);
            });
        },

        async submitNode(cameraId, node) {
            if (!node?.name) return;
            node.saving = true;
            node.feedback = '';
            node.feedbackType = 'success';
            try {
                const response = await fetchJson(`/cameras/genicam/nodes/${cameraId}`, {
                    method: 'POST',
                    body: JSON.stringify({
                        name: node.name,
                        value: node.workingValue,
                    }),
                });
                const updated = response?.data?.node;
                if (updated) {
                    Object.assign(node, {
                        ...node,
                        ...updated,
                        workingValue: updated.value,
                    });
                }
                node.feedback = response?.message || 'Node updated';
                node.feedbackType = 'success';
            } catch (error) {
                node.feedback = error.message || 'Failed to update node';
                node.feedbackType = 'error';
            } finally {
                node.saving = false;
                if (node.feedback) {
                    window.setTimeout(() => {
                        node.feedback = '';
                    }, 3000);
                }
            }
        },

        createRealSensePanelState() {
            return {
                open: false,
                loading: false,
                error: '',
                saving: false,
                feedback: '',
                feedbackType: 'success',
                resolutions: [],
                selectedResolution: '',
                fps: 30,
                depthEnabled: false,
            };
        },

        ensureRealSensePanel(cameraId) {
            if (!this.realsensePanels[cameraId]) {
                this.realsensePanels[cameraId] = this.createRealSensePanelState();
            }
            return this.realsensePanels[cameraId];
        },

        toggleRealSensePanel(cameraId) {
            const panel = this.ensureRealSensePanel(cameraId);
            panel.open = !panel.open;
            if (panel.open && !panel.resolutions.length) {
                this.loadRealSenseConfig(cameraId);
            }
        },

        async loadRealSenseConfig(cameraId, { force = false } = {}) {
            const panel = this.ensureRealSensePanel(cameraId);
            if (panel.loading) return;
            if (!force && panel.resolutions.length) return;

            panel.loading = true;
            panel.error = '';
            try {
                const response = await fetchJson(`/cameras/realsense/resolutions/${cameraId}`);
                const resolutions = response?.data?.resolutions || [];
                const current = response?.data?.current || {};

                // Group resolutions by unique width x height
                const uniqueResolutions = [];
                const seen = new Set();
                resolutions.forEach((res) => {
                    const key = `${res.width}x${res.height}`;
                    if (!seen.has(key)) {
                        seen.add(key);
                        uniqueResolutions.push(res);
                    }
                });

                panel.resolutions = uniqueResolutions;

                // Set current values
                if (current.resolution) {
                    panel.selectedResolution = `${current.resolution.width}x${current.resolution.height}`;
                } else if (uniqueResolutions.length > 0) {
                    // Default to first (highest) resolution
                    panel.selectedResolution = `${uniqueResolutions[0].width}x${uniqueResolutions[0].height}`;
                }

                panel.fps = current.fps || 30;
                panel.depthEnabled = current.depth_enabled || false;
            } catch (error) {
                panel.error = error.message || 'Failed to load RealSense configuration';
                panel.resolutions = [];
            } finally {
                panel.loading = false;
            }
        },

        async submitRealSenseConfig(cameraId) {
            const panel = this.ensureRealSensePanel(cameraId);
            if (panel.saving) return;

            panel.saving = true;
            panel.feedback = '';
            panel.feedbackType = 'success';

            try {
                // Parse selected resolution
                const [width, height] = panel.selectedResolution.split('x').map(Number);

                const payload = await fetchJson(`/cameras/realsense/config/${cameraId}`, {
                    method: 'POST',
                    body: JSON.stringify({
                        width,
                        height,
                        fps: panel.fps,
                        depth_enabled: panel.depthEnabled,
                    }),
                });

                panel.feedback = payload?.message || 'Configuration updated successfully';
                panel.feedbackType = 'success';

                // Reload cameras to get updated status
                setTimeout(() => {
                    this.reloadCameras();
                }, 1000);
            } catch (error) {
                panel.feedback = error.message || 'Failed to update configuration';
                panel.feedbackType = 'error';
            } finally {
                panel.saving = false;
                if (panel.feedback) {
                    window.setTimeout(() => {
                        panel.feedback = '';
                    }, 5000);
                }
            }
        },

        openAddModal() {
            this.addModal = {
                open: true,
                loading: false,
                error: '',
                name: '',
                camera_type: '',
                options: { usb: [], genicam: [], oakd: [], realsense: [] },
                selections: { usb: '', genicam: '', oakd: '', realsense: '' },
            };
            this.fetchDiscovery();
        },

        closeAddModal() {
            this.addModal.open = false;
        },

        async fetchDiscovery() {
            this.addModal.loading = true;
            this.addModal.error = '';
            try {
                const existing = this.cameras
                    .map((camera) => camera.identifier)
                    .filter(Boolean)
                    .join(',');
                const payload = await fetchJson(`/cameras/discover?existing=${encodeURIComponent(existing)}`);
                const data = payload?.data || payload;
                this.addModal.options = {
                    usb: data?.USB || [],
                    genicam: data?.GenICam || [],
                    oakd: data?.['OAK-D'] || [],
                    realsense: data?.RealSense || [],
                };
                this.onAddCameraTypeChange(this.addModal.camera_type);
            } catch (error) {
                this.addModal.error = error.message || 'Failed to discover cameras';
            } finally {
                this.addModal.loading = false;
            }
        },

        onAddCameraTypeChange(type) {
            if (!type) {
                this.addModal.selections = { usb: '', genicam: '', oakd: '', realsense: '' };
                return;
            }
            const options = this.getDiscoveryOptions(type);
            if (options.length === 1) {
                const [{ identifier }] = options;
                this.setAddSelection(type, identifier);
            } else {
                this.setAddSelection(type, '');
            }
        },

        getDiscoveryOptions(type) {
            if (type === 'USB') return this.addModal.options.usb || [];
            if (type === 'GenICam') return this.addModal.options.genicam || [];
            if (type === 'OAK-D') return this.addModal.options.oakd || [];
            if (type === 'RealSense') return this.addModal.options.realsense || [];
            return [];
        },

        setAddSelection(type, identifier) {
            if (type === 'USB') {
                this.addModal.selections.usb = identifier;
            } else if (type === 'GenICam') {
                this.addModal.selections.genicam = identifier;
            } else if (type === 'OAK-D') {
                this.addModal.selections.oakd = identifier;
            } else if (type === 'RealSense') {
                this.addModal.selections.realsense = identifier;
            }
        },

        isAddFormValid() {
            const nameValid = this.addModal.name.trim().length > 0;
            if (!nameValid) return false;
            const type = this.addModal.camera_type;
            if (!type) return false;

            if (type === 'USB') return Boolean(this.addModal.selections.usb);
            if (type === 'GenICam') return Boolean(this.addModal.selections.genicam);
            if (type === 'OAK-D') return Boolean(this.addModal.selections.oakd);
            if (type === 'RealSense') return Boolean(this.addModal.selections.realsense);
            return false;
        },

        openEditModal(camera) {
            this.editModal = {
                open: true,
                camera_id: camera.id,
                name: camera.name,
            };
        },

        closeEditModal() {
            this.editModal.open = false;
        },

        deleteConfirmationMessage(camera) {
            return `Are you sure you want to delete ${camera.name}?`;
        },
    }));
}
