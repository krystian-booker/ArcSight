const DEFAULT_HEADERS = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
};

async function parseJsonResponse(response) {
    const text = await response.text();
    if (!text) {
        return null;
    }
    try {
        return JSON.parse(text);
    } catch (error) {
        console.error('Failed to parse JSON response:', error);
        return null;
    }
}

export async function fetchJson(url, options = {}) {
    const opts = { ...options };
    opts.headers = { ...DEFAULT_HEADERS, ...(options.headers || {}) };

    const response = await fetch(url, opts);
    if (!response.ok) {
        const payload = await parseJsonResponse(response);
        const error = new Error(payload?.error || `Request failed (${response.status})`);
        error.status = response.status;
        error.payload = payload;
        throw error;
    }
    return parseJsonResponse(response);
}

export async function postJson(url, body = {}, options = {}) {
    return fetchJson(
        url,
        Object.assign(
            {
                method: 'POST',
                body: JSON.stringify(body),
            },
            options,
        ),
    );
}

export function debounce(fn, wait = 200) {
    let timer = null;
    const debounced = function (...args) {
        if (timer) {
            clearTimeout(timer);
        }
        timer = setTimeout(() => {
            timer = null;
            fn.apply(this, args);
        }, wait);
    };
    debounced.cancel = () => {
        if (timer) {
            clearTimeout(timer);
            timer = null;
        }
    };
    return debounced;
}

export function throttle(fn, limit = 200) {
    let inThrottle = false;
    let lastArgs = null;
    const throttled = function (...args) {
        if (!inThrottle) {
            fn.apply(this, args);
            inThrottle = true;
            setTimeout(() => {
                inThrottle = false;
                if (lastArgs) {
                    fn.apply(this, lastArgs);
                    lastArgs = null;
                }
            }, limit);
        } else {
            lastArgs = args;
        }
    };
    return throttled;
}

export function safeJsonParse(value, fallback = null) {
    try {
        return JSON.parse(value);
    } catch (error) {
        return fallback;
    }
}

export function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
}

export function formatDateTime(value) {
    if (!value) return '';
    try {
        return new Intl.DateTimeFormat(undefined, {
            dateStyle: 'medium',
            timeStyle: 'short',
        }).format(new Date(value));
    } catch (error) {
        return value;
    }
}

// Expose helpers to window for convenience in templates when needed.
window.$helpers = {
    fetchJson,
    postJson,
    debounce,
    throttle,
    safeJsonParse,
    downloadBlob,
    formatDateTime,
};
