export function registerGlobalStores(Alpine) {
    if (!Alpine) {
        return;
    }

    Alpine.store('toasts', {
        list: [],
        push(message, type = 'info') {
            const id = crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random());
            this.list.push({ id, message, type });
            setTimeout(() => this.remove(id), 4000);
        },
        remove(id) {
            this.list = this.list.filter((toast) => toast.id !== id);
        },
        clear() {
            this.list = [];
        },
    });

    Alpine.store('live', {
        online: true,
        latencyMs: null,
        update({ online, latencyMs }) {
            if (typeof online === 'boolean') {
                this.online = online;
            }
            if (typeof latencyMs === 'number' || latencyMs === null) {
                this.latencyMs = latencyMs;
            }
        },
    });

    Alpine.store('loading', {
        active: new Set(),
        start(key) {
            this.active.add(key);
        },
        stop(key) {
            this.active.delete(key);
        },
        has(key) {
            return this.active.has(key);
        },
    });
}
