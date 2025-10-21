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
        statusInterval: null,
        addModal: {
            open: false,
            loading: false,
            error: '',
            name: '',
            camera_type: '',
            options: { usb: [], genicam: [], oakd: [] },
            selections: { usb: '', genicam: '', oakd: '' },
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
            this.status = {};
            this.nodePanels = {};
            this.cameras.forEach((camera) => {
                this.status[camera.id] = { loading: true, connected: null };
                if (camera.camera_type === 'GenICam') {
                    this.nodePanels[camera.id] = this.createNodePanelState();
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
                const payload = await fetchJson('/api/cameras');
                this.cameras = normaliseCameras(payload || []);
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
                        const data = await fetchJson(`/cameras/status/${camera.id}`);
                        this.status[camera.id] = {
                            loading: false,
                            connected: Boolean(data?.connected),
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
                const payload = await fetchJson(`/cameras/genicam/nodes/${cameraId}`);
                panel.nodes = (payload?.nodes || []).map((node) => ({
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
                const payload = await fetchJson(`/cameras/genicam/nodes/${cameraId}`, {
                    method: 'POST',
                    body: JSON.stringify({
                        name: node.name,
                        value: node.workingValue,
                    }),
                });
                const updated = payload?.node;
                if (updated) {
                    Object.assign(node, {
                        ...node,
                        ...updated,
                        workingValue: updated.value,
                    });
                }
                node.feedback = payload?.message || 'Node updated';
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

        openAddModal() {
            this.addModal = {
                open: true,
                loading: false,
                error: '',
                name: '',
                camera_type: '',
                options: { usb: [], genicam: [], oakd: [] },
                selections: { usb: '', genicam: '', oakd: '' },
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
                this.addModal.options = {
                    usb: payload?.usb || [],
                    genicam: payload?.genicam || [],
                    oakd: payload?.oakd || [],
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
                this.addModal.selections = { usb: '', genicam: '', oakd: '' };
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
            return [];
        },

        setAddSelection(type, identifier) {
            if (type === 'USB') {
                this.addModal.selections.usb = identifier;
            } else if (type === 'GenICam') {
                this.addModal.selections.genicam = identifier;
            } else if (type === 'OAK-D') {
                this.addModal.selections.oakd = identifier;
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
