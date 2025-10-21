export function registerSettingsComponents(Alpine) {
    if (!Alpine) {
        return;
    }

    Alpine.data('settingsApp', (config = {}) => {
        const sortFieldNames = (names) => {
            if (!Array.isArray(names)) {
                return [];
            }
            const parseYear = (value) => {
                const match = /^(\d{4})/.exec(value);
                return match ? Number(match[1]) : 0;
            };
            return [...names].sort((a, b) => {
                const yearDiff = parseYear(b) - parseYear(a);
                if (yearDiff !== 0) {
                    return yearDiff;
                }
                return a.localeCompare(b);
            });
        };

        return {
            factoryResetOpen: false,
            endpoints: Object.assign(
                {
                    select: '',
                    upload: '',
                    delete: '',
                },
                config.endpoints || {},
            ),
            apriltag: {
                selectedField: typeof config.selectedField === 'string' ? config.selectedField : '',
                defaultFields: sortFieldNames(config.defaultFields),
                userFields: sortFieldNames(config.userFields),
                savingSelection: false,
                uploading: false,
                deleting: null,
            },
            sortFieldNames,

            toast(type, message) {
            if (!type || !message) {
                return;
            }
            const store = Alpine.store('toasts');
            if (store && typeof store.push === 'function') {
                store.push(message, type);
            } else {
                console.log(`[${type}] ${message}`);
            }
        },

        submitPost(url, confirmMessage = null) {
            if (confirmMessage && !window.confirm(confirmMessage)) {
                return;
            }
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = url;
            document.body.appendChild(form);
            form.submit();
        },

        openFactoryResetModal() {
            this.factoryResetOpen = true;
        },

        closeFactoryResetModal() {
            this.factoryResetOpen = false;
        },

        confirmFactoryReset(url) {
            this.submitPost(url);
            this.closeFactoryResetModal();
        },

        triggerImport() {
            this.$refs.importInput?.click();
        },

        handleImportChange(event) {
            event.target.form?.submit();
        },

        async saveApriltagFieldSelection() {
            if (!this.endpoints.select) {
                this.toast('error', 'Selection endpoint unavailable');
                return;
            }
            this.apriltag.savingSelection = true;
            try {
                const response = await fetch(this.endpoints.select, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        field_name: this.apriltag.selectedField || '',
                    }),
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || 'Failed to save selection');
                }
                this.apriltag.selectedField = data.selected || '';
                this.toast(
                    'success',
                    data.selected
                        ? `Selected AprilTag field ${data.selected}`
                        : 'Cleared AprilTag field selection',
                );
            } catch (error) {
                this.toast('error', error.message || 'Failed to save selection');
            } finally {
                this.apriltag.savingSelection = false;
            }
        },

        async uploadApriltagField() {
            if (!this.endpoints.upload) {
                this.toast('error', 'Upload endpoint unavailable');
                return;
            }
            const input = this.$refs.apriltagUploadInput;
            const file = input?.files?.[0];
            if (!file) {
                this.toast('error', 'Choose a .json file to upload');
                return;
            }
            const formData = new FormData();
            formData.append('field_layout', file);
            this.apriltag.uploading = true;
            try {
                const response = await fetch(this.endpoints.upload, {
                    method: 'POST',
                    body: formData,
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || 'Failed to upload field layout');
                }
                const name = data.name;
                if (name) {
                    const names = this.apriltag.userFields.includes(name)
                        ? this.apriltag.userFields
                        : [...this.apriltag.userFields, name];
                    this.apriltag.userFields = this.sortFieldNames(names);
                }
                if (input) {
                    input.value = '';
                }
                this.toast('success', `Uploaded ${name}`);
            } catch (error) {
                this.toast('error', error.message || 'Failed to upload field layout');
            } finally {
                this.apriltag.uploading = false;
            }
        },

        async deleteApriltagField(name) {
            if (!name || !this.endpoints.delete) {
                return;
            }
            this.apriltag.deleting = name;
            try {
                const response = await fetch(this.endpoints.delete, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ field_name: name }),
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || 'Failed to delete field layout');
                }
                this.apriltag.userFields = this.apriltag.userFields.filter((entry) => entry !== name);
                if (data.selected === null && this.apriltag.selectedField === name) {
                    this.apriltag.selectedField = '';
                }
                this.toast('success', `Deleted ${name}`);
            } catch (error) {
                this.toast('error', error.message || 'Failed to delete field layout');
            } finally {
                this.apriltag.deleting = null;
            }
        },
        };
    });
}
