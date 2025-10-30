// Chart instances
let charts = {};

// Color schemes
const colors = {
    primary: '#6366f1',
    secondary: '#8b5cf6',
    success: '#10b981',
    warning: '#f59e0b',
    danger: '#ef4444',
    info: '#3b82f6',
    purple: '#a855f7',
    pink: '#ec4899',
    indigo: '#6366f1',
    teal: '#14b8a6'
};

const chartColors = [
    colors.primary,
    colors.secondary,
    colors.success,
    colors.warning,
    colors.danger,
    colors.info,
    colors.purple,
    colors.pink,
    colors.indigo,
    colors.teal
];

// Initialize dashboard
document.addEventListener('DOMContentLoaded', () => {
    checkAuthentication();
    initializeDateInputs();
    refreshData();
});

// Check if user is authenticated
async function checkAuthentication() {
    try {
        const response = await fetch('/api/auth/check');
        const data = await response.json();

        if (!data.authenticated) {
            window.location.href = '/login.html';
        }
    } catch (error) {
        console.error('Auth check failed:', error);
        window.location.href = '/login.html';
    }
}

// Logout function
async function logout() {
    try {
        await fetch('/api/logout', { method: 'POST' });
        window.location.href = '/login.html';
    } catch (error) {
        console.error('Logout failed:', error);
        window.location.href = '/login.html';
    }
}

function initializeDateInputs() {
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - 7); // Default to last 7 days

    document.getElementById('endDate').valueAsDate = endDate;
    document.getElementById('startDate').valueAsDate = startDate;
}

function applyDateFilter() {
    refreshData();
}

async function fetchData() {
    const loading = document.getElementById('loadingState');
    const error = document.getElementById('errorState');
    const content = document.getElementById('dashboardContent');

    loading.style.display = 'block';
    error.classList.add('hidden');
    content.style.display = 'none';

    try {
        const startDate = document.getElementById('startDate').value;
        const endDate = document.getElementById('endDate').value;

        let url = '/api/costs';
        if (startDate && endDate) {
            url += `?start_date=${startDate}&end_date=${endDate}`;
        }

        const response = await fetch(url);
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText || 'Failed to fetch data'}`);
        }

        const data = await response.json();

        loading.style.display = 'none';
        content.style.display = 'block';

        updateSummaryCards(data);
        updateCharts(data);
        updateTable(data);
    } catch (err) {
        console.error('Error fetching data:', err);
        loading.style.display = 'none';
        error.classList.remove('hidden');
        document.getElementById('errorMessage').textContent = err.message || 'Failed to load data';
    }
}

// Alias for compatibility
async function refreshData() {
    await fetchData();
}

function updateSummaryCards(data) {
    // Total cost
    document.getElementById('totalCost').textContent = `$${data.summary.total_cost.toFixed(4)}`;

    // Total calls
    document.getElementById('totalCalls').textContent = data.summary.total_calls.toLocaleString();

    // Average cost
    const avgCost = data.summary.total_calls > 0
        ? data.summary.total_cost / data.summary.total_calls
        : 0;
    document.getElementById('avgCost').textContent = `$${avgCost.toFixed(4)}`;

    // Cache hit rate
    const totalTokens = data.summary.total_input_tokens || 0;
    const cachedTokens = data.summary.total_cached_tokens || 0;
    const cacheRate = totalTokens > 0 ? (cachedTokens / totalTokens) * 100 : 0;

    document.getElementById('cacheRate').textContent = `${cacheRate.toFixed(1)}%`;
}

function updateCharts(data) {
    createCallTypeChart(data);
    createWorkflowChart(data);
    createTimelineChart(data);
    createTokenChart(data);
    updateSalespersonBreakdown(data);
    // Removed createModelChart - canvas doesn't exist in new design
}

function createCallTypeChart(data) {
    const ctx = document.getElementById('callTypeChart');
    const byCallType = data.summary.by_call_type || {};

    const labels = Object.keys(byCallType).map(k => k.replace('_', ' '));
    const costs = Object.values(byCallType).map(v => v.cost);

    destroyChart('callTypeChart');
    charts.callTypeChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data: costs,
                backgroundColor: chartColors,
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#f1f5f9', padding: 15 }
                },
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            return `${label}: $${value.toFixed(4)}`;
                        }
                    }
                }
            }
        }
    });
}

function createWorkflowChart(data) {
    const ctx = document.getElementById('workflowChart');
    const byWorkflow = data.summary.by_workflow || {};

    const labels = Object.keys(byWorkflow).map(k => k ? k.replace('_', ' ') : 'unclassified');
    const costs = Object.values(byWorkflow).map(v => v.cost);

    destroyChart('workflowChart');
    charts.workflowChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data: costs,
                backgroundColor: chartColors,
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#f1f5f9', padding: 15 }
                },
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            return `${label}: $${value.toFixed(4)}`;
                        }
                    }
                }
            }
        }
    });
}

function createTimelineChart(data) {
    const ctx = document.getElementById('timelineChart');
    const dailyCosts = data.summary.daily_costs || [];

    const dates = dailyCosts.map(d => d.date);
    const costs = dailyCosts.map(d => d.cost);

    destroyChart('timelineChart');
    charts.timelineChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [{
                label: 'Daily Cost',
                data: costs,
                borderColor: colors.primary,
                backgroundColor: `${colors.primary}33`,
                fill: true,
                tension: 0.4,
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => `Cost: $${context.parsed.y.toFixed(4)}`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { color: '#94a3b8' },
                    grid: { color: '#334155' }
                },
                x: {
                    ticks: { color: '#94a3b8' },
                    grid: { display: false }
                }
            }
        }
    });
}

function createTokenChart(data) {
    const ctx = document.getElementById('tokenChart');

    const totalInput = data.summary.total_input_tokens || 0;
    const totalCached = data.summary.total_cached_tokens || 0;
    const totalOutput = data.summary.total_output_tokens || 0;
    const totalReasoning = data.summary.total_reasoning_tokens || 0;

    destroyChart('tokenChart');
    charts.tokenChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Input', 'Cached', 'Output', 'Reasoning'],
            datasets: [{
                data: [totalInput, totalCached, totalOutput, totalReasoning],
                backgroundColor: [colors.primary, colors.success, colors.warning, colors.secondary],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => `${context.parsed.y.toLocaleString()} tokens`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { color: '#94a3b8' },
                    grid: { color: '#334155' }
                },
                x: {
                    ticks: { color: '#94a3b8' },
                    grid: { display: false }
                }
            }
        }
    });
}

function createModelChart(data) {
    const ctx = document.getElementById('modelChart');
    const calls = data.calls || [];

    // Group by model
    const modelCosts = {};
    calls.forEach(call => {
        const model = call.model || 'unknown';
        modelCosts[model] = (modelCosts[model] || 0) + call.total_cost;
    });

    const labels = Object.keys(modelCosts);
    const costs = Object.values(modelCosts);

    destroyChart('modelChart');
    charts.modelChart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels,
            datasets: [{
                data: costs,
                backgroundColor: chartColors,
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#f1f5f9', padding: 15 }
                },
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            return `${label}: $${value.toFixed(4)}`;
                        }
                    }
                }
            }
        }
    });
}

function updateTable(data) {
    const tbody = document.getElementById('recentCallsTable');
    tbody.innerHTML = '';

    const calls = data.calls || [];
    const recentCalls = calls.slice(-50).reverse(); // Last 50 calls

    recentCalls.forEach(call => {
        const row = document.createElement('tr');
        row.className = 'border-b border-gray-700 hover:bg-white hover:bg-opacity-5 transition-colors';

        const timestamp = new Date(call.timestamp).toLocaleString();
        const callType = call.call_type.replace(/_/g, ' ');
        const workflow = call.workflow ? call.workflow.replace(/_/g, ' ') : '-';
        const model = call.model || '-';
        const tokens = `${call.input_tokens} + ${call.output_tokens}${call.cached_input_tokens > 0 ? ` (${call.cached_input_tokens} 🗲)` : ''}`;
        const cost = `$${call.total_cost.toFixed(4)}`;

        row.innerHTML = `
            <td class="py-3 px-4 text-sm">${timestamp}</td>
            <td class="py-3 px-4"><span class="px-2 py-1 bg-indigo-500 bg-opacity-20 text-indigo-300 rounded text-xs">${callType}</span></td>
            <td class="py-3 px-4"><span class="px-2 py-1 bg-purple-500 bg-opacity-20 text-purple-300 rounded text-xs">${workflow}</span></td>
            <td class="py-3 px-4 text-sm text-gray-300">${model}</td>
            <td class="py-3 px-4 text-sm text-right text-gray-300">${tokens}</td>
            <td class="py-3 px-4 text-sm text-right font-semibold text-green-400">${cost}</td>
        `;

        tbody.appendChild(row);
    });
}

function destroyChart(chartId) {
    if (charts[chartId]) {
        charts[chartId].destroy();
    }
}

function updateSalespersonBreakdown(data) {
    const container = document.getElementById('salespersonList');
    const byUser = data.summary.by_user || {};

    container.innerHTML = '';

    if (Object.keys(byUser).length === 0) {
        container.innerHTML = '<p class="text-gray-400 text-center col-span-full">No user data available</p>';
        return;
    }

    Object.entries(byUser).forEach(([userId, stats]) => {
        const card = document.createElement('div');
        card.className = 'stat-card p-6 rounded-xl';

        card.innerHTML = `
            <div class="flex items-center justify-between mb-4">
                <div class="w-10 h-10 bg-purple-500 bg-opacity-20 rounded-lg flex items-center justify-center">
                    <i class="fas fa-user text-purple-400"></i>
                </div>
                <span class="text-2xl font-bold text-green-400">$${stats.cost.toFixed(4)}</span>
            </div>
            <p class="text-gray-300 font-semibold mb-2">${userId}</p>
            <div class="flex justify-between text-sm text-gray-400">
                <span>${stats.calls} calls</span>
                <span>${stats.tokens.toLocaleString()} tokens</span>
            </div>
        `;

        container.appendChild(card);
    });
}
