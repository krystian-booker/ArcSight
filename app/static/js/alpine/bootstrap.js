import { registerGlobalStores } from './stores.js';
import './helpers.js';
import { registerLayoutComponents } from './components/layout.js';
import { registerDashboardComponents } from './components/dashboard.js';
import { registerCamerasComponents } from './components/cameras.js';
import { registerCalibrationComponents } from './components/calibration.js';
import { registerSettingsComponents } from './components/settings.js';

let registered = false;

function registerAll(Alpine) {
    if (!Alpine || registered) {
        return;
    }
    registerGlobalStores(Alpine);
    registerLayoutComponents(Alpine);
    registerDashboardComponents(Alpine);
    registerCamerasComponents(Alpine);
    registerCalibrationComponents(Alpine);
    registerSettingsComponents(Alpine);
    registered = true;
}

document.addEventListener('alpine:init', () => {
    registerAll(window.Alpine);
});

if (window.Alpine) {
    registerAll(window.Alpine);
}
