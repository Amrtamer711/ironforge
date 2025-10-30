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

// Date picker state
let datePickerMode = 'month';
let selectedYear = new Date().getFullYear();
let selectedMonth = new Date().getMonth();
let rangeStart = null;
let rangeEnd = null;
let rangePicking = 'start';

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
    // Set default to current month
    const now = new Date();
    selectedYear = now.getFullYear();
    selectedMonth = now.getMonth();
    updateDateRangeDisplay();
}

async function fetchData() {
    const loading = document.getElementById('loadingState');
    const error = document.getElementById('errorState');
    const content = document.getElementById('dashboardContent');

    loading.style.display = 'block';
    error.classList.add('hidden');
    content.style.display = 'none';

    try {
        // Calculate date range based on picker mode
        let startDate, endDate;

        if (datePickerMode === 'month') {
            startDate = new Date(selectedYear, selectedMonth, 1);
            endDate = new Date(selectedYear, selectedMonth + 1, 0);
        } else if (datePickerMode === 'year') {
            startDate = new Date(selectedYear, 0, 1);
            endDate = new Date(selectedYear, 11, 31);
        } else if (datePickerMode === 'range' && rangeStart && rangeEnd) {
            startDate = rangeStart;
            endDate = rangeEnd;
        } else {
            // Default to last 7 days
            endDate = new Date();
            startDate = new Date();
            startDate.setDate(startDate.getDate() - 7);
        }

        const startDateStr = startDate ? startDate.toISOString().split('T')[0] : null;
        const endDateStr = endDate ? endDate.toISOString().split('T')[0] : null;

        let url = '/api/costs';
        if (startDateStr && endDateStr) {
            url += `?start_date=${startDateStr}&end_date=${endDateStr}`;
        }

        const response = await fetch(url);
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText || 'Failed to fetch data'}`);
        }

        const data = await response.json();

        // Log the entire response for debugging
        console.log('=== API RESPONSE DATA ===');
        console.log('Full Response:', JSON.stringify(data, null, 2));
        console.log('Summary:', data.summary);
        console.log('Total Calls:', data.summary?.total_calls);
        console.log('Total Cost:', data.summary?.total_cost);
        console.log('Total Cached Tokens:', data.summary?.total_cached_tokens);
        console.log('By Call Type:', data.summary?.by_call_type);
        console.log('By Workflow:', data.summary?.by_workflow);
        console.log('By User:', data.summary?.by_user);
        console.log('Daily Costs:', data.summary?.daily_costs);
        console.log('Calls Array Length:', data.summary?.calls?.length || 0);
        console.log('========================');

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
    const uncachedInput = totalInput - totalCached;
    const totalOutput = data.summary.total_output_tokens || 0;
    const totalReasoning = data.summary.total_reasoning_tokens || 0;

    destroyChart('tokenChart');
    charts.tokenChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Input Tokens', 'Output Tokens', 'Reasoning Tokens'],
            datasets: [
                {
                    label: 'Uncached Input',
                    data: [uncachedInput, 0, 0],
                    backgroundColor: colors.primary,
                    borderWidth: 0
                },
                {
                    label: 'Cached Input',
                    data: [totalCached, 0, 0],
                    backgroundColor: colors.success,
                    borderWidth: 0
                },
                {
                    label: 'Output',
                    data: [0, totalOutput, 0],
                    backgroundColor: colors.warning,
                    borderWidth: 0
                },
                {
                    label: 'Reasoning',
                    data: [0, 0, totalReasoning],
                    backgroundColor: colors.secondary,
                    borderWidth: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'bottom',
                    labels: { color: '#f1f5f9', padding: 15 }
                },
                tooltip: {
                    callbacks: {
                        label: (context) => `${context.dataset.label}: ${context.parsed.y.toLocaleString()} tokens`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    stacked: true,
                    ticks: { color: '#94a3b8' },
                    grid: { color: '#334155' }
                },
                x: {
                    stacked: true,
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

    const calls = data.summary.calls || [];
    // Backend already returns sorted by timestamp DESC (newest first), limit to 50 for display
    const recentCalls = calls.slice(0, 50);

    if (recentCalls.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center py-8 text-gray-400">No API calls recorded yet</td></tr>';
        return;
    }

    recentCalls.forEach(call => {
        const row = document.createElement('tr');
        row.className = 'border-b border-gray-700 hover:bg-white hover:bg-opacity-5 transition-colors';

        const timestamp = new Date(call.timestamp).toLocaleString();
        const userName = call.user_id || '-';
        const callType = call.call_type.replace(/_/g, ' ');
        const workflow = call.workflow ? call.workflow.replace(/_/g, ' ') : '-';
        const model = call.model || '-';
        const tokens = `${call.input_tokens} + ${call.output_tokens}${call.cached_input_tokens > 0 ? ` (${call.cached_input_tokens} ⚡)` : ''}`;
        const cost = `$${call.total_cost.toFixed(4)}`;

        row.innerHTML = `
            <td class="py-3 px-4 text-sm">${timestamp}</td>
            <td class="py-3 px-4 text-sm text-gray-300">${userName}</td>
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

// ========== DATE RANGE PICKER FUNCTIONS ==========

function openDateRangeModal() {
    const modal = document.getElementById('dateRangeModal');
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    renderCalendar();
}

function closeDateRangeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('dateRangeModal');
    modal.classList.add('hidden');
    document.body.style.overflow = '';
}

function switchDateMode(mode) {
    datePickerMode = mode;

    // Update button styles
    document.querySelectorAll('.date-mode-btn').forEach(btn => {
        btn.classList.remove('bg-indigo-500', 'text-white');
        btn.classList.add('bg-gray-700', 'text-gray-300');
    });

    const activeBtn = document.getElementById(mode + 'ModeBtn');
    activeBtn.classList.remove('bg-gray-700', 'text-gray-300');
    activeBtn.classList.add('bg-indigo-500', 'text-white');

    // Reset range selection when switching modes
    if (mode === 'range') {
        rangeStart = null;
        rangeEnd = null;
        rangePicking = 'start';
    }

    renderCalendar();
}

function renderCalendar() {
    const content = document.getElementById('calendarContent');

    if (datePickerMode === 'month') {
        content.innerHTML = renderMonthPicker();
    } else if (datePickerMode === 'year') {
        content.innerHTML = renderYearPicker();
    } else if (datePickerMode === 'range') {
        content.innerHTML = renderRangePicker();
    }
}

function renderMonthPicker() {
    const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    const html = [];

    html.push('<div class="mb-6"><div class="flex items-center justify-between mb-4">');
    html.push('<button onclick="changeYear(-1)" class="p-2 hover:bg-gray-700 rounded-lg transition-all"><i class="fas fa-chevron-left"></i></button>');
    html.push(`<h4 class="text-xl font-bold">${selectedYear}</h4>`);
    html.push('<button onclick="changeYear(1)" class="p-2 hover:bg-gray-700 rounded-lg transition-all"><i class="fas fa-chevron-right"></i></button>');
    html.push('</div><div class="grid grid-cols-3 gap-4">');

    months.forEach((month, index) => {
        const isSelected = index === selectedMonth && selectedYear === new Date().getFullYear();
        const btnClass = isSelected ? 'bg-indigo-500 text-white' : 'bg-white bg-opacity-5 hover:bg-opacity-10 text-gray-300';
        html.push(`<button onclick="selectMonth(${index})" class="${btnClass} px-4 py-3 rounded-lg font-semibold transition-all">${month}</button>`);
    });

    html.push('</div></div>');
    return html.join('');
}

function renderYearPicker() {
    const currentYear = new Date().getFullYear();
    const html = ['<div class="grid grid-cols-3 gap-4">'];

    for (let year = currentYear - 5; year <= currentYear + 5; year++) {
        const isSelected = year === selectedYear;
        const btnClass = isSelected ? 'bg-indigo-500 text-white' : 'bg-white bg-opacity-5 hover:bg-opacity-10 text-gray-300';
        html.push(`<button onclick="selectYear(${year})" class="${btnClass} px-4 py-3 rounded-lg font-semibold transition-all">${year}</button>`);
    }

    html.push('</div>');
    return html.join('');
}

function renderRangePicker() {
    const daysOfWeek = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    const firstDay = new Date(selectedYear, selectedMonth, 1).getDay();
    const daysInMonth = new Date(selectedYear, selectedMonth + 1, 0).getDate();
    const html = [];

    html.push('<div class="mb-4"><div class="flex items-center justify-between mb-4">');
    html.push('<button onclick="changeRangeMonth(-1)" class="p-2 hover:bg-gray-700 rounded-lg transition-all"><i class="fas fa-chevron-left"></i></button>');
    html.push(`<h4 class="text-xl font-bold">${months[selectedMonth]} ${selectedYear}</h4>`);
    html.push('<button onclick="changeRangeMonth(1)" class="p-2 hover:bg-gray-700 rounded-lg transition-all"><i class="fas fa-chevron-right"></i></button>');
    html.push('</div><div class="grid grid-cols-7 gap-2 mb-2">');

    daysOfWeek.forEach(day => html.push(`<div class="text-center text-sm text-gray-400 font-semibold">${day}</div>`));
    html.push('</div><div class="grid grid-cols-7 gap-2">');

    for (let i = 0; i < firstDay; i++) html.push('<div></div>');

    for (let day = 1; day <= daysInMonth; day++) {
        const date = new Date(selectedYear, selectedMonth, day);
        const isStart = rangeStart && date.toDateString() === rangeStart.toDateString();
        const isEnd = rangeEnd && date.toDateString() === rangeEnd.toDateString();
        const isInRange = rangeStart && rangeEnd && date >= rangeStart && date <= rangeEnd;
        let btnClass = 'bg-white bg-opacity-5 hover:bg-opacity-10 text-gray-300';
        if (isStart || isEnd) btnClass = 'bg-indigo-500 text-white';
        else if (isInRange) btnClass = 'bg-indigo-500 bg-opacity-30 text-white';
        html.push(`<button onclick="selectRangeDate(${selectedYear}, ${selectedMonth}, ${day})" class="${btnClass} px-3 py-2 rounded-lg font-semibold transition-all">${day}</button>`);
    }

    html.push('</div></div><div class="flex gap-4 text-sm">');
    html.push('<div class="flex-1 p-3 bg-white bg-opacity-5 rounded-lg"><p class="text-gray-400 mb-1">Start Date</p>');
    html.push(`<p class="font-semibold">${rangeStart ? formatDateLong(rangeStart) : 'Not selected'}</p></div>`);
    html.push('<div class="flex-1 p-3 bg-white bg-opacity-5 rounded-lg"><p class="text-gray-400 mb-1">End Date</p>');
    html.push(`<p class="font-semibold">${rangeEnd ? formatDateLong(rangeEnd) : 'Not selected'}</p></div></div>`);

    return html.join('');
}

function changeYear(delta) {
    selectedYear += delta;
    renderCalendar();
}

function changeRangeMonth(delta) {
    selectedMonth += delta;
    if (selectedMonth < 0) {
        selectedMonth = 11;
        selectedYear--;
    } else if (selectedMonth > 11) {
        selectedMonth = 0;
        selectedYear++;
    }
    renderCalendar();
}

function selectMonth(month) {
    selectedMonth = month;
    closeDateRangeModal();
    updateDateRangeDisplay();
    fetchData();
}

function selectYear(year) {
    selectedYear = year;
    closeDateRangeModal();
    updateDateRangeDisplay();
    fetchData();
}

function selectRangeDate(year, month, day) {
    const date = new Date(year, month, day);
    if (rangePicking === 'start') {
        rangeStart = date;
        rangeEnd = null;
        rangePicking = 'end';
    } else {
        if (rangeStart && date >= rangeStart) {
            rangeEnd = date;
        }
    }
    renderCalendar();
}

function formatDateLong(date) {
    const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    return `${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()}`;
}

function updateDateRangeDisplay() {
    const textElement = document.getElementById('dateRangeText');
    if (!textElement) return;
    if (datePickerMode === 'month') {
        const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
        textElement.textContent = `${months[selectedMonth]} ${selectedYear}`;
    } else if (datePickerMode === 'year') {
        textElement.textContent = `${selectedYear}`;
    } else if (datePickerMode === 'range' && rangeStart && rangeEnd) {
        textElement.textContent = `${formatDateLong(rangeStart)} - ${formatDateLong(rangeEnd)}`;
    } else {
        textElement.textContent = 'Select Date Range';
    }
}

function applyDateRange() {
    closeDateRangeModal();
    updateDateRangeDisplay();
    fetchData();
}
