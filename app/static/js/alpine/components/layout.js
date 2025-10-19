const HANDHELD_QUERY = '(max-width: 1080px)';
const FOCUSABLE_SELECTOR =
    'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function isVisible(element) {
    if (!element) {
        return false;
    }
    return element.offsetWidth > 0 || element.offsetHeight > 0 || element.getClientRects().length > 0;
}

function getFocusableElements(root) {
    if (!root) {
        return [];
    }
    return Array.from(root.querySelectorAll(FOCUSABLE_SELECTOR)).filter(
        (el) => !el.hasAttribute('disabled') && el.getAttribute('aria-hidden') !== 'true' && isVisible(el),
    );
}

export function registerLayoutComponents(Alpine) {
    if (!Alpine) {
        return;
    }

    Alpine.data('layoutShell', () => ({
        sidebarOpen: false,
        isHandheld: false,
        focusReturnEl: null,
        mediaQuery: null,
        focusTrapHandler: null,
        focusContainHandler: null,
        scrollState: {
            locked: false,
            top: 0,
        },

        registerCleanup(callback) {
            if (typeof callback !== 'function') {
                return;
            }
            if (typeof this.$cleanup === 'function') {
                this.$cleanup(callback);
                return;
            }
            const target = this.$el;
            if (!target || typeof target.addEventListener !== 'function') {
                return;
            }
            const handler = () => {
                callback();
                target.removeEventListener('alpine:destroy', handler);
            };
            target.addEventListener('alpine:destroy', handler);
        },

        init() {
            this.isHandheld = window.matchMedia(HANDHELD_QUERY).matches;
            this.setupMediaWatcher();
            this.$watch('sidebarOpen', (open) => {
                if (open && this.isHandheld) {
                    this.rememberFocus();
                    this.lockScroll();
                    this.enableFocusTrap();
                    this.$nextTick(() => {
                        this.focusFirstItem();
                    });
                    return;
                }
                this.disableFocusTrap();
                this.unlockScroll();
                this.restoreFocus();
            });
        },

        setupMediaWatcher() {
            const mql = window.matchMedia(HANDHELD_QUERY);
            const handler = (event) => {
                this.isHandheld = event.matches;
                if (!event.matches) {
                    this.sidebarOpen = false;
                }
            };
            if (typeof mql.addEventListener === 'function') {
                mql.addEventListener('change', handler);
            } else {
                mql.addListener(handler);
            }
            this.mediaQuery = { mql, handler };
            this.registerCleanup(() => {
                if (this.mediaQuery) {
                    const { mql: query, handler: listener } = this.mediaQuery;
                    if (typeof query.removeEventListener === 'function') {
                        query.removeEventListener('change', listener);
                    } else {
                        query.removeListener(listener);
                    }
                }
                this.disableFocusTrap();
                this.unlockScroll(true);
            });
        },

        toggleSidebar() {
            if (!this.isHandheld) {
                return;
            }
            this.sidebarOpen = !this.sidebarOpen;
        },

        closeSidebar() {
            if (!this.sidebarOpen) {
                return;
            }
            this.sidebarOpen = false;
        },

        handleNavClick(event) {
            if (!this.isHandheld) {
                return;
            }
            const link = event.target.closest('a');
            if (link) {
                this.sidebarOpen = false;
            }
        },

        rememberFocus() {
            const active = document.activeElement;
            if (active && active !== document.body && typeof active.focus === 'function') {
                this.focusReturnEl = active;
                return;
            }
            this.focusReturnEl = this.$refs.sidebarToggle || null;
        },

        restoreFocus() {
            const target = this.focusReturnEl || this.$refs.sidebarToggle;
            this.focusReturnEl = null;
            if (target && typeof target.focus === 'function') {
                requestAnimationFrame(() => {
                    target.focus({ preventScroll: true });
                });
            }
        },

        focusFirstItem() {
            const focusable = getFocusableElements(this.$refs.sidebar);
            if (focusable.length > 0) {
                focusable[0].focus({ preventScroll: true });
                return;
            }
            this.$refs.sidebar?.focus({ preventScroll: true });
        },

        enableFocusTrap() {
            if (this.focusTrapHandler) {
                return;
            }
            this.focusTrapHandler = (event) => {
                if (!this.sidebarOpen || !this.isHandheld || event.key !== 'Tab') {
                    return;
                }
                const focusable = getFocusableElements(this.$refs.sidebar);
                if (focusable.length === 0) {
                    event.preventDefault();
                    this.$refs.sidebar?.focus({ preventScroll: true });
                    return;
                }
                const first = focusable[0];
                const last = focusable[focusable.length - 1];
                const active = document.activeElement;
                if (event.shiftKey) {
                    if (active === first || !this.$refs.sidebar.contains(active)) {
                        event.preventDefault();
                        last.focus({ preventScroll: true });
                    }
                    return;
                }
                if (active === last) {
                    event.preventDefault();
                    first.focus({ preventScroll: true });
                }
            };
            this.focusContainHandler = (event) => {
                if (!this.sidebarOpen || !this.isHandheld) {
                    return;
                }
                if (!this.$refs.sidebar.contains(event.target)) {
                    this.$nextTick(() => {
                        this.focusFirstItem();
                    });
                }
            };
            document.addEventListener('keydown', this.focusTrapHandler, true);
            document.addEventListener('focusin', this.focusContainHandler, true);
        },

        disableFocusTrap() {
            if (this.focusTrapHandler) {
                document.removeEventListener('keydown', this.focusTrapHandler, true);
                this.focusTrapHandler = null;
            }
            if (this.focusContainHandler) {
                document.removeEventListener('focusin', this.focusContainHandler, true);
                this.focusContainHandler = null;
            }
        },

        lockScroll() {
            if (this.scrollState.locked) {
                return;
            }
            this.scrollState.top = window.scrollY || document.documentElement.scrollTop || 0;
            this.$root.style.position = 'fixed';
            this.$root.style.top = `-${this.scrollState.top}px`;
            this.$root.style.width = '100%';
            this.scrollState.locked = true;
        },

        unlockScroll(force = false) {
            if (!this.scrollState.locked && !force) {
                return;
            }
            this.$root.style.position = '';
            this.$root.style.top = '';
            this.$root.style.width = '';
            if (this.scrollState.locked) {
                window.scrollTo(0, this.scrollState.top || 0);
            }
            this.scrollState.locked = false;
            this.scrollState.top = 0;
        },
    }));
}
