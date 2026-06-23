let chartInstance = null;
let selectedMachineId = null;
let refreshTimer = null;

document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  await loadMachines();
});

function bindEvents() {
  document.getElementById("machineForm").addEventListener("submit", createMachine);
  document.getElementById("sensorForm").addEventListener("submit", submitSensorReading);
  document.getElementById("loadHistoryBtn").addEventListener("click", loadHistory);
  document.getElementById("machineSelect").addEventListener("change", onMachineChange);
  document.getElementById("refreshNowBtn").addEventListener("click", refreshDashboard);
  document.getElementById("exportHistoryBtn").addEventListener("click", exportHistory);
  document.getElementById("exportAlertsBtn").addEventListener("click", exportAlerts);
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, options);
  const result = await response.json();

  if (!response.ok) {
    throw new Error(result.message || "Request failed");
  }

  return result.data;
}

function setMessage(elementId, message, isError = false) {
  const el = document.getElementById(elementId);
  el.textContent = message;
  el.style.color = isError ? "#b91c1c" : "#6b7280";
}

async function loadMachines() {
  try {
    const machines = await apiFetch("/api/machines");
    const select = document.getElementById("machineSelect");

    select.innerHTML = '<option value="">Choose a machine</option>';

    machines.forEach(machine => {
      const option = document.createElement("option");
      option.value = machine.id;
      option.textContent = `${machine.name} (${machine.machine_type}) - ID ${machine.id}`;
      select.appendChild(option);
    });
  } catch (error) {
    setMessage("machineResult", error.message, true);
  }
}

async function createMachine(event) {
  event.preventDefault();

  try {
    const payload = {
      name: document.getElementById("name").value.trim(),
      machine_type: document.getElementById("machine_type").value.trim(),
      location: document.getElementById("location").value.trim()
    };

    const data = await apiFetch("/api/machines", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    setMessage("machineResult", `Created machine with ID: ${data.machine_id}`);
    document.getElementById("machineForm").reset();

    await loadMachines();

    document.getElementById("machineSelect").value = String(data.machine_id);
    selectedMachineId = data.machine_id;
    startAutoRefresh();
    await refreshDashboard();
    await loadHistory();
  } catch (error) {
    setMessage("machineResult", error.message, true);
  }
}

async function onMachineChange(event) {
  selectedMachineId = event.target.value ? Number(event.target.value) : null;

  if (!selectedMachineId) {
    stopAutoRefresh();
    resetDashboard();
    return;
  }

  startAutoRefresh();
  await refreshDashboard();
  await loadHistory();
}

async function submitSensorReading(event) {
  event.preventDefault();

  if (!selectedMachineId) {
    setMessage("sensorResult", "Please select a machine first.", true);
    return;
  }

  try {
    const payload = {
      temperature: parseFloat(document.getElementById("temperature").value),
      vibration: parseFloat(document.getElementById("vibration").value),
      pressure: parseFloat(document.getElementById("pressure").value),
      rpm: parseFloat(document.getElementById("rpm").value),
      runtime_hours: parseFloat(document.getElementById("runtime_hours").value)
    };

    await apiFetch(`/api/machines/${selectedMachineId}/sensor`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    setMessage("sensorResult", "Sensor reading submitted successfully.");
    document.getElementById("sensorForm").reset();

    await refreshDashboard();
    await loadHistory();
  } catch (error) {
    setMessage("sensorResult", error.message, true);
  }
}

async function refreshDashboard() {
  if (!selectedMachineId) return;

  try {
    const [status, summary, alerts] = await Promise.all([
      apiFetch(`/api/machines/${selectedMachineId}/status`),
      apiFetch(`/api/machines/${selectedMachineId}/summary`),
      apiFetch(`/api/machines/${selectedMachineId}/alerts`)
    ]);

    updateStatusCards(status);
    updateSummaryCards(summary);
    updateAlerts(alerts);
  } catch (error) {
    console.error("Dashboard refresh failed:", error.message);
  }
}

function updateSummaryCards(summary) {
  document.getElementById("kpiReadings").textContent = summary.total_readings ?? "--";
  document.getElementById("kpiAlerts").textContent = summary.total_alerts ?? "--";
  document.getElementById("kpiAvgHealth").textContent = summary.average_health_score ?? "--";
  document.getElementById("kpiHighRisk").textContent = summary.high_risk_count ?? "--";
  document.getElementById("kpiMtbf").textContent = summary.estimated_mtbf ?? "--";
  document.getElementById("kpiMttr").textContent = summary.estimated_mttr ?? "--";
}

function updateStatusCards(status) {
  const healthScore = status.health_score ?? "--";
  const failureRisk = status.failure_risk ?? "--";
  const anomalyStatus = Number(status.anomaly_status) === 1 ? "Anomaly" : "Normal";

  document.getElementById("healthScore").textContent = healthScore;
  document.getElementById("anomalyStatus").textContent = anomalyStatus;
  document.getElementById("failureRisk").textContent = `${failureRisk}%`;
  document.getElementById("recommendedAction").textContent = status.recommended_action ?? "--";

  const badge = document.getElementById("healthBadge");
  badge.className = "badge";

  const label = status.health_label || deriveHealthLabel(healthScore);
  badge.classList.add(label);
  badge.textContent = capitalize(label);
}

function deriveHealthLabel(score) {
  if (score >= 80) return "safe";
  if (score >= 60) return "warning";
  return "critical";
}

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function updateAlerts(alerts) {
  const alertsList = document.getElementById("alertsList");

  if (!alerts.length) {
    alertsList.innerHTML = "<p>No alerts yet.</p>";
    return;
  }

  alertsList.innerHTML = alerts.map(alert => `
    <div class="alert-item ${alert.alert_type}">
      <strong>${alert.alert_type.toUpperCase()}</strong><br>
      ${alert.message}<br>
      <small>${alert.created_at}</small>
    </div>
  `).join("");
}

async function loadHistory() {
  if (!selectedMachineId) return;

  try {
    const readings = await apiFetch(`/api/machines/${selectedMachineId}/history?limit=100`);
    renderChart(readings.slice().reverse());
  } catch (error) {
    console.error("History load failed:", error.message);
  }
}

function exportHistory() {
  if (!selectedMachineId) {
    alert("Select a machine first");
    return;
  }
  window.open(`/api/machines/${selectedMachineId}/history/export`, "_blank");
}

function exportAlerts() {
  if (!selectedMachineId) {
    alert("Select a machine first");
    return;
  }
  window.open(`/api/machines/${selectedMachineId}/alerts/export`, "_blank");
}

function renderChart(readings) {
  const labels = readings.map(item => item.recorded_at);
  const temperatures = readings.map(item => item.temperature);
  const vibrations = readings.map(item => item.vibration);
  const pressures = readings.map(item => item.pressure);

  const ctx = document.getElementById("historyChart").getContext("2d");

  if (chartInstance) {
    chartInstance.destroy();
  }

  chartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Temperature",
          data: temperatures,
          borderColor: "#dc2626",
          backgroundColor: "rgba(220, 38, 38, 0.1)",
          tension: 0.3
        },
        {
          label: "Vibration",
          data: vibrations,
          borderColor: "#2563eb",
          backgroundColor: "rgba(37, 99, 235, 0.1)",
          tension: 0.3
        },
        {
          label: "Pressure",
          data: pressures,
          borderColor: "#16a34a",
          backgroundColor: "rgba(22, 163, 74, 0.1)",
          tension: 0.3
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false
      },
      scales: {
        y: {
          beginAtZero: true
        }
      },
      plugins: {
        legend: {
          position: "top"
        },
        annotation: {
          annotations: {
            tempThreshold: {
              type: "line",
              yMin: 80,
              yMax: 80,
              borderColor: "#dc2626",
              borderWidth: 2,
              borderDash: [6, 6]
            },
            vibrationThreshold: {
              type: "line",
              yMin: 6,
              yMax: 6,
              borderColor: "#2563eb",
              borderWidth: 2,
              borderDash: [6, 6]
            }
          }
        }
      }
    }
  });
}

function startAutoRefresh() {
  stopAutoRefresh();
  refreshTimer = setInterval(refreshDashboard, 5000);
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

function resetDashboard() {
  document.getElementById("kpiReadings").textContent = "--";
  document.getElementById("kpiAlerts").textContent = "--";
  document.getElementById("kpiAvgHealth").textContent = "--";
  document.getElementById("kpiHighRisk").textContent = "--";
  document.getElementById("kpiMtbf").textContent = "--";
  document.getElementById("kpiMttr").textContent = "--";
  document.getElementById("healthScore").textContent = "--";
  document.getElementById("anomalyStatus").textContent = "--";
  document.getElementById("failureRisk").textContent = "--";
  document.getElementById("recommendedAction").textContent = "--";
  document.getElementById("healthBadge").className = "badge neutral";
  document.getElementById("healthBadge").textContent = "--";
  document.getElementById("alertsList").innerHTML = "<p>No alerts yet.</p>";

  if (chartInstance) {
    chartInstance.destroy();
    chartInstance = null;
  }
}