export function registerSettingsComponents(Alpine) {
    if (!Alpine) {
        return;
    }

    Alpine.data('settingsApp', () => ({
        factoryResetOpen: false,

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
    }));
}
