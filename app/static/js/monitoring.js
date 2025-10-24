(() => {
    const root = document.getElementById("monitoring-app");
    if (!root) {
        return;
    }

    const enabled = root.dataset.enabled === "true";
    if (!enabled) {
        return;
    }

    const refreshInterval = Number(root.dataset.refresh || "2000");
    const tableBody = root.querySelector("[data-table-body]");

    const fields = {
        cpuPercent: root.querySelector('[data-field="cpu-percent"]'),
        ramPercent: root.querySelector('[data-field="ram-percent"]'),
        ramUsed: root.querySelector('[data-field="ram-used"]'),
        cpuTemp: root.querySelector('[data-field="cpu-temp"]'),
        memoryRss: root.querySelector('[data-field="memory-rss"]'),
        pipelineCount: root.querySelector('[data-field="pipeline-count"]'),
        dropsPerMinute: root.querySelector('[data-field="drops-per-minute"]'),
        latencyThreshold: root.querySelector('[data-field="latency-threshold"]'),
        queueThreshold: root.querySelector('[data-field="queue-threshold"]'),
        windowSize: root.querySelector('[data-field="window-size"]'),
        generatedAt: root.querySelector('[data-field="generated-at"]'),
    };

    function formatBytes(bytes) {
        if (!bytes || bytes <= 0) {
            return "0 MB";
        }
        const mb = bytes / (1024 * 1024);
        return `${mb.toFixed(1)} MB`;
    }

    function formatMs(value) {
        if (value === undefined || value === null || Number.isNaN(value)) {
            return "—";
        }
        return `${value.toFixed(1)} ms`;
    }

    function formatPercent(value) {
        if (value === undefined || value === null || Number.isNaN(value)) {
            return "—";
        }
        return `${value.toFixed(1)}%`;
    }

    function formatTemperature(value) {
        if (value === undefined || value === null || Number.isNaN(value)) {
            return "—";
        }
        return `${value.toFixed(1)}°C`;
    }

    function renderSystemMetrics(systemData) {
        if (fields.cpuPercent) {
            fields.cpuPercent.textContent = formatPercent(systemData?.cpu_percent ?? 0);
        }
        if (fields.ramPercent) {
            fields.ramPercent.textContent = formatPercent(systemData?.ram_percent ?? 0);
        }
        if (fields.ramUsed) {
            const totalBytes = systemData?.ram_total_bytes ?? 0;
            const usedBytes = systemData?.ram_used_bytes ?? 0;
            fields.ramUsed.textContent = `${formatBytes(usedBytes)} / ${formatBytes(totalBytes)}`;
        }
        if (fields.cpuTemp) {
            const temps = systemData?.temperatures ?? [];
            if (temps.length > 0) {
                // Find CPU-related temperature sensor
                const cpuTemp = temps.find(t =>
                    t.sensor && (
                        t.sensor.toLowerCase().includes('cpu') ||
                        t.sensor.toLowerCase().includes('core') ||
                        t.sensor.toLowerCase().includes('package')
                    )
                );
                if (cpuTemp) {
                    fields.cpuTemp.textContent = formatTemperature(cpuTemp.temperature_c);
                } else {
                    // Use first available temperature
                    fields.cpuTemp.textContent = formatTemperature(temps[0].temperature_c);
                }
            } else {
                fields.cpuTemp.textContent = "N/A";
            }
        }
    }

    function renderSummary(snapshot) {
        const pipelines = snapshot?.pipelines ?? [];
        const config = snapshot?.config ?? {};

        if (fields.memoryRss) {
            fields.memoryRss.textContent = formatBytes(snapshot?.memory?.rss_bytes ?? 0);
        }
        if (fields.pipelineCount) {
            fields.pipelineCount.textContent = String(pipelines.length);
        }
        if (fields.dropsPerMinute) {
            const dropsPerMinute = pipelines.reduce((acc, pipeline) => {
                const perMinute = pipeline?.drops?.per_minute ?? 0;
                return acc + perMinute;
            }, 0);
            fields.dropsPerMinute.textContent = dropsPerMinute.toFixed(2);
        }
        if (fields.latencyThreshold && config.latency_warn_ms !== undefined) {
            fields.latencyThreshold.textContent = `${config.latency_warn_ms.toFixed(1)} ms`;
        }
        if (fields.queueThreshold && config.queue_high_utilization_pct !== undefined) {
            fields.queueThreshold.textContent = `${config.queue_high_utilization_pct.toFixed(0)}%`;
        }
        if (fields.windowSize && config.window_seconds !== undefined) {
            fields.windowSize.textContent = `${config.window_seconds.toFixed(0)} s`;
        }
        if (fields.generatedAt) {
            const generated = snapshot?.generated_at ? new Date(snapshot.generated_at * 1000) : null;
            fields.generatedAt.textContent = generated
                ? generated.toLocaleTimeString()
                : "—";
        }
    }

    function buildStatusBadges(pipeline, config) {
        const badges = [];
        const latencyP95 = pipeline?.latency_ms?.total?.p95_ms ?? 0;
        const queueUtil = pipeline?.queue?.utilization_pct ?? 0;
        const drops = pipeline?.drops?.window_total ?? 0;
        const queueHighWater = pipeline?.queue?.high_watermark_pct ?? 0;

        if (latencyP95 > (config?.latency_warn_ms ?? 0)) {
            badges.push({ label: "Slow frames", tone: "warn" });
        }
        if (queueUtil >= (config?.queue_high_utilization_pct ?? 80)) {
            badges.push({ label: "Queue saturated", tone: "warn" });
        } else if (queueHighWater >= (config?.queue_high_utilization_pct ?? 80)) {
            badges.push({ label: "Queue spike", tone: "warn" });
        }
        if (drops > 0) {
            badges.push({ label: "Drops observed", tone: "error" });
        }
        if (!badges.length) {
            badges.push({ label: "Nominal", tone: "ok" });
        }
        return badges;
    }

    function renderTable(pipelines, config) {
        if (!tableBody) {
            return;
        }
        tableBody.innerHTML = "";

        if (!pipelines.length) {
            const emptyRow = document.createElement("tr");
            const emptyCell = document.createElement("td");
            emptyCell.colSpan = 6;
            emptyCell.className = "muted text-center";
            emptyCell.textContent = "No active pipelines.";
            emptyRow.appendChild(emptyCell);
            tableBody.appendChild(emptyRow);
            return;
        }

        const fragment = document.createDocumentFragment();

        pipelines.forEach((pipeline) => {
            const row = document.createElement("tr");

            const pipelineCell = document.createElement("td");
            const pipelineStack = document.createElement("div");
            pipelineStack.className = "stack stack-xs";
            const title = document.createElement("span");
            const pipelineLabel = `${pipeline.camera_identifier || "Camera"} · ${pipeline.pipeline_type || "Pipeline"} #${pipeline.pipeline_id}`;
            title.textContent = pipelineLabel;
            const subtitle = document.createElement("span");
            subtitle.className = "muted text-small";
            subtitle.textContent = `Queue ${pipeline.queue?.current_depth ?? 0}/${pipeline.queue?.max_size || "∞"}`;
            pipelineStack.appendChild(title);
            pipelineStack.appendChild(subtitle);
            pipelineCell.appendChild(pipelineStack);
            row.appendChild(pipelineCell);

            const fpsCell = document.createElement("td");
            fpsCell.textContent = pipeline.fps ? pipeline.fps.toFixed(1) : "0.0";
            row.appendChild(fpsCell);

            const latencyCell = document.createElement("td");
            const totalLatency = pipeline.latency_ms?.total ?? {};
            latencyCell.textContent = [
                formatMs(totalLatency.avg_ms ?? 0),
                formatMs(totalLatency.p95_ms ?? 0),
                formatMs(totalLatency.max_ms ?? 0),
            ].join(" / ");
            row.appendChild(latencyCell);

            const queueCell = document.createElement("td");
            const queue = pipeline.queue ?? {};
            const queueParts = [
                `${queue.current_depth ?? 0}/${queue.max_size || "∞"}`,
                formatPercent(queue.utilization_pct ?? 0),
            ];
            queueCell.textContent = queueParts.join(" · ");
            row.appendChild(queueCell);

            const dropsCell = document.createElement("td");
            const drops = pipeline.drops ?? {};
            dropsCell.textContent = `${(drops.window_total ?? 0).toFixed(0)} (${(drops.per_minute ?? 0).toFixed(2)}/min)`;
            row.appendChild(dropsCell);

            const statusCell = document.createElement("td");
            const badgeContainer = document.createElement("div");
            badgeContainer.className = "cluster cluster-wrap";
            buildStatusBadges(pipeline, config).forEach((badge) => {
                const span = document.createElement("span");
                span.className = `badge badge--${badge.tone}`;
                span.textContent = badge.label;
                badgeContainer.appendChild(span);
            });
            statusCell.appendChild(badgeContainer);
            row.appendChild(statusCell);

            fragment.appendChild(row);
        });

        tableBody.appendChild(fragment);
    }

    async function fetchAndRender() {
        try {
            // Fetch both pipeline metrics and system metrics in parallel
            const [metricsResponse, systemResponse] = await Promise.all([
                fetch("/api/metrics/summary", { cache: "no-cache" }),
                fetch("/api/metrics/system", { cache: "no-cache" }),
            ]);

            if (!metricsResponse.ok) {
                throw new Error(`Failed to fetch metrics: ${metricsResponse.status}`);
            }
            if (!systemResponse.ok) {
                throw new Error(`Failed to fetch system metrics: ${systemResponse.status}`);
            }

            const snapshot = await metricsResponse.json();
            const systemData = await systemResponse.json();

            renderSystemMetrics(systemData);
            renderSummary(snapshot);
            renderTable(snapshot?.pipelines ?? [], snapshot?.config ?? {});
        } catch (error) {
            console.error(error);
        }
    }

    fetchAndRender();
    setInterval(fetchAndRender, Math.max(refreshInterval, 1000));
})();
