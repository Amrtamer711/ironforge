// Global variables
let completionChartInstance = null;
let statusChartInstance = null; // Status pie chart
let statusBarChartInstance = null; // Status bar chart (full width)
let currentDashboardData = null; // Store dashboard data for modal
let userRole = null; // Store user role (head_of_marketing or head_of_design)
let userName = null; // Store user name
let allTasksPieChartInstance = null; // Pie chart for all tasks in modal
let overdueTasksPieChartInstance = null; // Pie chart for overdue tasks in modal
let modalDistributionChartInstance = null; // Distribution bar chart in modal

// Initialize dashboard on load
document.addEventListener('DOMContentLoaded', () => {
    // Check if user is already authenticated
    const storedRole = localStorage.getItem('userRole');
    const storedName = localStorage.getItem('userName');

    if (storedRole && storedName) {
        userRole = storedRole;
        userName = storedName;
        showDashboard();
    } else {
        showLoginScreen();
    }
});

// Show login screen
function showLoginScreen() {
    document.getElementById('loginScreen').style.display = 'flex';
    document.getElementById('mainDashboard').style.display = 'none';
}

// Show dashboard
function showDashboard() {
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('mainDashboard').style.display = 'block';

    // Update header with user name
    const userNameElement = document.getElementById('userName');
    if (userNameElement) {
        userNameElement.textContent = userName;
    }

    // Hide reviewer section if user is Head of Design
    const reviewerSection = document.getElementById('reviewerSection');
    if (reviewerSection) {
        if (userRole === 'head_of_design') {
            reviewerSection.style.display = 'none';
        } else {
            reviewerSection.style.display = 'block';
        }
    }

    initializePeriodInput();
    setupEventListeners();
    loadDashboard();
}

// Handle login
async function handleLogin(event) {
    event.preventDefault();

    const password = document.getElementById('passwordInput').value;
    const errorElement = document.getElementById('loginError');
    const loginButton = document.getElementById('loginButton');

    // Clear previous error
    errorElement.style.display = 'none';
    loginButton.disabled = true;
    loginButton.textContent = 'Logging in...';

    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ password })
        });

        const data = await response.json();

        if (data.success) {
            // Store credentials
            userRole = data.role;
            userName = data.name;
            localStorage.setItem('userRole', data.role);
            localStorage.setItem('userName', data.name);

            // Show dashboard
            showDashboard();
        } else {
            // Show error
            errorElement.textContent = data.error || 'Invalid password';
            errorElement.style.display = 'block';
            loginButton.disabled = false;
            loginButton.textContent = 'Login';
        }
    } catch (error) {
        console.error('Login error:', error);
        errorElement.textContent = 'Connection error. Please try again.';
        errorElement.style.display = 'block';
        loginButton.disabled = false;
        loginButton.textContent = 'Login';
    }
}

// Handle logout
function handleLogout() {
    localStorage.removeItem('userRole');
    localStorage.removeItem('userName');
    userRole = null;
    userName = null;

    // Reset login form
    const passwordInput = document.getElementById('passwordInput');
    const loginButton = document.getElementById('loginButton');
    const loginError = document.getElementById('loginError');

    if (passwordInput) passwordInput.value = '';
    if (loginButton) {
        loginButton.disabled = false;
        loginButton.innerHTML = '<i class="fas fa-sign-in-alt mr-2"></i>Login';
    }
    if (loginError) loginError.style.display = 'none';

    showLoginScreen();
}

// Initialize period input with current month
function initializePeriodInput() {
    // Initialize date range display with current month
    updateDateRangeDisplay();
}

// Setup event listeners
function setupEventListeners() {
    // Close modals on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeVideographerModal();
            closeDateRangeModal();
        }
    });
}

// Transform raw database tasks into the expected frontend structure
function transformRawData(rawData) {
    // rawData format: { live_tasks: [...], completed_tasks: [...] }
    // Need to transform into: { videographers: { name: [tasks...] }, summary: {...}, pie: {...}, reviewer: {...} }

    const videographers = {};
    let totalTasks = 0;
    let assignedTasks = 0;
    let uploads = 0;
    let completedTasks = 0;
    let acceptedTasks = 0;

    // Combine live_tasks and completed_tasks
    const allTasks = [...(rawData.live_tasks || []), ...(rawData.completed_tasks || [])];

    allTasks.forEach(rawTask => {
        totalTasks++;

        // Normalize field names (live_tasks use capitals, completed_tasks use lowercase)
        rawTask.task_number = rawTask.task_number;
        rawTask.brand = rawTask.Brand || rawTask.brand;
        rawTask.filming_date = rawTask['Filming Date'] || rawTask.filming_date;
        rawTask.status = rawTask.Status || rawTask.status;
        rawTask.videographer = rawTask.Videographer || rawTask.videographer;
        rawTask.version_history = rawTask['Version History'] || rawTask.version_history;

        // Parse version_history if it's still a string
        let versionHistory = rawTask.version_history;
        if (typeof versionHistory === 'string') {
            try {
                versionHistory = JSON.parse(versionHistory);
            } catch (e) {
                versionHistory = [];
            }
        }
        if (!Array.isArray(versionHistory)) {
            versionHistory = [];
        }

        // Count uploads (total versions)
        const versionNumbers = new Set(versionHistory.map(e => e.version));
        uploads += versionNumbers.size;

        // Group version history by version number to create versions array
        const versionsMap = new Map();
        versionHistory.forEach(event => {
            const versionNum = event.version || 1;
            if (!versionsMap.has(versionNum)) {
                versionsMap.set(versionNum, {
                    version: versionNum,
                    lifecycle: []
                });
            }
            // Transform event to include all fields from the database
            versionsMap.get(versionNum).lifecycle.push({
                stage: event.folder,
                at: event.at,
                rejection_class: event.rejection_class || null,
                rejection_comments: event.rejection_comments || null,
                rejected_by: event.rejected_by || null
            });
        });

        const versions = Array.from(versionsMap.values()).sort((a, b) => a.version - b.version);

        // Check if task is assigned
        if (rawTask.videographer && rawTask.videographer !== 'Unassigned') {
            assignedTasks++;
        }

        // Check if task is completed
        if (rawTask.status === 'Accepted' || rawTask.status === 'Done') {
            completedTasks++;
            if (rawTask.status === 'Accepted') {
                acceptedTasks++;
            }
        }

        // Create transformed task
        const task = {
            task_number: rawTask.task_number,
            brand: rawTask.brand,
            filming_deadline: rawTask.filming_date,
            submission_date: rawTask.submission_date,
            status: rawTask.status,
            videographer: rawTask.videographer,
            versions: versions,
            // Keep all other fields for reference
            ...rawTask
        };

        // Calculate current version (latest version with activity)
        if (versions.length > 0) {
            task.current_version = Math.max(...versions.map(v => v.version));
        } else {
            task.current_version = 1;
        }

        // Group by videographer
        const videographer = rawTask.videographer || 'Unassigned';
        if (!videographers[videographer]) {
            videographers[videographer] = [];
        }
        videographers[videographer].push(task);
    });

    // Calculate reviewer stats by getting all tasks
    const allTasksForReview = [];
    Object.values(videographers).forEach(tasks => {
        allTasksForReview.push(...tasks);
    });

    // Calculate acceptance rate: (accepted + submitted) / (accepted + rejected + returned + submitted)
    let versionsAccepted = 0;
    let versionsSubmitted = 0;
    let versionsRejectedByHOD = 0;
    let versionsReturnedByHOS = 0;

    console.log('Total tasks to process:', allTasksForReview.length);
    console.log('Sample task:', allTasksForReview[0]);

    allTasksForReview.forEach(task => {
        if (!task.versions || task.versions.length === 0) {
            console.log('Task has no versions:', task.task_number);
            return;
        }

        console.log('Processing task:', task.task_number, 'with', task.versions.length, 'versions');

        task.versions.forEach(version => {
            if (!version.lifecycle || version.lifecycle.length === 0) return;

            // Get the latest state for this version
            const latestEvent = version.lifecycle[version.lifecycle.length - 1];
            const latestStage = latestEvent.stage ? latestEvent.stage.toLowerCase() : '';

            if (latestStage === 'accepted' || latestStage === 'done') {
                versionsAccepted++;
            } else if (latestStage === 'submitted' || latestStage === 'submitted to sales') {
                versionsSubmitted++;
            }

            // Count all rejection events in lifecycle
            version.lifecycle.forEach(event => {
                const stage = event.stage ? event.stage.toLowerCase() : '';
                if (stage === 'rejected' || stage === 'editing') {
                    versionsRejectedByHOD++;
                } else if (stage === 'returned') {
                    versionsReturnedByHOS++;
                }
            });
        });
    });

    const totalReviewedVersions = versionsAccepted + versionsSubmitted + versionsRejectedByHOD + versionsReturnedByHOS;
    const acceptedPct = totalReviewedVersions > 0
        ? Math.round(((versionsAccepted + versionsSubmitted) / totalReviewedVersions) * 100)
        : 0;

    console.log('Acceptance Rate Calculation:', {
        versionsAccepted,
        versionsSubmitted,
        versionsRejectedByHOD,
        versionsReturnedByHOS,
        totalReviewedVersions,
        acceptedPct
    });

    // Calculate response times and handled count
    let totalResponseHours = 0;
    let responseCount = 0;
    let handledCount = 0;
    let acceptedByHOS = 0; // Videos where HOD accepted AND HOS accepted
    let currentlySubmittedToHOS = 0; // Videos HOD accepted, pending HOS decision
    let returnedByHOS = 0; // Videos where HOD accepted BUT HOS returned

    allTasksForReview.forEach(task => {
        if (!task.versions || task.versions.length === 0) return;

        task.versions.forEach(version => {
            if (!version.lifecycle || version.lifecycle.length < 2) return;

            // Find the FIRST upload time (first pending/critique event)
            let uploadTime = null;
            for (const event of version.lifecycle) {
                const stage = event.stage ? event.stage.toLowerCase() : '';
                if (stage === 'pending' || stage === 'critique') {
                    uploadTime = event.at ? parseDateFromBackend(event.at) : null;
                    break; // Use the first pending/critique event as upload time
                }
            }

            // Find the FIRST reviewer (HOD) decision
            let reviewTime = null;
            let reviewDecision = null;
            for (const event of version.lifecycle) {
                const stage = event.stage ? event.stage.toLowerCase() : '';
                if (stage === 'rejected' || stage === 'editing' || stage === 'accepted' ||
                    stage === 'submitted' || stage === 'submitted to sales') {
                    reviewTime = event.at ? parseDateFromBackend(event.at) : null;
                    reviewDecision = stage;
                    break; // Use the first reviewer decision
                }
            }

            // Only count if we have both upload and review times
            if (uploadTime && reviewTime && reviewDecision) {
                handledCount++;

                // Calculate response time in hours (round to nearest hour)
                const responseHours = Math.round((reviewTime - uploadTime) / (1000 * 60 * 60));
                totalResponseHours += responseHours;
                responseCount++;

                // For success rate: only consider videos that HOD accepted (reached HOS)
                if (reviewDecision === 'accepted' || reviewDecision === 'submitted' || reviewDecision === 'submitted to sales') {
                    // Check HOS decision
                    let hasHOSAccepted = false;
                    let hasHOSReturned = false;

                    for (const event of version.lifecycle) {
                        const stage = event.stage ? event.stage.toLowerCase() : '';
                        if (stage === 'accepted' || stage === 'done') {
                            hasHOSAccepted = true;
                            break;
                        }
                        if (stage === 'returned') {
                            hasHOSReturned = true;
                            break;
                        }
                    }

                    if (hasHOSAccepted) {
                        acceptedByHOS++;
                    } else if (hasHOSReturned) {
                        returnedByHOS++;
                    } else {
                        // Still pending HOS decision (submitted to sales but not yet accepted/returned)
                        currentlySubmittedToHOS++;
                    }
                }
            }
        });
    });

    const avgResponseHours = responseCount > 0 ? Math.round(totalResponseHours / responseCount) : 0;
    const avgResponseDisplay = avgResponseHours > 0 ? `${avgResponseHours} hrs` : '0 hrs';

    // Success rate = Videos where both HOD and HOS accepted / Videos where both HOD and HOS made decisions
    // (Don't count pending videos as successes - only count completed decisions)
    const totalWithHOSDecision = acceptedByHOS + returnedByHOS;
    const handledPercent = totalWithHOSDecision > 0
        ? Math.round((acceptedByHOS / totalWithHOSDecision) * 100)
        : 0;

    console.log('Reviewer Performance Calculation:', {
        totalResponseHours,
        responseCount,
        avgResponseHours,
        avgResponseDisplay,
        handledCount,
        acceptedByHOS,
        currentlySubmittedToHOS,
        returnedByHOS,
        totalWithHOSDecision,
        handledPercent,
        uploads,
        successRateFormula: `${acceptedByHOS} / (${acceptedByHOS} + ${returnedByHOS}) = ${handledPercent}%`,
        explanation: 'Success rate measures HOD correctness: videos where both HOD and HOS accepted / all videos where both made decisions'
    });

    // Calculate per-videographer summary stats
    const summaryVideographers = {};
    Object.entries(videographers).forEach(([vgName, tasks]) => {
        let vgCompleted = 0;
        let vgUploads = 0;
        let vgLate = 0;
        let vgStarted = 0;

        const now = new Date();
        now.setHours(0, 0, 0, 0);

        tasks.forEach(task => {
            // Count completed tasks
            if (task.status === 'Accepted' || task.status === 'Done') {
                vgCompleted++;
            }

            // Count uploads (versions)
            if (task.versions && task.versions.length > 0) {
                vgUploads += task.versions.length;
            }

            // Count tasks that have started (filming date passed)
            if (task.filming_deadline && task.filming_deadline !== 'NA') {
                const filmingDate = parseDateFromBackend(task.filming_deadline);
                if (filmingDate && filmingDate <= now) {
                    vgStarted++;
                }
            }

            // Count late tasks
            if (task.submission_date && task.submission_date !== 'NA') {
                const submissionDate = parseDateFromBackend(task.submission_date);
                if (submissionDate && submissionDate <= now && task.status !== 'Accepted' && task.status !== 'Done') {
                    vgLate++;
                }
            }
        });

        // Calculate acceptance rate (same logic as global acceptance rate)
        let vgVersionsAccepted = 0;
        let vgVersionsSubmitted = 0;
        let vgVersionsRejectedByHOD = 0;
        let vgVersionsReturnedByHOS = 0;

        tasks.forEach(task => {
            if (!task.versions || task.versions.length === 0) return;

            task.versions.forEach(version => {
                if (!version.lifecycle || version.lifecycle.length === 0) return;

                const latestEvent = version.lifecycle[version.lifecycle.length - 1];
                const latestStage = latestEvent.stage ? latestEvent.stage.toLowerCase() : '';

                if (latestStage === 'accepted' || latestStage === 'done') {
                    vgVersionsAccepted++;
                } else if (latestStage === 'submitted' || latestStage === 'submitted to sales') {
                    vgVersionsSubmitted++;
                }

                version.lifecycle.forEach(event => {
                    const stage = event.stage ? event.stage.toLowerCase() : '';
                    if (stage === 'rejected' || stage === 'editing') {
                        vgVersionsRejectedByHOD++;
                    } else if (stage === 'returned') {
                        vgVersionsReturnedByHOS++;
                    }
                });
            });
        });

        const vgTotalReviewedVersions = vgVersionsAccepted + vgVersionsSubmitted + vgVersionsRejectedByHOD + vgVersionsReturnedByHOS;
        const vgAcceptedPct = vgTotalReviewedVersions > 0
            ? Math.round(((vgVersionsAccepted + vgVersionsSubmitted) / vgTotalReviewedVersions) * 100)
            : 0;

        summaryVideographers[vgName] = {
            total: tasks.length,
            started: vgStarted,
            late: vgLate,
            completed: vgCompleted,
            uploads: vgUploads,
            accepted_pct: vgAcceptedPct
        };
    });

    // Calculate status breakdown for bar chart (count current versions in each state)
    let pendingVersionsCount = 0;
    let rejectedVersionsCount = 0;
    let returnedVersionsCount = 0;
    let submittedVersionsCount = 0;
    let acceptedVersionsCount = 0;

    allTasksForReview.forEach(task => {
        if (!task.versions || task.versions.length === 0) return;

        task.versions.forEach(version => {
            if (!version.lifecycle || version.lifecycle.length === 0) return;

            // Get the latest state for this version
            const latestEvent = version.lifecycle[version.lifecycle.length - 1];
            const latestStage = latestEvent.stage ? latestEvent.stage.toLowerCase() : '';

            if (latestStage === 'pending' || latestStage === 'critique') {
                pendingVersionsCount++;
            } else if (latestStage === 'rejected' || latestStage === 'editing') {
                rejectedVersionsCount++;
            } else if (latestStage === 'returned') {
                returnedVersionsCount++;
            } else if (latestStage === 'submitted' || latestStage === 'submitted to sales') {
                submittedVersionsCount++;
            } else if (latestStage === 'accepted' || latestStage === 'done') {
                acceptedVersionsCount++;
            }
        });
    });

    return {
        mode: rawData.mode,
        period: rawData.period,
        videographers: videographers,
        summary_videographers: summaryVideographers,
        summary: {
            total: totalTasks,
            assigned: assignedTasks,
            uploads: uploads,
            accepted_pct: acceptedPct,
            pending: pendingVersionsCount,
            rejected: rejectedVersionsCount,
            returned: returnedVersionsCount,
            submitted_to_sales: submittedVersionsCount,
            accepted_videos: acceptedVersionsCount
        },
        pie: {
            completed: completedTasks,
            not_completed: totalTasks - completedTasks
        },
        reviewer: {
            avg_response_display: avgResponseDisplay,
            handled: handledCount,
            accepted: acceptedByHOS,
            handled_percent: handledPercent
        }
    };
}

// Load dashboard data
async function loadDashboard() {
    const loadingState = document.getElementById('loadingState');
    const dashboardContent = document.getElementById('dashboardContent');

    // Show loading
    loadingState.style.display = 'block';
    dashboardContent.style.display = 'none';

    try {
        // Build query params based on date picker mode
        let mode = 'month';
        let period = '';

        if (datePickerMode === 'month') {
            mode = 'month';
            // Format as YYYY-MM
            period = `${selectedYear}-${String(selectedMonth + 1).padStart(2, '0')}`;
        } else if (datePickerMode === 'year') {
            mode = 'year';
            period = `${selectedYear}`;
        } else if (datePickerMode === 'range' && rangeStart && rangeEnd) {
            mode = 'range';
            // Format as YYYY-MM-DD,YYYY-MM-DD
            const startStr = `${rangeStart.getFullYear()}-${String(rangeStart.getMonth() + 1).padStart(2, '0')}-${String(rangeStart.getDate()).padStart(2, '0')}`;
            const endStr = `${rangeEnd.getFullYear()}-${String(rangeEnd.getMonth() + 1).padStart(2, '0')}-${String(rangeEnd.getDate()).padStart(2, '0')}`;
            period = `${startStr},${endStr}`;
        } else {
            // Default to current month if range not fully selected
            const now = new Date();
            period = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
        }

        const response = await fetch(`/api/dashboard?mode=${mode}&period=${period}`);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const rawData = await response.json();

        // Transform raw database data into expected structure
        const data = transformRawData(rawData);
        currentDashboardData = data; // Store for modal

        // Update UI with data
        updateQuickStats(data);
        updateReviewerStats(data);
        updateCharts(data);
        updateVideographers(data);

        // Hide loading, show content
        loadingState.style.display = 'none';
        dashboardContent.style.display = 'block';
    } catch (error) {
        console.error('Error loading dashboard:', error);
        loadingState.innerHTML = `
            <div class="text-red-400">
                <i class="fas fa-exclamation-triangle text-4xl mb-4"></i>
                <p>Error loading dashboard data</p>
                <p class="text-sm text-gray-400 mt-2">${error.message}</p>
                <button onclick="loadDashboard()" class="mt-4 px-6 py-2 bg-indigo-500 rounded-lg hover:bg-indigo-600 transition-all">
                    Retry
                </button>
            </div>
        `;
    }
}

// Update quick stats cards
function updateQuickStats(data) {
    // Calculate tasks that have started (submission date passed)
    let tasksStarted = 0;
    let lateTasks = 0;

    // Get all tasks from videographers data
    const allTasks = [];
    Object.values(data.videographers || {}).forEach(tasks => {
        allTasks.push(...tasks);
    });

    const now = new Date();
    now.setHours(0, 0, 0, 0);

    allTasks.forEach(task => {
        // Tasks Started: filming date has passed
        if (task.filming_deadline && task.filming_deadline !== 'NA') {
            const filmingDate = parseDateFromBackend(task.filming_deadline);
            if (filmingDate && filmingDate <= now) {
                tasksStarted++;
            }
        }

        // Late Tasks: submission date has passed but not completed
        if (task.submission_date && task.submission_date !== 'NA') {
            const submissionDate = parseDateFromBackend(task.submission_date);
            // Exclude completed tasks (Accepted or Done)
            if (submissionDate && submissionDate <= now && task.status !== 'Accepted' && task.status !== 'Done') {
                lateTasks++;
            }
        }
    });

    // Recalculate pending/submitted counts to match modal logic (exclude completed tasks)
    const pendingVersions = getTasksWithVersionsInState(allTasks, 'pending');
    const submittedVersions = getTasksWithVersionsInState(allTasks, 'submitted');

    // Calculate upload to completed task ratio (average versions per completed task)
    let totalVersionsFromCompletedTasks = 0;
    let completedTaskCount = 0;
    let totalRejectionsByHOD = 0;
    let totalRejectionsByHOS = 0;

    allTasks.forEach(task => {
        // Check if task is completed
        if (task.status === 'Accepted' || task.status === 'Done') {
            completedTaskCount++;
            // Count how many versions this completed task has
            if (task.versions && task.versions.length > 0) {
                totalVersionsFromCompletedTasks += task.versions.length;
            }
        }

        // Count all rejection events in version history
        if (task.versions && task.versions.length > 0) {
            task.versions.forEach(version => {
                if (version.lifecycle && version.lifecycle.length > 0) {
                    version.lifecycle.forEach(event => {
                        const stage = event.stage ? event.stage.toLowerCase() : '';
                        // Count HOD rejections (rejected/editing)
                        if (stage === 'rejected' || stage === 'editing') {
                            totalRejectionsByHOD++;
                        }
                        // Count HOS rejections (returned)
                        if (stage === 'returned') {
                            totalRejectionsByHOS++;
                        }
                    });
                }
            });
        }
    });

    const uploadRatio = completedTaskCount > 0
        ? (totalVersionsFromCompletedTasks / completedTaskCount).toFixed(2)
        : '0';

    // Row 1
    document.getElementById('totalTasksCreated').textContent = data.summary.total;
    document.getElementById('totalTasksAssigned').textContent = data.summary.assigned;
    document.getElementById('totalTasksStarted').textContent = tasksStarted;
    document.getElementById('totalLateTasks').textContent = lateTasks;
    document.getElementById('totalVersionsUploaded').textContent = data.summary.uploads;
    document.getElementById('completedTasks').textContent = data.pie.completed;

    // Row 2 - Use recalculated counts
    document.getElementById('pendingHOD').textContent = pendingVersions.length;
    document.getElementById('pendingHOS').textContent = submittedVersions.length;
    document.getElementById('rejectedByHOD').textContent = totalRejectionsByHOD; // Total rejection events
    document.getElementById('rejectedByHOS').textContent = totalRejectionsByHOS; // Total rejection events
    document.getElementById('uploadToCompletedRatio').textContent = uploadRatio;
    document.getElementById('acceptanceRate').textContent = `${data.summary.accepted_pct}%`;
}

// Update summary statistics - REMOVED (no longer needed)

// Update reviewer statistics
function updateReviewerStats(data) {
    document.getElementById('avgResponseTime').textContent = data.reviewer.avg_response_display;
    document.getElementById('reviewerHandled').textContent = data.reviewer.handled;
    document.getElementById('reviewerAccepted').textContent = data.reviewer.accepted;
    document.getElementById('handledPercent').textContent = `${data.reviewer.handled_percent}%`;

    // Calculate pending reviews count
    const allTasks = [];
    Object.values(data.videographers || {}).forEach(tasks => {
        allTasks.push(...tasks);
    });

    const pendingReviewsData = getPendingReviews(allTasks);
    document.getElementById('pendingReviews').textContent = pendingReviewsData.count;
}

// Update charts
function updateCharts(data) {
    updateCompletionChart(data);
    updateStatusPieChart(data);
    updateStatusBarChart(data);
}

// Update completion pie chart
function updateCompletionChart(data) {
    const ctx = document.getElementById('completionChart').getContext('2d');

    // Destroy existing chart
    if (completionChartInstance) {
        completionChartInstance.destroy();
    }

    completionChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Completed', 'Not Completed'],
            datasets: [{
                data: [data.pie.completed, data.pie.not_completed],
                backgroundColor: [
                    'rgba(34, 197, 94, 0.8)',
                    'rgba(239, 68, 68, 0.8)'
                ],
                hoverBackgroundColor: [
                    'rgba(34, 197, 94, 1)',
                    'rgba(239, 68, 68, 1)'
                ],
                borderColor: [
                    'rgba(34, 197, 94, 1)',
                    'rgba(239, 68, 68, 1)'
                ],
                borderWidth: 2,
                hoverBorderWidth: 2,
                hoverOffset: 0,
                offset: 0,
                spacing: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'nearest'
            },
            animation: {
                animateScale: false,
                animateRotate: true
            },
            elements: {
                arc: {
                    offset: 0,
                    hoverOffset: 0
                }
            },
            onHover: (event, activeElements) => {
                event.native.target.style.cursor = activeElements.length > 0 ? 'pointer' : 'default';
            },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        font: {
                            size: 12,
                            family: 'Inter'
                        },
                        padding: 15
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: 'white',
                    bodyColor: 'white',
                    borderColor: 'rgba(99, 102, 241, 0.5)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            const total = data.summary.total;
                            const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                            return `${label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

// Update status pie chart (for passed tasks)
function updateStatusPieChart(data) {
    const ctx = document.getElementById('statusChart').getContext('2d');

    // Destroy existing chart
    if (statusChartInstance) {
        statusChartInstance.destroy();
    }

    // Use the same completed count from backend (data.pie.completed)
    // But only count tasks where filming date has passed for "not completed"
    const now = new Date();
    now.setHours(0, 0, 0, 0);

    // Get all tasks from videographers data
    const allTasks = [];
    Object.values(data.videographers || {}).forEach(tasks => {
        allTasks.push(...tasks);
    });

    // Count tasks that have started
    let tasksStarted = 0;
    allTasks.forEach(task => {
        if (task.filming_deadline && task.filming_deadline !== 'NA') {
            const filmingDate = parseDateFromBackend(task.filming_deadline);
            if (filmingDate && filmingDate <= now) {
                tasksStarted++;
            }
        }
    });

    // Completed = backend's pie.completed
    // Not completed = tasks started - completed
    const completedStartedTasks = data.pie.completed;
    const notCompletedStartedTasks = tasksStarted - completedStartedTasks;

    statusChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Completed', 'Not Completed'],
            datasets: [{
                data: [completedStartedTasks, notCompletedStartedTasks],
                backgroundColor: [
                    'rgba(34, 197, 94, 0.8)',
                    'rgba(239, 68, 68, 0.8)'
                ],
                hoverBackgroundColor: [
                    'rgba(34, 197, 94, 1)',
                    'rgba(239, 68, 68, 1)'
                ],
                borderColor: [
                    'rgba(34, 197, 94, 1)',
                    'rgba(239, 68, 68, 1)'
                ],
                borderWidth: 2,
                hoverBorderWidth: 2,
                hoverOffset: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'nearest'
            },
            animation: {
                animateScale: false,
                animateRotate: true
            },
            elements: {
                arc: {
                    offset: 0,
                    hoverOffset: 0
                }
            },
            onHover: (event, activeElements) => {
                event.native.target.style.cursor = activeElements.length > 0 ? 'pointer' : 'default';
            },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        font: {
                            size: 12,
                            family: 'Inter'
                        },
                        padding: 15
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: 'white',
                    bodyColor: 'white',
                    borderColor: 'rgba(99, 102, 241, 0.5)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            const total = completedStartedTasks + notCompletedStartedTasks;
                            const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                            return `${label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

// Update status bar chart (full width)
function updateStatusBarChart(data) {
    const ctx = document.getElementById('statusBarChart').getContext('2d');

    // Destroy existing chart
    if (statusBarChartInstance) {
        statusBarChartInstance.destroy();
    }

    statusBarChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Pending HOD Review', 'Rejected by HOD', 'Rejected by HOS', 'Pending HOS Review', 'Accepted by HOS'],
            datasets: [{
                label: 'Videos',
                data: [
                    data.summary.pending,
                    data.summary.rejected,
                    data.summary.returned,
                    data.summary.submitted_to_sales,
                    data.summary.accepted_videos
                ],
                backgroundColor: [
                    'rgba(234, 179, 8, 0.8)',
                    'rgba(239, 68, 68, 0.8)',
                    'rgba(249, 115, 22, 0.8)',
                    'rgba(59, 130, 246, 0.8)',
                    'rgba(34, 197, 94, 0.8)'
                ],
                borderColor: [
                    'rgba(234, 179, 8, 1)',
                    'rgba(239, 68, 68, 1)',
                    'rgba(249, 115, 22, 1)',
                    'rgba(59, 130, 246, 1)',
                    'rgba(34, 197, 94, 1)'
                ],
                borderWidth: 2,
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.6)',
                        font: {
                            size: 11,
                            family: 'Inter'
                        },
                        stepSize: 1
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)',
                        drawBorder: false
                    }
                },
                x: {
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.6)',
                        font: {
                            size: 11,
                            family: 'Inter'
                        }
                    },
                    grid: {
                        display: false
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: 'white',
                    bodyColor: 'white',
                    borderColor: 'rgba(99, 102, 241, 0.5)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: false
                }
            }
        }
    });
}

// Update videographers section
function updateVideographers(data) {
    const container = document.getElementById('videographersList');

    if (Object.keys(data.summary_videographers).length === 0) {
        container.innerHTML = `
            <div class="text-center py-8 text-gray-400">
                <i class="fas fa-user-slash text-4xl mb-3"></i>
                <p>No videographer data available for this period</p>
            </div>
        `;
        return;
    }

    container.innerHTML = '';

    // Sort videographers by total tasks descending
    const sortedVGs = Object.entries(data.summary_videographers)
        .sort((a, b) => b[1].total - a[1].total);

    for (const [vgName, stats] of sortedVGs) {
        const vgCard = document.createElement('div');
        vgCard.className = 'videographer-card p-6 rounded-xl transition-all';
        vgCard.onclick = () => openVideographerModal(vgName, stats, data.videographers[vgName] || []);

        vgCard.innerHTML = `
            <div class="flex items-center justify-between mb-4">
                <div class="flex items-center space-x-3">
                    <div class="w-12 h-12 bg-gradient-to-br from-green-400 to-blue-500 rounded-full flex items-center justify-center">
                        <span class="text-xl font-bold">${vgName.charAt(0).toUpperCase()}</span>
                    </div>
                    <div>
                        <h4 class="text-lg font-semibold">${vgName}</h4>
                        <p class="text-sm text-gray-400">${stats.total} tasks assigned</p>
                    </div>
                </div>
                <div class="flex items-center space-x-3">
                    <div class="text-right">
                        <p class="text-2xl font-bold ${stats.accepted_pct >= 70 ? 'text-green-400' : stats.accepted_pct >= 50 ? 'text-yellow-400' : 'text-red-400'}">
                            ${stats.accepted_pct}%
                        </p>
                        <p class="text-xs text-gray-400">Acceptance Rate</p>
                    </div>
                    <i class="fas fa-arrow-right text-gray-500"></i>
                </div>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div class="text-center p-3 bg-white bg-opacity-5 rounded-lg">
                    <p class="text-lg font-bold text-cyan-400">${stats.started}</p>
                    <p class="text-xs text-gray-400">Tasks Started</p>
                </div>
                <div class="text-center p-3 bg-white bg-opacity-5 rounded-lg">
                    <p class="text-lg font-bold text-red-400">${stats.late}</p>
                    <p class="text-xs text-gray-400">Late Tasks</p>
                </div>
                <div class="text-center p-3 bg-white bg-opacity-5 rounded-lg">
                    <p class="text-lg font-bold text-green-400">${stats.completed}</p>
                    <p class="text-xs text-gray-400">Completed Tasks</p>
                </div>
                <div class="text-center p-3 bg-white bg-opacity-5 rounded-lg">
                    <p class="text-lg font-bold text-purple-400">${stats.uploads}</p>
                    <p class="text-xs text-gray-400">Total Uploads</p>
                </div>
            </div>

            <!-- Progress bar -->
            <div class="mt-4">
                <div class="w-full bg-gray-700 rounded-full h-2 overflow-hidden">
                    <div class="h-full bg-gradient-to-r from-green-400 to-blue-500 transition-all duration-500"
                         style="width: ${stats.accepted_pct}%">
                    </div>
                </div>
            </div>
        `;

        container.appendChild(vgCard);
    }
}

// Open videographer modal
function openVideographerModal(vgName, stats, tasks) {
    const modal = document.getElementById('videographerModal');

    // Update header
    document.getElementById('modalInitial').textContent = vgName.charAt(0).toUpperCase();
    document.getElementById('modalTitle').textContent = vgName;
    document.getElementById('modalSubtitle').textContent = `${stats.total} Tasks | ${stats.accepted_pct}% Acceptance Rate`;

    // Calculate version counts from tasks
    let vgPending = 0, vgRejected = 0, vgReturned = 0, vgSubmitted = 0, vgAccepted = 0;

    // Calculate rejection distribution
    const rejectionClasses = {};
    let totalRejections = 0;

    tasks.forEach(task => {
        if (!task.versions) return;
        task.versions.forEach(version => {
            if (!version.lifecycle || version.lifecycle.length === 0) return;
            const latestEvent = version.lifecycle[version.lifecycle.length - 1];
            const latestStage = latestEvent.stage ? latestEvent.stage.toLowerCase() : '';

            if (latestStage === 'pending' || latestStage === 'critique') vgPending++;
            else if (latestStage === 'rejected' || latestStage === 'editing') vgRejected++;
            else if (latestStage === 'returned') vgReturned++;
            else if (latestStage === 'submitted' || latestStage === 'submitted to sales') vgSubmitted++;
            else if (latestStage === 'accepted' || latestStage === 'done') vgAccepted++;

            // Collect rejection events for distribution
            version.lifecycle.forEach(event => {
                const stage = event.stage ? event.stage.toLowerCase() : '';
                if (stage === 'rejected' || stage === 'editing' || stage === 'returned') {
                    const rejClass = event.rejection_class || 'Unclassified';
                    rejectionClasses[rejClass] = (rejectionClasses[rejClass] || 0) + 1;
                    totalRejections++;
                }
            });
        });
    });

    // Calculate rejection rate
    const totalVersions = vgPending + vgRejected + vgReturned + vgSubmitted + vgAccepted;
    const rejectionRate = totalVersions > 0 ? ((totalRejections / totalVersions) * 100).toFixed(1) : 0;

    document.getElementById('modalStats').innerHTML = `
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="text-center p-4 bg-white bg-opacity-5 rounded-lg">
                <p class="text-3xl font-bold text-emerald-400">${stats.accepted_pct}%</p>
                <p class="text-sm text-gray-400 mt-2">Acceptance Rate</p>
            </div>
            <div class="text-center p-4 bg-white bg-opacity-5 rounded-lg">
                <p class="text-3xl font-bold text-red-400">${rejectionRate}%</p>
                <p class="text-sm text-gray-400 mt-2">Rejection Rate</p>
            </div>
        </div>
    `;

    // Section 1: Detailed Stats
    document.getElementById('modalDetailedStats').innerHTML = `
        <div class="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <div class="text-center p-4 bg-white bg-opacity-5 rounded-lg">
                <p class="text-2xl font-bold text-yellow-400">${vgPending}</p>
                <p class="text-xs text-gray-400 mt-2">Pending HOD</p>
            </div>
            <div class="text-center p-4 bg-white bg-opacity-5 rounded-lg">
                <p class="text-2xl font-bold text-red-400">${vgRejected}</p>
                <p class="text-xs text-gray-400 mt-2">Rejected by HOD</p>
            </div>
            <div class="text-center p-4 bg-white bg-opacity-5 rounded-lg">
                <p class="text-2xl font-bold text-orange-400">${vgReturned}</p>
                <p class="text-xs text-gray-400 mt-2">Rejected by HOS</p>
            </div>
            <div class="text-center p-4 bg-white bg-opacity-5 rounded-lg">
                <p class="text-2xl font-bold text-blue-400">${vgSubmitted}</p>
                <p class="text-xs text-gray-400 mt-2">Pending HOS</p>
            </div>
            <div class="text-center p-4 bg-white bg-opacity-5 rounded-lg">
                <p class="text-2xl font-bold text-green-400">${vgAccepted}</p>
                <p class="text-xs text-gray-400 mt-2">Accepted</p>
            </div>
            <div class="text-center p-4 bg-white bg-opacity-5 rounded-lg">
                <p class="text-2xl font-bold text-emerald-400">${stats.accepted_pct}%</p>
                <p class="text-xs text-gray-400 mt-2">Acceptance Rate</p>
            </div>
        </div>
    `;

    // Section 2: Version History
    document.getElementById('modalVersionHistory').innerHTML = renderTaskDetails(tasks);

    // Section 3: Failure Analysis
    document.getElementById('modalFailureAnalysis').innerHTML = renderFailureAnalysis(tasks);

    // Create distribution chart
    createModalDistributionChart(vgPending, vgRejected, vgReturned, vgSubmitted, vgAccepted);

    // Reset scroll to first section
    document.getElementById('modalScrollContainer').scrollLeft = 0;

    // Show modal
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

// Parse date from backend (dd-mm-yyyy format)
function parseDateFromBackend(dateStr) {
    if (!dateStr || dateStr === 'NA') return null;

    try {
        // Check if this is a datetime string (dd-mm-yyyy HH:MM:SS) or just a date (dd-mm-yyyy)
        const hasTime = dateStr.includes(':');

        if (hasTime) {
            // Parse dd-mm-yyyy HH:MM:SS format
            const [datePart, timePart] = dateStr.split(' ');
            const dateParts = datePart.split('-');
            const timeParts = timePart.split(':');

            if (dateParts.length !== 3 || timeParts.length !== 3) return null;

            const day = parseInt(dateParts[0]);
            const month = parseInt(dateParts[1]) - 1; // JS months are 0-indexed
            const year = parseInt(dateParts[2]);
            const hours = parseInt(timeParts[0]);
            const minutes = parseInt(timeParts[1]);
            const seconds = parseInt(timeParts[2]);

            return new Date(year, month, day, hours, minutes, seconds);
        } else {
            // Parse dd-mm-yyyy format (date only)
            const parts = dateStr.split('-');
            if (parts.length !== 3) return null;

            const day = parseInt(parts[0]);
            const month = parseInt(parts[1]) - 1; // JS months are 0-indexed
            const year = parseInt(parts[2]);

            const date = new Date(year, month, day);
            date.setHours(0, 0, 0, 0);
            return date;
        }
    } catch (e) {
        console.error('Error parsing date from backend:', e);
        return null;
    }
}

// Calculate submission date (filming date + 3 working days)
// NOTE: This is a simplified version. Backend uses proper UAE working days logic.
// Prefer using task.submission_date from backend when available.
function calculateSubmissionDate(filmingDateStr) {
    if (!filmingDateStr) return null;

    try {
        // Parse dd-mm-yyyy format
        const parts = filmingDateStr.split('-');
        if (parts.length !== 3) return null;

        const day = parseInt(parts[0]);
        const month = parseInt(parts[1]) - 1; // JS months are 0-indexed
        const year = parseInt(parts[2]);

        let filmingDate = new Date(year, month, day);

        // Add 3 working days (skip weekends only - backend handles UAE holidays)
        let workingDaysAdded = 0;
        let currentDate = new Date(filmingDate);

        while (workingDaysAdded < 3) {
            currentDate.setDate(currentDate.getDate() + 1);
            const dayOfWeek = currentDate.getDay();
            // Skip Saturday (6) and Sunday (0)
            if (dayOfWeek !== 0 && dayOfWeek !== 6) {
                workingDaysAdded++;
            }
        }

        return currentDate;
    } catch (e) {
        console.error('Error calculating submission date:', e);
        return null;
    }
}

// Check if task is overdue based on submission date
function isTaskOverdue(task) {
    // Prefer backend-calculated submission date (includes UAE holidays)
    let submissionDate = null;

    if (task.submission_date && task.submission_date !== 'NA') {
        submissionDate = parseDateFromBackend(task.submission_date);
    } else {
        // Fallback to client-side calculation (less accurate)
        submissionDate = calculateSubmissionDate(task.filming_deadline || task.filming_date);
    }

    if (!submissionDate) return false;

    const now = new Date();
    now.setHours(0, 0, 0, 0); // Reset time to start of day

    // Task is overdue if submission date has passed and it's not accepted
    return submissionDate < now && task.status !== 'Accepted';
}

// Create pie charts in modal
function createModalPieCharts(tasks) {
    // Destroy existing charts
    if (allTasksPieChartInstance) {
        allTasksPieChartInstance.destroy();
    }
    if (overdueTasksPieChartInstance) {
        overdueTasksPieChartInstance.destroy();
    }
    if (modalDistributionChartInstance) {
        modalDistributionChartInstance.destroy();
    }

    // Count tasks by status for all tasks
    const statusCounts = {
        'Pending': 0,
        'Rejected': 0,
        'Returned': 0,
        'Submitted to Sales': 0,
        'Accepted': 0
    };

    // Count tasks where submission date has passed (include ALL statuses)
    const submissionPassedCounts = {
        'Pending': 0,
        'Rejected': 0,
        'Returned': 0,
        'Submitted to Sales': 0,
        'Accepted': 0
    };

    const now = new Date();
    now.setHours(0, 0, 0, 0);

    tasks.forEach(task => {
        // Count all tasks
        if (statusCounts.hasOwnProperty(task.status)) {
            statusCounts[task.status]++;
        }

        // Count tasks where submission date has passed (regardless of status)
        if (task.submission_date && task.submission_date !== 'NA') {
            const submissionDate = parseDateFromBackend(task.submission_date);
            if (submissionDate && submissionDate < now) {
                if (submissionPassedCounts.hasOwnProperty(task.status)) {
                    submissionPassedCounts[task.status]++;
                }
            }
        }
    });

    // Chart colors
    const chartColors = {
        'Pending': 'rgba(234, 179, 8, 0.8)',      // Yellow
        'Rejected': 'rgba(239, 68, 68, 0.8)',     // Red
        'Returned': 'rgba(249, 115, 22, 0.8)',    // Orange
        'Submitted to Sales': 'rgba(59, 130, 246, 0.8)', // Blue
        'Accepted': 'rgba(34, 197, 94, 0.8)'      // Green
    };

    // Create All Tasks Pie Chart
    const allTasksCtx = document.getElementById('allTasksPieChart').getContext('2d');
    const allTasksData = Object.entries(statusCounts).filter(([_, count]) => count > 0);

    allTasksPieChartInstance = new Chart(allTasksCtx, {
        type: 'pie',
        data: {
            labels: allTasksData.map(([status]) => status),
            datasets: [{
                data: allTasksData.map(([_, count]) => count),
                backgroundColor: allTasksData.map(([status]) => chartColors[status]),
                borderColor: 'rgba(255, 255, 255, 0.1)',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        padding: 15,
                        font: { size: 12 }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((value / total) * 100).toFixed(1);
                            return `${label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });

    // Create Submission Passed Tasks Pie Chart (right chart)
    const overdueTasksCtx = document.getElementById('overdueTasksPieChart').getContext('2d');
    const submissionPassedData = Object.entries(submissionPassedCounts).filter(([_, count]) => count > 0);

    overdueTasksPieChartInstance = new Chart(overdueTasksCtx, {
        type: 'pie',
        data: {
            labels: submissionPassedData.map(([status]) => status),
            datasets: [{
                data: submissionPassedData.map(([_, count]) => count),
                backgroundColor: submissionPassedData.map(([status]) => chartColors[status]),
                borderColor: 'rgba(255, 255, 255, 0.1)',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        padding: 15,
                        font: { size: 12 }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((value / total) * 100).toFixed(1);
                            return `${label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });

    // Create Distribution Bar Chart
    const distributionCtx = document.getElementById('modalDistributionChart').getContext('2d');
    const distributionData = Object.entries(statusCounts).filter(([_, count]) => count > 0);

    modalDistributionChartInstance = new Chart(distributionCtx, {
        type: 'bar',
        data: {
            labels: distributionData.map(([status]) => status),
            datasets: [{
                label: 'Number of Videos',
                data: distributionData.map(([_, count]) => count),
                backgroundColor: distributionData.map(([status]) => chartColors[status]),
                borderColor: distributionData.map(([status]) => chartColors[status].replace('0.8', '1')),
                borderWidth: 2,
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        stepSize: 1,
                        font: { size: 12 }
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)',
                        drawBorder: false
                    }
                },
                x: {
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        font: { size: 12 }
                    },
                    grid: {
                        display: false
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const value = context.parsed.y || 0;
                            const total = distributionData.reduce((sum, [_, count]) => sum + count, 0);
                            const percentage = ((value / total) * 100).toFixed(1);
                            return `Videos: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

// Close videographer modal
function closeVideographerModal() {
    const modal = document.getElementById('videographerModal');
    modal.classList.add('closing');

    setTimeout(() => {
        modal.classList.add('hidden');
        modal.classList.remove('closing');
        document.body.style.overflow = ''; // Restore scrolling
    }, 300);
}

// Close modal on backdrop click
function closeModal(event) {
    if (event.target.id === 'videographerModal') {
        closeVideographerModal();
    }
}

// Render task details
function renderTaskDetails(tasks) {
    if (!tasks || tasks.length === 0) {
        return '<p class="text-gray-400 text-center py-8">No tasks found for this videographer</p>';
    }

    return tasks.map(task => `
        <div class="task-card p-6 rounded-xl mb-6">
            <div class="flex items-start justify-between mb-4">
                <div>
                    <h5 class="text-xl font-semibold text-white mb-1">
                        <i class="fas fa-tasks mr-2 text-indigo-400"></i>
                        Task #${task.task_number}
                    </h5>
                    <p class="text-lg text-gray-300">${task.brand || 'No brand'}</p>
                    <div class="flex flex-wrap gap-3 mt-2 text-sm text-gray-400">
                        ${task.reference ? `<span><i class="fas fa-hashtag mr-1"></i>Ref: ${task.reference}</span>` : ''}
                        ${task.filming_deadline ? `<span><i class="fas fa-calendar mr-1"></i>Filming: ${task.filming_deadline}</span>` : ''}
                    </div>
                </div>
                <span class="px-4 py-2 rounded-full text-sm font-semibold ${getStatusBadgeClass(task.status)}">
                    ${task.status}
                </span>
            </div>

            ${renderVersionHistory(task.versions)}
        </div>
    `).join('');
}

// Render version history
function renderVersionHistory(versions) {
    if (!versions || versions.length === 0) {
        return `
            <div class="bg-white bg-opacity-5 rounded-lg p-4 text-center">
                <i class="fas fa-inbox text-3xl text-gray-600 mb-2"></i>
                <p class="text-gray-500">No versions uploaded yet</p>
            </div>
        `;
    }

    return `
        <div class="space-y-4">
            <h6 class="text-sm font-semibold text-indigo-300 uppercase tracking-wide flex items-center">
                <i class="fas fa-layer-group mr-2"></i>
                Version History (${versions.length} ${versions.length === 1 ? 'version' : 'versions'})
            </h6>
            ${versions.map(version => `
                <div class="bg-white bg-opacity-5 rounded-lg p-4">
                    <div class="flex items-center justify-between mb-3">
                        <h6 class="font-bold text-lg text-indigo-300">
                            <i class="fas fa-code-branch mr-2"></i>
                            Version ${version.version}
                        </h6>
                    </div>

                    <div class="version-timeline space-y-2">
                        ${version.lifecycle.map((event, index) => `
                            <div class="flex items-start space-x-3 relative">
                                <div class="w-3 h-3 rounded-full ${getStageColor(event.stage)} mt-1 z-10 ring-4 ring-black"></div>
                                <div class="flex-1">
                                    <div class="flex items-center justify-between">
                                        <span class="font-semibold ${getStageTextColor(event.stage)}">
                                            ${formatStageName(event.stage)}
                                        </span>
                                        <span class="text-xs text-gray-500">${event.at || 'No timestamp'}</span>
                                    </div>
                                    ${event.rejection_class || event.rejection_comments ? `
                                        <div class="mt-2 p-3 bg-red-900 bg-opacity-20 border border-red-500 border-opacity-30 rounded-lg">
                                            ${event.rejection_class ? `
                                                <p class="text-sm font-medium text-red-300 mb-1">
                                                    <i class="fas fa-tag mr-1"></i>${event.rejection_class}
                                                </p>
                                            ` : ''}
                                            ${event.rejection_comments ? `
                                                <p class="text-sm text-red-200">
                                                    <i class="fas fa-comment-dots mr-1"></i>${event.rejection_comments}
                                                </p>
                                            ` : ''}
                                            ${event.rejected_by ? `
                                                <p class="text-xs text-red-400 mt-1">
                                                    <i class="fas fa-user mr-1"></i>By: ${event.rejected_by}
                                                </p>
                                            ` : ''}
                                        </div>
                                    ` : ''}
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

// Get status badge class
function getStatusBadgeClass(status) {
    const classes = {
        'Pending': 'bg-yellow-500 bg-opacity-20 text-yellow-300 border border-yellow-500',
        'Done': 'bg-green-500 bg-opacity-20 text-green-300 border border-green-500',
        'Rejected': 'bg-red-500 bg-opacity-20 text-red-300 border border-red-500',
        'Returned': 'bg-orange-500 bg-opacity-20 text-orange-300 border border-orange-500',
        'Submitted to Sales': 'bg-blue-500 bg-opacity-20 text-blue-300 border border-blue-500'
    };
    return classes[status] || 'bg-gray-500 bg-opacity-20 text-gray-300 border border-gray-500';
}

// Get stage color (for timeline dots)
function getStageColor(stage) {
    const lowerStage = (stage || '').toLowerCase();
    const colors = {
        'critique': 'bg-yellow-400',
        'pending': 'bg-yellow-400',
        'editing': 'bg-red-400',
        'rejected': 'bg-red-400',
        'returned': 'bg-red-400',
        'submitted to sales': 'bg-blue-400',
        'submitted': 'bg-blue-400',
        'accepted': 'bg-green-400',
        'done': 'bg-green-400'
    };
    return colors[lowerStage] || 'bg-gray-400';
}

// Get stage text color
function getStageTextColor(stage) {
    const lowerStage = (stage || '').toLowerCase();
    const colors = {
        'critique': 'text-yellow-300',
        'pending': 'text-yellow-300',
        'editing': 'text-red-300',
        'rejected': 'text-red-300',
        'returned': 'text-red-300',
        'submitted to sales': 'text-blue-300',
        'submitted': 'text-blue-300',
        'accepted': 'text-green-300',
        'done': 'text-green-300'
    };
    return colors[lowerStage] || 'text-gray-300';
}

// Format stage name for version lifecycle
function formatStageName(stage) {
    if (!stage) return 'Unknown';

    const versionStageMap = {
        'Critique': 'Uploaded',
        'critique': 'Uploaded',
        'pending': 'Uploaded',
        'Pending': 'Uploaded',
        'Editing': 'Rejected by HOD',
        'editing': 'Rejected by HOD',
        'rejected': 'Rejected by HOD',
        'Rejected': 'Rejected by HOD',
        'Submitted': 'Accepted by HOD',
        'submitted': 'Accepted by HOD',
        'Returned': 'Rejected By HOS',
        'returned': 'Rejected By HOS',
        'Accepted': 'Accepted',
        'accepted': 'Accepted',
        'Done': 'Accepted',
        'done': 'Accepted'
    };

    return versionStageMap[stage] || stage.charAt(0).toUpperCase() + stage.slice(1);
}

// Handle errors gracefully
window.addEventListener('error', (event) => {
    console.error('Global error:', event.error);
});

// ==================== DATE RANGE PICKER ====================

// Date range picker state
let datePickerMode = 'month'; // 'month', 'year', or 'range'
let selectedYear = new Date().getFullYear();
let selectedMonth = new Date().getMonth(); // 0-indexed
let rangeStart = null;
let rangeEnd = null;
let rangePicking = 'start'; // 'start' or 'end'
let availableMonths = []; // Will be populated from backend data

// Open date range modal
function openDateRangeModal() {
    const modal = document.getElementById('dateRangeModal');
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    renderCalendar();
}

// Close date range modal
function closeDateRangeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('dateRangeModal');
    modal.classList.add('hidden');
    document.body.style.overflow = '';
}

// Switch between date picker modes
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

    // Render calendar with animation
    const content = document.getElementById('calendarContent');
    content.style.opacity = '0';
    content.style.transform = 'scale(0.95)';

    setTimeout(() => {
        renderCalendar();
        content.style.transition = 'all 0.3s ease';
        content.style.opacity = '1';
        content.style.transform = 'scale(1)';
    }, 150);
}

// Render calendar based on current mode
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

// Render month picker
function renderMonthPicker() {
    const months = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ];

    let html = `
        <div class="mb-6">
            <div class="flex items-center justify-between mb-4">
                <button onclick="changeYear(-1)" class="p-2 hover:bg-gray-700 rounded-lg transition-all">
                    <i class="fas fa-chevron-left"></i>
                </button>
                <h4 class="text-xl font-bold">${selectedYear}</h4>
                <button onclick="changeYear(1)" class="p-2 hover:bg-gray-700 rounded-lg transition-all">
                    <i class="fas fa-chevron-right"></i>
                </button>
            </div>
            <div class="grid grid-cols-3 gap-4">
    `;

    months.forEach((month, index) => {
        const isSelected = selectedYear === new Date().getFullYear() && selectedMonth === index;
        const isAvailable = true; // For now, all months are available
        const btnClass = isSelected
            ? 'bg-indigo-500 text-white'
            : isAvailable
                ? 'bg-gray-700 hover:bg-gray-600 text-white'
                : 'bg-gray-800 text-gray-500 cursor-not-allowed';

        html += `
            <button
                onclick="selectMonth(${index})"
                ${!isAvailable ? 'disabled' : ''}
                class="${btnClass} px-4 py-3 rounded-lg font-semibold transition-all transform hover:scale-105">
                ${month}
            </button>
        `;
    });

    html += '</div></div>';
    return html;
}

// Render year picker
function renderYearPicker() {
    const currentYear = new Date().getFullYear();
    const years = [];

    // Show 5 years before and 5 years after current year
    for (let i = currentYear - 5; i <= currentYear + 5; i++) {
        years.push(i);
    }

    let html = '<div class="grid grid-cols-3 gap-4">';

    years.forEach(year => {
        const isSelected = year === selectedYear;
        const isAvailable = true; // For now, all years are available
        const btnClass = isSelected
            ? 'bg-indigo-500 text-white'
            : isAvailable
                ? 'bg-gray-700 hover:bg-gray-600 text-white'
                : 'bg-gray-800 text-gray-500 cursor-not-allowed';

        html += `
            <button
                onclick="selectYear(${year})"
                ${!isAvailable ? 'disabled' : ''}
                class="${btnClass} px-6 py-4 rounded-lg font-bold text-lg transition-all transform hover:scale-105">
                ${year}
            </button>
        `;
    });

    html += '</div>';
    return html;
}

// Render range picker with calendar
function renderRangePicker() {
    const months = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ];

    let html = `
        <div class="mb-6">
            <div class="flex items-center justify-between mb-4">
                <button onclick="changeRangeMonth(-1)" class="p-2 hover:bg-gray-700 rounded-lg transition-all">
                    <i class="fas fa-chevron-left"></i>
                </button>
                <h4 class="text-xl font-bold">${months[selectedMonth]} ${selectedYear}</h4>
                <button onclick="changeRangeMonth(1)" class="p-2 hover:bg-gray-700 rounded-lg transition-all">
                    <i class="fas fa-chevron-right"></i>
                </button>
            </div>

            <!-- Range Selection Display -->
            <div class="grid grid-cols-2 gap-4 mb-6">
                <div class="p-4 ${rangePicking === 'start' ? 'bg-indigo-500 bg-opacity-20 border-2 border-indigo-500' : 'bg-gray-700'} rounded-lg cursor-pointer" onclick="setRangePicking('start')">
                    <p class="text-sm text-gray-400 mb-1">Start Date</p>
                    <p class="font-bold">${rangeStart ? formatDateShort(rangeStart) : 'Select start date'}</p>
                </div>
                <div class="p-4 ${rangePicking === 'end' ? 'bg-indigo-500 bg-opacity-20 border-2 border-indigo-500' : 'bg-gray-700'} rounded-lg cursor-pointer" onclick="setRangePicking('end')">
                    <p class="text-sm text-gray-400 mb-1">End Date</p>
                    <p class="font-bold">${rangeEnd ? formatDateShort(rangeEnd) : 'Select end date'}</p>
                </div>
            </div>

            <!-- Calendar Grid -->
            <div class="grid grid-cols-7 gap-2">
                <div class="text-center text-sm text-gray-400 font-semibold p-2">Sun</div>
                <div class="text-center text-sm text-gray-400 font-semibold p-2">Mon</div>
                <div class="text-center text-sm text-gray-400 font-semibold p-2">Tue</div>
                <div class="text-center text-sm text-gray-400 font-semibold p-2">Wed</div>
                <div class="text-center text-sm text-gray-400 font-semibold p-2">Thu</div>
                <div class="text-center text-sm text-gray-400 font-semibold p-2">Fri</div>
                <div class="text-center text-sm text-gray-400 font-semibold p-2">Sat</div>
    `;

    // Calculate calendar days
    const firstDay = new Date(selectedYear, selectedMonth, 1).getDay();
    const daysInMonth = new Date(selectedYear, selectedMonth + 1, 0).getDate();

    // Add empty cells for days before month starts
    for (let i = 0; i < firstDay; i++) {
        html += '<div></div>';
    }

    // Add day cells
    for (let day = 1; day <= daysInMonth; day++) {
        const date = new Date(selectedYear, selectedMonth, day);
        const isSelected = (rangeStart && date.getTime() === rangeStart.getTime()) ||
                          (rangeEnd && date.getTime() === rangeEnd.getTime());
        const isInRange = rangeStart && rangeEnd && date >= rangeStart && date <= rangeEnd;
        const isDisabled = rangePicking === 'end' && rangeStart && date < rangeStart;

        let btnClass = 'p-3 rounded-lg text-center transition-all';
        if (isDisabled) {
            btnClass += ' bg-gray-800 text-gray-600 cursor-not-allowed';
        } else if (isSelected) {
            btnClass += ' bg-indigo-500 text-white font-bold';
        } else if (isInRange) {
            btnClass += ' bg-indigo-500 bg-opacity-30 text-white';
        } else {
            btnClass += ' bg-gray-700 hover:bg-gray-600 text-white cursor-pointer';
        }

        html += `
            <button
                onclick="selectRangeDate(${selectedYear}, ${selectedMonth}, ${day})"
                ${isDisabled ? 'disabled' : ''}
                class="${btnClass}">
                ${day}
            </button>
        `;
    }

    html += '</div></div>';
    return html;
}

// Helper functions
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
    // Month is already in selectedYear
    closeDateRangeModal();
    updateDateRangeDisplay();
    loadDashboard();
}

function selectYear(year) {
    selectedYear = year;
    closeDateRangeModal();
    updateDateRangeDisplay();
    loadDashboard();
}

function setRangePicking(type) {
    rangePicking = type;
    renderCalendar();
}

function selectRangeDate(year, month, day) {
    const date = new Date(year, month, day);

    if (rangePicking === 'start') {
        rangeStart = date;
        rangeEnd = null; // Reset end date when start changes
        rangePicking = 'end'; // Auto-switch to end date picking
    } else {
        if (rangeStart && date >= rangeStart) {
            rangeEnd = date;
        }
    }

    renderCalendar();
}

function formatDateShort(date) {
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return `${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()}`;
}

function formatDateLong(date) {
    const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    return `${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()}`;
}

function updateDateRangeDisplay() {
    const textElement = document.getElementById('dateRangeText');
    if (!textElement) return; // Element not ready yet

    if (datePickerMode === 'month') {
        const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
        textElement.textContent = `${months[selectedMonth]} ${selectedYear}`;
    } else if (datePickerMode === 'year') {
        textElement.textContent = `${selectedYear}`;
    } else if (datePickerMode === 'range' && rangeStart && rangeEnd) {
        textElement.textContent = `${formatDateLong(rangeStart)} - ${formatDateLong(rangeEnd)}`;
    }
}

function applyDateRange() {
    closeDateRangeModal();
    updateDateRangeDisplay();
    loadDashboard();
}

// ==================== STAT DETAILS MODAL ====================

// Get tasks that have versions in a specific state
function getTasksWithVersionsInState(allTasks, targetState) {
    const tasksWithVersions = [];

    allTasks.forEach(task => {
        if (!task.versions || task.versions.length === 0) return;

        // Track version states for this task
        const versionStates = {};

        task.versions.forEach(version => {
            if (!version.lifecycle || version.lifecycle.length === 0) return;

            // Get the latest state for this version
            const latestEvent = version.lifecycle[version.lifecycle.length - 1];
            const folder = latestEvent.stage ? latestEvent.stage.toLowerCase() : '';

            // Debug logging
            let state = null;
            if (folder === 'pending' || folder === 'critique') state = 'pending';
            else if (folder === 'rejected' || folder === 'editing') state = 'rejected';
            else if (folder === 'returned') state = 'returned';
            else if (folder === 'submitted to sales' || folder === 'submitted') state = 'submitted';
            else if (folder === 'accepted' || folder === 'done') state = 'accepted';

            if (state) {
                versionStates[version.version] = state;
            }
        });

        // Only show versions in target state if task doesn't have an accepted version
        // (matching backend logic that ignores old versions once task is completed)
        const hasAcceptedVersion = Object.values(versionStates).includes('accepted');

        if (!hasAcceptedVersion) {
            // Check if any version is in the target state
            for (const [versionNum, state] of Object.entries(versionStates)) {
                if (state === targetState) {
                    // Add this task once for each version in the target state
                    tasksWithVersions.push({
                        ...task,
                        displayVersion: versionNum,
                        versionState: state
                    });
                }
            }
        }
    });

    return tasksWithVersions;
}

// Get tasks with rejection events grouped by task
function getTasksWithRejections(allTasks, rejectionType) {
    const tasksWithRejections = [];

    allTasks.forEach(task => {
        if (!task.versions || task.versions.length === 0) return;

        const rejectionEvents = [];

        // Collect all rejection events for this task
        task.versions.forEach(version => {
            if (!version.lifecycle || version.lifecycle.length === 0) return;

            version.lifecycle.forEach(event => {
                const stage = event.stage ? event.stage.toLowerCase() : '';

                // Check if this event matches the rejection type
                let isMatch = false;
                if (rejectionType === 'hod' && (stage === 'rejected' || stage === 'editing')) {
                    isMatch = true;
                } else if (rejectionType === 'hos' && stage === 'returned') {
                    isMatch = true;
                }

                if (isMatch) {
                    rejectionEvents.push({
                        version: version.version,
                        event: event,
                        stage: stage
                    });
                }
            });
        });

        // Only add this task if it has rejections
        if (rejectionEvents.length > 0) {
            tasksWithRejections.push({
                ...task,
                rejectionEvents: rejectionEvents,
                rejectionCount: rejectionEvents.length
            });
        }
    });

    return tasksWithRejections;
}

// Show details for a specific stat
function showStatDetails(statType) {
    if (!currentDashboardData) {
        console.error('No dashboard data available');
        return;
    }

    const modal = document.getElementById('detailsModal');
    const titleElement = document.getElementById('detailsModalTitle');
    const contentElement = document.getElementById('detailsModalContent');

    // Get all tasks from videographers data
    const allTasks = [];

    if (currentDashboardData.videographers) {
        Object.values(currentDashboardData.videographers).forEach(tasks => {
            if (Array.isArray(tasks)) {
                allTasks.push(...tasks);
            }
        });
    }

    const now = new Date();
    now.setHours(0, 0, 0, 0);

    let filteredTasks = [];
    let titleText = '';

    switch (statType) {
        case 'total_created':
            filteredTasks = allTasks;
            titleText = 'Total Tasks Created';
            break;

        case 'total_assigned':
            filteredTasks = allTasks.filter(task => task.status !== 'Not assigned yet');
            titleText = 'Total Tasks Assigned';
            break;

        case 'total_started':
            filteredTasks = allTasks.filter(task => {
                if (task.filming_deadline && task.filming_deadline !== 'NA') {
                    const filmingDate = parseDateFromBackend(task.filming_deadline);
                    return filmingDate && filmingDate <= now;
                }
                return false;
            });
            titleText = 'Total Tasks Started (Filming Date Passed)';
            break;

        case 'total_late':
            filteredTasks = allTasks.filter(task => {
                if (task.submission_date && task.submission_date !== 'NA') {
                    const submissionDate = parseDateFromBackend(task.submission_date);
                    return submissionDate && submissionDate <= now && task.status !== 'Accepted' && task.status !== 'Done';
                }
                return false;
            });
            titleText = 'Total Late Tasks';
            break;

        case 'completed':
            filteredTasks = allTasks.filter(task => task.status === 'Accepted' || task.status === 'Done');
            titleText = 'Completed Tasks';
            break;

        case 'pending_hod':
            // Show all versions in pending state
            filteredTasks = getTasksWithVersionsInState(allTasks, 'pending');
            titleText = `Pending HOD Review (${filteredTasks.length} versions)`;
            break;

        case 'pending_hos':
            // Show all versions in submitted state
            filteredTasks = getTasksWithVersionsInState(allTasks, 'submitted');
            titleText = `Pending HOS Review (${filteredTasks.length} versions)`;
            break;

        case 'rejected_hod':
            // Show tasks with rejection events by HOD
            filteredTasks = getTasksWithRejections(allTasks, 'hod');
            const totalHODRejections = filteredTasks.reduce((sum, task) => sum + task.rejectionCount, 0);
            titleText = `Rejected by HOD (${totalHODRejections} rejections across ${filteredTasks.length} tasks)`;
            break;

        case 'rejected_hos':
            // Show tasks with rejection events by HOS
            filteredTasks = getTasksWithRejections(allTasks, 'hos');
            const totalHOSRejections = filteredTasks.reduce((sum, task) => sum + task.rejectionCount, 0);
            titleText = `Rejected by HOS (${totalHOSRejections} rejections across ${filteredTasks.length} tasks)`;
            break;

        case 'upload_ratio':
            // Show completed tasks with their version history
            filteredTasks = allTasks.filter(task => task.status === 'Accepted' || task.status === 'Done');
            const totalVersions = filteredTasks.reduce((sum, task) => sum + (task.versions ? task.versions.length : 0), 0);
            const avgVersions = filteredTasks.length > 0 ? (totalVersions / filteredTasks.length).toFixed(2) : '0';
            titleText = `Upload to Completion Ratio: ${avgVersions} avg versions per task (${totalVersions} versions across ${filteredTasks.length} completed tasks)`;
            break;

        case 'acceptance_rate':
            // Show all versions with their acceptance/rejection status and distribution
            const allVersionsWithStatus = [];
            const acceptanceRejectionClasses = {};
            let totalAcceptanceRejections = 0;

            allTasks.forEach(task => {
                if (!task.versions) return;
                task.versions.forEach(version => {
                    if (!version.lifecycle || version.lifecycle.length === 0) return;
                    const latestEvent = version.lifecycle[version.lifecycle.length - 1];
                    const latestStage = latestEvent.stage ? latestEvent.stage.toLowerCase() : '';

                    // Collect rejection events for distribution
                    version.lifecycle.forEach(event => {
                        const stage = event.stage ? event.stage.toLowerCase() : '';
                        if (stage === 'rejected' || stage === 'editing' || stage === 'returned') {
                            const rejClass = event.rejection_class || 'Unclassified';
                            acceptanceRejectionClasses[rejClass] = (acceptanceRejectionClasses[rejClass] || 0) + 1;
                            totalAcceptanceRejections++;
                        }
                    });

                    allVersionsWithStatus.push({
                        task: task.task_number || task['Task Number'],
                        version: version.version_number || version.version,
                        status: latestStage,
                        lifecycle: version.lifecycle
                    });
                });
            });

            const acceptedVersions = allVersionsWithStatus.filter(v => v.status === 'accepted' || v.status === 'done').length;
            const rejectedVersions = allVersionsWithStatus.filter(v => v.status === 'rejected' || v.status === 'editing' || v.status === 'returned').length;
            const acceptancePercent = allVersionsWithStatus.length > 0 ? ((acceptedVersions / allVersionsWithStatus.length) * 100).toFixed(1) : 0;
            const rejectionPercent = allVersionsWithStatus.length > 0 ? ((rejectedVersions / allVersionsWithStatus.length) * 100).toFixed(1) : 0;

            // Create rejection distribution HTML
            let rejectionDistHTML = '<div class="mt-6"><h4 class="text-lg font-semibold mb-4 text-gray-200">Rejection Class Distribution</h4>';
            if (totalAcceptanceRejections > 0) {
                const sortedAcceptanceRejections = Object.entries(acceptanceRejectionClasses)
                    .map(([className, count]) => ({
                        className,
                        count,
                        percentage: ((count / totalAcceptanceRejections) * 100).toFixed(1)
                    }))
                    .sort((a, b) => b.count - a.count);

                const colors = ['bg-red-500', 'bg-orange-500', 'bg-yellow-500', 'bg-blue-500', 'bg-purple-500', 'bg-pink-500'];
                rejectionDistHTML += '<div class="space-y-3">';
                sortedAcceptanceRejections.forEach((rej, idx) => {
                    const color = colors[idx % colors.length];
                    rejectionDistHTML += `
                        <div class="glass-card p-4 rounded-lg">
                            <div class="flex items-center justify-between mb-2">
                                <div class="flex items-center space-x-3">
                                    <div class="w-3 h-3 rounded-full ${color}"></div>
                                    <span class="font-semibold text-white">${rej.className}</span>
                                </div>
                                <div class="text-right">
                                    <span class="text-xl font-bold text-white">${rej.count}</span>
                                    <span class="text-sm text-gray-400 ml-2">(${rej.percentage}%)</span>
                                </div>
                            </div>
                            <div class="w-full bg-gray-700 rounded-full h-2">
                                <div class="${color} h-full rounded-full" style="width: ${rej.percentage}%"></div>
                            </div>
                        </div>
                    `;
                });
                rejectionDistHTML += '</div>';
            } else {
                rejectionDistHTML += '<p class="text-gray-400 text-center py-4">No rejections recorded</p>';
            }
            rejectionDistHTML += '</div>';

            titleText = `Acceptance Rate Details`;
            document.getElementById('detailsModalContent').innerHTML = `
                <div class="space-y-6">
                    <div class="grid grid-cols-2 gap-4">
                        <div class="glass-card p-6 rounded-lg text-center">
                            <p class="text-4xl font-bold text-emerald-400">${acceptancePercent}%</p>
                            <p class="text-sm text-gray-400 mt-2">Acceptance Rate</p>
                        </div>
                        <div class="glass-card p-6 rounded-lg text-center">
                            <p class="text-4xl font-bold text-red-400">${rejectionPercent}%</p>
                            <p class="text-sm text-gray-400 mt-2">Rejection Rate</p>
                        </div>
                    </div>
                    ${rejectionDistHTML}
                </div>
            `;

            document.getElementById('detailsModalTitle').textContent = titleText;
            document.getElementById('detailsModal').classList.remove('hidden');
            return; // Skip the default rendering

        default:
            console.error('Unknown stat type:', statType);
            return;
    }

    // Sort tasks: completed at bottom, uncompleted by closest submission date
    filteredTasks.sort((a, b) => {
        const aCompleted = a.status === 'Accepted' || a.status === 'Done';
        const bCompleted = b.status === 'Accepted' || b.status === 'Done';

        // Completed tasks go to the bottom
        if (aCompleted && !bCompleted) return 1;
        if (!aCompleted && bCompleted) return -1;

        // Both completed: sort by newest to oldest (latest submission first)
        if (aCompleted && bCompleted) {
            const aSubmission = parseDateFromBackend(a.submission_date);
            const bSubmission = parseDateFromBackend(b.submission_date);

            if (!aSubmission && !bSubmission) return 0;
            if (!aSubmission) return 1; // Tasks without submission date go to end
            if (!bSubmission) return -1;

            // Newest submission date first (reverse order)
            return bSubmission - aSubmission;
        }

        // Both uncompleted: sort by submission date (closest first)
        const aSubmission = parseDateFromBackend(a.submission_date);
        const bSubmission = parseDateFromBackend(b.submission_date);

        if (!aSubmission && !bSubmission) return 0;
        if (!aSubmission) return 1; // Tasks without submission date go to end
        if (!bSubmission) return -1;

        // Closest submission date first
        return aSubmission - bSubmission;
    });

    titleElement.textContent = titleText;

    // Use different rendering based on modal type
    if (statType === 'rejected_hod' || statType === 'rejected_hos') {
        contentElement.innerHTML = renderTasksWithRejections(filteredTasks);
    } else if (statType === 'upload_ratio') {
        contentElement.innerHTML = renderTasksWithVersions(filteredTasks);
    } else {
        contentElement.innerHTML = renderTaskList(filteredTasks);
    }

    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

// Show version details
function showVersionDetails() {
    if (!currentDashboardData) {
        console.error('No dashboard data available');
        return;
    }

    const modal = document.getElementById('detailsModal');
    const titleElement = document.getElementById('detailsModalTitle');
    const contentElement = document.getElementById('detailsModalContent');

    // Get all tasks from videographers data
    const allTasks = [];
    Object.values(currentDashboardData.videographers || {}).forEach(tasks => {
        allTasks.push(...tasks);
    });

    // Filter tasks that have versions
    const tasksWithVersions = allTasks.filter(task => task.versions && task.versions.length > 0);

    // Count total versions
    const totalVersions = tasksWithVersions.reduce((sum, task) => sum + task.versions.length, 0);

    // Sort tasks by submission date (same logic as other modals)
    tasksWithVersions.sort((a, b) => {
        const aCompleted = a.status === 'Accepted' || a.status === 'Done';
        const bCompleted = b.status === 'Accepted' || b.status === 'Done';

        if (aCompleted && !bCompleted) return 1;
        if (!aCompleted && bCompleted) return -1;

        if (aCompleted && bCompleted) {
            const aSubmission = parseDateFromBackend(a.submission_date);
            const bSubmission = parseDateFromBackend(b.submission_date);
            if (!aSubmission && !bSubmission) return 0;
            if (!aSubmission) return 1;
            if (!bSubmission) return -1;
            return bSubmission - aSubmission;
        }

        const aSubmission = parseDateFromBackend(a.submission_date);
        const bSubmission = parseDateFromBackend(b.submission_date);
        if (!aSubmission && !bSubmission) return 0;
        if (!aSubmission) return 1;
        if (!bSubmission) return -1;
        return aSubmission - bSubmission;
    });

    titleElement.textContent = `Total Versions Uploaded (${totalVersions})`;
    contentElement.innerHTML = renderTasksWithVersions(tasksWithVersions);

    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

// Toggle version history visibility
function toggleVersionHistory(taskNumber) {
    const versionContainer = document.getElementById(`versions-${taskNumber}`);
    const icon = document.getElementById(`icon-${taskNumber}`);

    if (versionContainer.classList.contains('hidden')) {
        versionContainer.classList.remove('hidden');
        icon.classList.remove('fa-chevron-down');
        icon.classList.add('fa-chevron-up');
    } else {
        versionContainer.classList.add('hidden');
        icon.classList.remove('fa-chevron-up');
        icon.classList.add('fa-chevron-down');
    }
}

// Map status to human-readable text
function getHumanReadableStatus(task) {
    const status = task.status;
    const videographer = task.videographer;

    const statusMap = {
        'Critique': 'Uploaded And Pending HOD Approval',
        'Editing': 'Rejected By HOD And Being Amended',
        'Submitted to Sales': 'Accepted by HOD And Pending HOS Approval',
        'Returned': 'Rejected By HOS And Being Amended',
        'Accepted': 'Completed',
        'Done': 'Completed'
    };

    // If status is in the map, use it
    if (statusMap[status]) {
        return statusMap[status];
    }

    // Otherwise check if it's assigned but not uploaded
    if (videographer && videographer !== 'NA' && videographer !== '') {
        return `Assigned to ${videographer} But Yet To Be Uploaded`;
    }

    return status || 'Unknown Status';
}

// Check if task is late
function isTaskLate(task) {
    if (!task.submission_date || task.submission_date === 'NA') return false;
    if (task.status === 'Accepted' || task.status === 'Done') return false;

    const now = new Date();
    now.setHours(0, 0, 0, 0);
    const submissionDate = parseDateFromBackend(task.submission_date);

    return submissionDate && submissionDate < now;
}

// Render task list
function renderTaskList(tasks) {
    if (!tasks || tasks.length === 0) {
        return '<p class="text-gray-400 text-center py-8">No tasks found</p>';
    }

    return tasks.map(task => {
        const humanStatus = getHumanReadableStatus(task);
        const isLate = isTaskLate(task);
        const versionDisplay = task.displayVersion ? ` - Version ${task.displayVersion}` : '';

        return `
        <div class="bg-white bg-opacity-5 rounded-lg p-4 mb-4 hover:bg-opacity-10 transition-all">
            <div class="flex items-start justify-between">
                <div class="flex-1">
                    <h5 class="text-lg font-semibold text-white mb-1">
                        <i class="fas fa-tasks mr-2 text-indigo-400"></i>
                        Task #${task.task_number}${versionDisplay}
                        ${isLate ? '<span class="ml-2 px-2 py-1 bg-red-500 text-white text-xs font-bold rounded">LATE</span>' : ''}
                    </h5>
                    <p class="text-gray-300 mb-2">${task.brand || 'No brand'}</p>
                    <div class="flex flex-wrap gap-3 text-sm text-gray-400">
                        ${task.videographer ? `<span><i class="fas fa-user mr-1"></i>${task.videographer}</span>` : ''}
                        ${task.filming_deadline ? `<span><i class="fas fa-calendar mr-1"></i>Filming: ${task.filming_deadline}</span>` : ''}
                        ${task.submission_date && task.submission_date !== 'NA' ? `<span><i class="fas fa-calendar-check mr-1"></i>Submission: ${task.submission_date}</span>` : ''}
                    </div>
                </div>
                <span class="px-4 py-2 rounded-full text-sm font-semibold ${getStatusBadgeClass(task.status)}">
                    ${humanStatus}
                </span>
            </div>
        </div>
    `;
    }).join('');
}

// Render tasks with collapsible version histories
function renderTasksWithVersions(tasks) {
    if (!tasks || tasks.length === 0) {
        return '<p class="text-gray-400 text-center py-8">No tasks with versions found</p>';
    }

    return tasks.map(task => {
        const humanStatus = getHumanReadableStatus(task);
        const isLate = isTaskLate(task);
        const versionCount = task.versions ? task.versions.length : 0;

        return `
        <div class="bg-white bg-opacity-5 rounded-lg p-4 mb-4 transition-all">
            <div class="flex items-start justify-between cursor-pointer hover:bg-opacity-10" onclick="toggleVersionHistory(${task.task_number})">
                <div class="flex-1">
                    <h5 class="text-lg font-semibold text-white mb-1">
                        <i id="icon-${task.task_number}" class="fas fa-chevron-down mr-2 text-indigo-400"></i>
                        Task #${task.task_number}
                        ${isLate ? '<span class="ml-2 px-2 py-1 bg-red-500 text-white text-xs font-bold rounded">LATE</span>' : ''}
                        <span class="ml-2 px-2 py-1 bg-purple-500 text-white text-xs font-bold rounded">${versionCount} Version${versionCount !== 1 ? 's' : ''}</span>
                    </h5>
                    <p class="text-gray-300 mb-2">${task.brand || 'No brand'}</p>
                    <div class="flex flex-wrap gap-3 text-sm text-gray-400">
                        ${task.videographer ? `<span><i class="fas fa-user mr-1"></i>${task.videographer}</span>` : ''}
                        ${task.filming_deadline ? `<span><i class="fas fa-calendar mr-1"></i>Filming: ${task.filming_deadline}</span>` : ''}
                        ${task.submission_date && task.submission_date !== 'NA' ? `<span><i class="fas fa-calendar-check mr-1"></i>Submission: ${task.submission_date}</span>` : ''}
                    </div>
                </div>
                <span class="px-4 py-2 rounded-full text-sm font-semibold ${getStatusBadgeClass(task.status)}">
                    ${humanStatus}
                </span>
            </div>

            <!-- Version History (collapsed by default) -->
            <div id="versions-${task.task_number}" class="hidden mt-4 pl-4 border-l-2 border-indigo-500">
                ${[...task.versions].reverse().map(version => `
                    <div class="bg-white bg-opacity-5 rounded-lg p-4 mb-3">
                        <h6 class="font-bold text-lg text-purple-300 mb-3">
                            <i class="fas fa-code-branch mr-2"></i>
                            Version ${version.version}
                        </h6>
                        <div class="space-y-2">
                            ${version.lifecycle.map(event => {
                                const stageName = formatStageName(event.stage);
                                const isRejection = event.stage && (event.stage.toLowerCase() === 'editing' || event.stage.toLowerCase() === 'rejected' || event.stage.toLowerCase() === 'returned');
                                const displayName = isRejection && event.rejection_class
                                    ? `${stageName} - ${event.rejection_class}`
                                    : stageName;

                                return `
                                <div class="flex items-start space-x-3">
                                    <div class="w-3 h-3 rounded-full ${getStageColor(event.stage)} mt-1"></div>
                                    <div class="flex-1">
                                        <div class="flex items-center justify-between">
                                            <span class="font-semibold ${getStageTextColor(event.stage)}">
                                                ${displayName}
                                            </span>
                                            <span class="text-xs text-gray-500">${event.at || 'No timestamp'}</span>
                                        </div>
                                        ${event.rejection_comments ? `
                                            <p class="text-sm text-red-300 mt-1">
                                                <i class="fas fa-comment-dots mr-1"></i>${event.rejection_comments}
                                            </p>
                                        ` : ''}
                                    </div>
                                </div>
                            `}).join('')}
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
    }).join('');
}

// Render tasks with rejection events (collapsible)
function renderTasksWithRejections(tasks) {
    if (!tasks || tasks.length === 0) {
        return '<p class="text-gray-400 text-center py-8">No rejections found</p>';
    }

    return tasks.map(task => {
        const humanStatus = getHumanReadableStatus(task);
        const isLate = isTaskLate(task);
        const rejectionCount = task.rejectionCount || 0;

        return `
        <div class="bg-white bg-opacity-5 rounded-lg p-4 mb-4 transition-all">
            <div class="flex items-start justify-between cursor-pointer hover:bg-opacity-10" onclick="toggleRejectionHistory(${task.task_number})">
                <div class="flex-1">
                    <h5 class="text-lg font-semibold text-white mb-1">
                        <i id="rejection-icon-${task.task_number}" class="fas fa-chevron-down mr-2 text-red-400"></i>
                        Task #${task.task_number}
                        ${isLate ? '<span class="ml-2 px-2 py-1 bg-red-500 text-white text-xs font-bold rounded">LATE</span>' : ''}
                        <span class="ml-2 px-2 py-1 bg-red-500 text-white text-xs font-bold rounded">${rejectionCount} Rejection${rejectionCount !== 1 ? 's' : ''}</span>
                    </h5>
                    <p class="text-gray-300 mb-2">${task.brand || 'No brand'}</p>
                    <div class="flex flex-wrap gap-3 text-sm text-gray-400">
                        ${task.videographer ? `<span><i class="fas fa-user mr-1"></i>${task.videographer}</span>` : ''}
                        ${task.filming_deadline ? `<span><i class="fas fa-calendar mr-1"></i>Filming: ${task.filming_deadline}</span>` : ''}
                        ${task.submission_date && task.submission_date !== 'NA' ? `<span><i class="fas fa-calendar-check mr-1"></i>Submission: ${task.submission_date}</span>` : ''}
                    </div>
                </div>
                <span class="px-4 py-2 rounded-full text-sm font-semibold ${getStatusBadgeClass(task.status)}">
                    ${humanStatus}
                </span>
            </div>

            <!-- Rejection History (collapsed by default) -->
            <div id="rejections-${task.task_number}" class="hidden mt-4 pl-4 border-l-2 border-red-500">
                ${task.rejectionEvents.map((rejection, index) => `
                    <div class="bg-red-900 bg-opacity-20 rounded-lg p-4 mb-3 border-l-4 border-red-500">
                        <div class="flex items-center justify-between mb-2">
                            <h6 class="font-bold text-lg text-red-300">
                                <i class="fas fa-times-circle mr-2"></i>
                                Rejection #${index + 1} - Version ${rejection.version}
                            </h6>
                            <span class="text-xs text-gray-400">${rejection.event.at || 'No timestamp'}</span>
                        </div>
                        ${rejection.event.rejection_class ? `
                            <div class="mb-2">
                                <span class="inline-block px-3 py-1 bg-red-600 text-white text-sm font-semibold rounded">
                                    ${rejection.event.rejection_class}
                                </span>
                            </div>
                        ` : ''}
                        ${rejection.event.rejection_comments ? `
                            <p class="text-sm text-gray-300 mt-2">
                                <i class="fas fa-comment-dots mr-2"></i>${rejection.event.rejection_comments}
                            </p>
                        ` : ''}
                        ${rejection.event.rejected_by ? `
                            <p class="text-xs text-gray-400 mt-2">
                                <i class="fas fa-user mr-1"></i>Rejected by: ${rejection.event.rejected_by}
                            </p>
                        ` : ''}
                    </div>
                `).join('')}
            </div>
        </div>
    `;
    }).join('');
}

// Toggle rejection history visibility
function toggleRejectionHistory(taskNumber) {
    const rejectionContainer = document.getElementById(`rejections-${taskNumber}`);
    const icon = document.getElementById(`rejection-icon-${taskNumber}`);

    if (rejectionContainer.classList.contains('hidden')) {
        rejectionContainer.classList.remove('hidden');
        icon.classList.remove('fa-chevron-down');
        icon.classList.add('fa-chevron-up');
    } else {
        rejectionContainer.classList.add('hidden');
        icon.classList.remove('fa-chevron-up');
        icon.classList.add('fa-chevron-down');
    }
}

// Render version list
function renderVersionList(versions) {
    if (!versions || versions.length === 0) {
        return '<p class="text-gray-400 text-center py-8">No versions found</p>';
    }

    return versions.map(versionData => {
        const latestStage = versionData.lifecycle && versionData.lifecycle.length > 0
            ? versionData.lifecycle[versionData.lifecycle.length - 1].stage
            : 'Unknown';

        return `
            <div class="bg-white bg-opacity-5 rounded-lg p-4 mb-4 hover:bg-opacity-10 transition-all">
                <div class="flex items-start justify-between mb-3">
                    <div class="flex-1">
                        <h5 class="text-lg font-semibold text-white mb-1">
                            <i class="fas fa-code-branch mr-2 text-purple-400"></i>
                            Task #${versionData.task_number} - Version ${versionData.version}
                        </h5>
                        <p class="text-gray-300 mb-2">${versionData.brand || 'No brand'}</p>
                        <div class="flex flex-wrap gap-3 text-sm text-gray-400">
                            ${versionData.videographer ? `<span><i class="fas fa-user mr-1"></i>${versionData.videographer}</span>` : ''}
                        </div>
                    </div>
                    <span class="px-4 py-2 rounded-full text-sm font-semibold ${getStatusBadgeClass(latestStage)}">
                        ${formatStageName(latestStage)}
                    </span>
                </div>

                <!-- Lifecycle Timeline -->
                <div class="mt-3 space-y-2 pl-4 border-l-2 border-gray-600">
                    ${versionData.lifecycle.map(event => {
                        const stageName = formatStageName(event.stage);
                        const isRejection = event.stage && (event.stage.toLowerCase() === 'editing' || event.stage.toLowerCase() === 'rejected' || event.stage.toLowerCase() === 'returned');
                        const displayName = isRejection && event.rejection_class
                            ? `${stageName} - ${event.rejection_class}`
                            : stageName;

                        return `
                        <div class="pb-2">
                            <div class="flex items-center justify-between">
                                <span class="font-medium ${getStageTextColor(event.stage)}">
                                    <i class="fas fa-circle text-xs mr-2"></i>
                                    ${displayName}
                                </span>
                                <span class="text-xs text-gray-500">${event.at || 'No timestamp'}</span>
                            </div>
                            ${event.rejection_comments ? `
                                <p class="text-sm text-red-300 mt-1 ml-5">
                                    <i class="fas fa-comment-dots mr-1"></i>${event.rejection_comments}
                                </p>
                            ` : ''}
                        </div>
                    `}).join('')}
                </div>
            </div>
        `;
    }).join('');
}

// Get pending reviews (versions waiting for HOD review)
function getPendingReviews(allTasks) {
    // Reuse the existing function to get tasks with pending versions
    const pendingTasks = getTasksWithVersionsInState(allTasks, 'pending');

    const now = new Date();
    const pendingReviews = [];

    pendingTasks.forEach(taskData => {
        const task = taskData;
        const versionNum = taskData.displayVersion;

        // Find the version object
        const version = task.versions.find(v => v.version == versionNum);
        if (!version || !version.lifecycle) return;

        // Find the FIRST time this version entered pending/critique state
        let uploadTime = null;
        for (const event of version.lifecycle) {
            const eventStage = event.stage ? event.stage.toLowerCase() : '';
            if (eventStage === 'pending' || eventStage === 'critique') {
                // The timestamp field is called "at" not "timestamp"
                uploadTime = event.at ? parseDateFromBackend(event.at) : null;
                break; // Use the first pending/critique event
            }
        }

        const waitingHours = uploadTime ? Math.round((now - uploadTime) / (1000 * 60 * 60)) : 0;

        pendingReviews.push({
            task: task,
            version: parseInt(versionNum),
            uploadTime: uploadTime,
            waitingHours: waitingHours
        });
    });

    return {
        count: pendingReviews.length,
        reviews: pendingReviews
    };
}

// Get reviewer response time data
function getResponseTimeData(allTasks) {
    const responseTimes = [];

    allTasks.forEach(task => {
        if (!task.versions || task.versions.length === 0) return;

        task.versions.forEach(version => {
            if (!version.lifecycle || version.lifecycle.length < 2) return;

            // Find the FIRST upload time (first pending/critique event)
            let uploadTime = null;
            for (const event of version.lifecycle) {
                const stage = event.stage ? event.stage.toLowerCase() : '';
                if (stage === 'pending' || stage === 'critique') {
                    uploadTime = event.at ? parseDateFromBackend(event.at) : null;
                    break; // Use the first pending/critique event as upload time
                }
            }

            // Find the FIRST reviewer decision (first rejected/accepted event)
            let reviewTime = null;
            let reviewDecision = null;
            let reviewEvent = null;
            for (const event of version.lifecycle) {
                const stage = event.stage ? event.stage.toLowerCase() : '';
                if (stage === 'rejected' || stage === 'editing' || stage === 'accepted' ||
                    stage === 'submitted' || stage === 'submitted to sales') {
                    reviewTime = event.at ? parseDateFromBackend(event.at) : null;
                    reviewDecision = stage;
                    reviewEvent = event;
                    break; // Use the first reviewer decision
                }
            }

            // Only add if we have both upload and review times
            if (uploadTime && reviewTime && reviewDecision) {
                const responseHours = Math.round((reviewTime - uploadTime) / (1000 * 60 * 60));
                const decision = (reviewDecision === 'accepted' || reviewDecision === 'submitted' || reviewDecision === 'submitted to sales') ? 'Accepted' : 'Rejected';

                responseTimes.push({
                    task: task,
                    version: version.version,
                    uploadTime: uploadTime,
                    reviewTime: reviewTime,
                    responseHours: responseHours,
                    decision: decision,
                    rejectionClass: reviewEvent.rejection_class || null,
                    comments: reviewEvent.rejection_comments || null
                });
            }
        });
    });

    return responseTimes;
}

// Get videos handled data (with correctness vs HOS)
function getVideosHandledData(allTasks) {
    const handledVideos = [];

    allTasks.forEach(task => {
        if (!task.versions || task.versions.length === 0) return;

        task.versions.forEach(version => {
            if (!version.lifecycle || version.lifecycle.length === 0) return;

            // Check if HOD reviewed this version (accepted or rejected it)
            let hodDecision = null;
            let hosDecision = null;
            let hodEvent = null;
            let hosEvent = null;

            for (let i = 0; i < version.lifecycle.length; i++) {
                const event = version.lifecycle[i];
                const stage = event.stage ? event.stage.toLowerCase() : '';

                // HOD accepted (moved to submitted/submitted to sales)
                if (stage === 'submitted' || stage === 'submitted to sales' || stage === 'accepted') {
                    if (!hodDecision) {
                        hodDecision = 'Accepted';
                        hodEvent = event;
                    }
                }

                // HOD rejected (moved to rejected/editing)
                if (stage === 'rejected' || stage === 'editing') {
                    if (!hodDecision) {
                        hodDecision = 'Rejected';
                        hodEvent = event;
                    }
                }

                // HOS accepted
                if (stage === 'accepted') {
                    hosDecision = 'Accepted';
                    hosEvent = event;
                }

                // HOS returned
                if (stage === 'returned') {
                    hosDecision = 'Returned';
                    hosEvent = event;
                }
            }

            // Only include versions where HOD made a decision
            if (hodDecision) {
                let correctness = 'Pending HOS Review';

                // If HOD rejected, it never reaches HOS
                if (hodDecision === 'Rejected') {
                    correctness = 'N/A';
                    hosDecision = null; // Don't show HOS decision for rejected videos
                } else if (hodDecision === 'Accepted') {
                    // HOD accepted, so check HOS decision
                    if (hosDecision === 'Accepted') {
                        correctness = 'Correct';
                    } else if (hosDecision === 'Returned') {
                        correctness = 'Incorrect';
                    } else {
                        // No HOS decision yet
                        correctness = 'Pending HOS Review';
                    }
                }

                handledVideos.push({
                    task: task,
                    version: version.version,
                    hodDecision: hodDecision,
                    hosDecision: hosDecision,
                    correctness: correctness,
                    hodEvent: hodEvent,
                    hosEvent: hosEvent
                });
            }
        });
    });

    return handledVideos;
}

// Get accepted tasks (tasks that HOS accepted)
function getAcceptedTasks(allTasks) {
    const acceptedTasks = [];

    allTasks.forEach(task => {
        if (task.status === 'Accepted' || task.status === 'Done') {
            // Find the accepted version
            if (task.versions && task.versions.length > 0) {
                for (const version of task.versions) {
                    if (version.lifecycle && version.lifecycle.length > 0) {
                        const hasAccepted = version.lifecycle.some(event => {
                            const stage = event.stage ? event.stage.toLowerCase() : '';
                            return stage === 'accepted';
                        });

                        if (hasAccepted) {
                            acceptedTasks.push({
                                task: task,
                                acceptedVersion: version.version
                            });
                            break; // Only need one accepted version per task
                        }
                    }
                }
            }
        }
    });

    return acceptedTasks;
}

// Show reviewer details modal
function showReviewerDetails(type) {
    if (!currentDashboardData) return;

    const allTasks = [];
    Object.values(currentDashboardData.videographers || {}).forEach(tasks => {
        allTasks.push(...tasks);
    });

    const modal = document.getElementById('detailsModal');
    const titleElement = document.getElementById('detailsModalTitle');
    const contentElement = document.getElementById('detailsModalContent');

    let titleText = '';
    let contentHTML = '';

    if (type === 'response_time') {
        const responseTimes = getResponseTimeData(allTasks);
        titleText = `Response Time Details (${responseTimes.length} reviews)`;
        contentHTML = renderResponseTimeDetails(responseTimes);
    } else if (type === 'videos_handled') {
        const handledVideos = getVideosHandledData(allTasks);
        titleText = `Videos Handled Details (${handledVideos.length} videos)`;
        contentHTML = renderVideosHandledDetails(handledVideos);
    } else if (type === 'accepted') {
        const acceptedTasks = getAcceptedTasks(allTasks);
        titleText = `Accepted Tasks (${acceptedTasks.length} tasks)`;
        contentHTML = renderAcceptedTasksDetails(acceptedTasks);
    } else if (type === 'pending_reviews') {
        const pendingReviews = getPendingReviews(allTasks);
        titleText = `Pending Reviews (${pendingReviews.count} versions awaiting review)`;
        contentHTML = renderPendingReviewsDetails(pendingReviews.reviews);
    } else if (type === 'success_rate') {
        // Show failure distribution for videos HOD accepted but HOS returned
        const failedVideos = [];
        const failureClasses = {};
        let totalFailures = 0;

        allTasks.forEach(task => {
            if (!task.versions) return;
            task.versions.forEach(version => {
                if (!version.lifecycle || version.lifecycle.length === 0) return;

                // Check if HOD accepted this version
                let hodAccepted = false;
                let hosReturned = false;
                let returnEvent = null;

                for (const event of version.lifecycle) {
                    const stage = event.stage ? event.stage.toLowerCase() : '';
                    if (stage === 'submitted' || stage === 'submitted to sales') {
                        hodAccepted = true;
                    }
                    if (stage === 'returned') {
                        hosReturned = true;
                        returnEvent = event;
                    }
                }

                // If HOD accepted but HOS returned, this is a failure
                if (hodAccepted && hosReturned && returnEvent) {
                    const rejClass = returnEvent.rejection_class || 'Unclassified';
                    failureClasses[rejClass] = (failureClasses[rejClass] || 0) + 1;
                    totalFailures++;

                    failedVideos.push({
                        task,
                        version: version.version,
                        returnEvent
                    });
                }
            });
        });

        // Create failure distribution HTML
        let failureDistHTML = '<div class="mt-6"><h4 class="text-lg font-semibold mb-4 text-gray-200">Failure Distribution by Rejection Class</h4>';
        if (totalFailures > 0) {
            const sortedFailures = Object.entries(failureClasses)
                .map(([className, count]) => ({
                    className,
                    count,
                    percentage: ((count / totalFailures) * 100).toFixed(1)
                }))
                .sort((a, b) => b.count - a.count);

            const colors = ['bg-red-500', 'bg-orange-500', 'bg-yellow-500', 'bg-blue-500', 'bg-purple-500', 'bg-pink-500'];
            failureDistHTML += '<div class="space-y-3">';
            sortedFailures.forEach((failure, idx) => {
                const color = colors[idx % colors.length];
                failureDistHTML += `
                    <div class="glass-card p-4 rounded-lg">
                        <div class="flex items-center justify-between mb-2">
                            <div class="flex items-center space-x-3">
                                <div class="w-3 h-3 rounded-full ${color}"></div>
                                <span class="font-semibold text-white">${failure.className}</span>
                            </div>
                            <div class="text-right">
                                <span class="text-xl font-bold text-white">${failure.count}</span>
                                <span class="text-sm text-gray-400 ml-2">(${failure.percentage}%)</span>
                            </div>
                        </div>
                        <div class="w-full bg-gray-700 rounded-full h-2">
                            <div class="${color} h-full rounded-full" style="width: ${failure.percentage}%"></div>
                        </div>
                    </div>
                `;
            });
            failureDistHTML += '</div>';
        } else {
            failureDistHTML += '<p class="text-gray-400 text-center py-4">No failures recorded - perfect track record!</p>';
        }
        failureDistHTML += '</div>';

        // Calculate success rate and failure rate
        const handledVideos = getVideosHandledData(allTasks);
        const hodAcceptedCount = handledVideos.filter(v => v.hodDecision === 'Accepted').length;
        const successfulCount = handledVideos.filter(v => v.correctness === 'Correct').length;
        const successRate = hodAcceptedCount > 0 ? ((successfulCount / hodAcceptedCount) * 100).toFixed(1) : 0;
        const failureRate = hodAcceptedCount > 0 ? ((totalFailures / hodAcceptedCount) * 100).toFixed(1) : 0;

        titleText = `Success Rate Details`;
        contentHTML = `
            <div class="space-y-6">
                <div class="grid grid-cols-2 gap-4">
                    <div class="glass-card p-6 rounded-lg text-center">
                        <p class="text-4xl font-bold text-emerald-400">${successRate}%</p>
                        <p class="text-sm text-gray-400 mt-2">Success Rate</p>
                    </div>
                    <div class="glass-card p-6 rounded-lg text-center">
                        <p class="text-4xl font-bold text-red-400">${failureRate}%</p>
                        <p class="text-sm text-gray-400 mt-2">Failure Rate</p>
                    </div>
                </div>
                ${failureDistHTML}
            </div>
        `;
    }

    titleElement.textContent = titleText;
    contentElement.innerHTML = contentHTML;

    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

// Render response time details
function renderResponseTimeDetails(responseTimes) {
    if (responseTimes.length === 0) {
        return '<p class="text-gray-400 text-center py-8">No response data available.</p>';
    }

    // Group by task
    const taskGroups = {};
    responseTimes.forEach(rt => {
        const taskNum = rt.task.task_number;
        if (!taskGroups[taskNum]) {
            taskGroups[taskNum] = {
                task: rt.task,
                responses: []
            };
        }
        taskGroups[taskNum].responses.push(rt);
    });

    return Object.values(taskGroups).map(group => {
        const avgResponse = group.responses.reduce((sum, r) => sum + r.responseHours, 0) / group.responses.length;

        return `
        <div class="bg-white bg-opacity-5 rounded-lg p-4 mb-4 transition-all">
            <div class="flex items-start justify-between cursor-pointer hover:bg-opacity-10" onclick="toggleResponseHistory(${group.task.task_number})">
                <h5 class="text-lg font-semibold text-white mb-1">
                    <i id="response-icon-${group.task.task_number}" class="fas fa-chevron-down mr-2 text-green-400"></i>
                    Task #${group.task.task_number}
                    <span class="ml-2 px-2 py-1 bg-green-500 text-white text-xs font-bold rounded">${group.responses.length} Review${group.responses.length !== 1 ? 's' : ''}</span>
                    <span class="ml-2 text-sm text-gray-400">Avg: ${avgResponse.toFixed(1)} hrs</span>
                </h5>
                <div class="text-right">
                    <p class="text-sm text-gray-400">${group.task.videographer || 'Unknown'}</p>
                    <p class="text-xs text-gray-500">${group.task.brand || 'N/A'}</p>
                </div>
            </div>
            <div id="responses-${group.task.task_number}" class="hidden mt-4 pl-4 border-l-2 border-green-500">
                ${group.responses.map((response, index) => `
                    <div class="bg-gray-900 bg-opacity-40 rounded-lg p-4 mb-3 border-l-4 ${response.decision === 'Accepted' ? 'border-green-500' : 'border-red-500'}">
                        <div class="flex items-center justify-between mb-2">
                            <h6 class="font-bold text-lg ${response.decision === 'Accepted' ? 'text-green-300' : 'text-red-300'}">
                                Version ${response.version} - ${response.decision}
                            </h6>
                            <span class="px-3 py-1 ${response.decision === 'Accepted' ? 'bg-green-600' : 'bg-red-600'} text-white text-sm font-semibold rounded">
                                ${response.responseHours} hrs
                            </span>
                        </div>
                        <p class="text-xs text-gray-400 mb-1">Uploaded: ${response.uploadTime.toLocaleString()}</p>
                        <p class="text-xs text-gray-400 mb-2">Reviewed: ${response.reviewTime.toLocaleString()}</p>
                        ${response.rejectionClass ? `<p class="text-sm text-yellow-300 mt-2"><strong>Class:</strong> ${response.rejectionClass}</p>` : ''}
                        ${response.comments ? `<p class="text-sm text-gray-300 mt-2"><i class="fas fa-comment-dots mr-1"></i>${response.comments}</p>` : ''}
                    </div>
                `).join('')}
            </div>
        </div>
        `;
    }).join('');
}

// Render videos handled details
function renderVideosHandledDetails(handledVideos) {
    if (handledVideos.length === 0) {
        return '<p class="text-gray-400 text-center py-8">No handled videos available.</p>';
    }

    // Group by task
    const taskGroups = {};
    handledVideos.forEach(hv => {
        const taskNum = hv.task.task_number;
        if (!taskGroups[taskNum]) {
            taskGroups[taskNum] = {
                task: hv.task,
                videos: []
            };
        }
        taskGroups[taskNum].videos.push(hv);
    });

    return Object.values(taskGroups).map(group => {
        return `
        <div class="bg-white bg-opacity-5 rounded-lg p-4 mb-4 transition-all">
            <div class="flex items-start justify-between cursor-pointer hover:bg-opacity-10" onclick="toggleHandledHistory(${group.task.task_number})">
                <h5 class="text-lg font-semibold text-white mb-1">
                    <i id="handled-icon-${group.task.task_number}" class="fas fa-chevron-down mr-2 text-blue-400"></i>
                    Task #${group.task.task_number}
                    <span class="ml-2 px-2 py-1 bg-blue-500 text-white text-xs font-bold rounded">${group.videos.length} Version${group.videos.length !== 1 ? 's' : ''}</span>
                </h5>
                <div class="text-right">
                    <p class="text-sm text-gray-400">${group.task.videographer || 'Unknown'}</p>
                    <p class="text-xs text-gray-500">${group.task.brand || 'N/A'}</p>
                </div>
            </div>
            <div id="handled-${group.task.task_number}" class="hidden mt-4 pl-4 border-l-2 border-blue-500">
                ${group.videos.map((video, index) => {
                    let correctnessColor = 'text-yellow-300';
                    let correctnessBg = 'bg-yellow-600';
                    if (video.correctness === 'Correct') {
                        correctnessColor = 'text-green-300';
                        correctnessBg = 'bg-green-600';
                    } else if (video.correctness === 'Incorrect') {
                        correctnessColor = 'text-red-300';
                        correctnessBg = 'bg-red-600';
                    } else if (video.correctness === 'N/A') {
                        correctnessColor = 'text-gray-300';
                        correctnessBg = 'bg-gray-600';
                    }

                    return `
                    <div class="bg-gray-900 bg-opacity-40 rounded-lg p-4 mb-3">
                        <div class="flex items-center justify-between mb-2">
                            <h6 class="font-bold text-lg text-white">Version ${video.version}</h6>
                            <span class="px-3 py-1 ${correctnessBg} text-white text-sm font-semibold rounded">
                                ${video.correctness}
                            </span>
                        </div>
                        <div class="${video.hodDecision === 'Rejected' ? 'mt-3' : 'grid grid-cols-2 gap-4 mt-3'}">
                            <div>
                                <p class="text-xs text-gray-500 mb-1">HOD Decision</p>
                                <p class="text-sm font-semibold ${video.hodDecision === 'Accepted' ? 'text-green-400' : 'text-red-400'}">
                                    ${video.hodDecision}
                                </p>
                            </div>
                            ${video.hodDecision === 'Accepted' ? `
                            <div>
                                <p class="text-xs text-gray-500 mb-1">HOS Decision</p>
                                <p class="text-sm font-semibold ${video.hosDecision === 'Accepted' ? 'text-green-400' : video.hosDecision === 'Returned' ? 'text-red-400' : 'text-yellow-400'}">
                                    ${video.hosDecision || 'Pending'}
                                </p>
                            </div>
                            ` : ''}
                        </div>
                    </div>
                `;
                }).join('')}
            </div>
        </div>
        `;
    }).join('');
}

// Render accepted tasks details
function renderAcceptedTasksDetails(acceptedTasks) {
    if (acceptedTasks.length === 0) {
        return '<p class="text-gray-400 text-center py-8">No accepted tasks available.</p>';
    }

    return acceptedTasks.map(at => {
        return `
        <div class="bg-white bg-opacity-5 rounded-lg p-4 mb-3 transition-all hover:bg-opacity-10">
            <div class="flex items-start justify-between">
                <div>
                    <h5 class="text-lg font-semibold text-white mb-1">
                        Task #${at.task.task_number}
                        <span class="ml-2 px-2 py-1 bg-purple-500 text-white text-xs font-bold rounded">Version ${at.acceptedVersion}</span>
                    </h5>
                    <p class="text-sm text-gray-400">${at.task.videographer_name || 'Unknown'}</p>
                    <p class="text-xs text-gray-500">${at.task.job_number || 'N/A'}</p>
                </div>
                <div class="text-right">
                    <span class="px-3 py-1 bg-green-600 text-white text-sm font-semibold rounded">
                        Accepted by HOS
                    </span>
                </div>
            </div>
        </div>
        `;
    }).join('');
}

// Render pending reviews details
function renderPendingReviewsDetails(pendingReviews) {
    if (pendingReviews.length === 0) {
        return '<p class="text-gray-400 text-center py-8">No pending reviews.</p>';
    }

    // Group by task
    const taskGroups = {};
    pendingReviews.forEach(pr => {
        const taskNum = pr.task.task_number;
        if (!taskGroups[taskNum]) {
            taskGroups[taskNum] = {
                task: pr.task,
                versions: []
            };
        }
        taskGroups[taskNum].versions.push(pr);
    });

    return Object.values(taskGroups).map(group => {
        const maxWaiting = Math.max(...group.versions.map(v => v.waitingHours));

        return `
        <div class="bg-white bg-opacity-5 rounded-lg p-4 mb-4 transition-all">
            <div class="flex items-start justify-between cursor-pointer hover:bg-opacity-10" onclick="togglePendingHistory(${group.task.task_number})">
                <h5 class="text-lg font-semibold text-white mb-1">
                    <i id="pending-icon-${group.task.task_number}" class="fas fa-chevron-down mr-2 text-orange-400"></i>
                    Task #${group.task.task_number}
                    <span class="ml-2 px-2 py-1 bg-orange-500 text-white text-xs font-bold rounded">${group.versions.length} Pending</span>
                    <span class="ml-2 text-sm text-gray-400">Max Wait: ${maxWaiting} hrs</span>
                </h5>
                <div class="text-right">
                    <p class="text-sm text-gray-400">${group.task.videographer || 'Unknown'}</p>
                    <p class="text-xs text-gray-500">${group.task.brand || 'N/A'}</p>
                </div>
            </div>
            <div id="pending-${group.task.task_number}" class="hidden mt-4 pl-4 border-l-2 border-orange-500">
                ${group.versions.map((pending, index) => `
                    <div class="bg-orange-900 bg-opacity-20 rounded-lg p-4 mb-3 border-l-4 border-orange-500">
                        <div class="flex items-center justify-between mb-2">
                            <h6 class="font-bold text-lg text-orange-300">Version ${pending.version}</h6>
                            <span class="px-3 py-1 bg-orange-600 text-white text-sm font-semibold rounded">
                                Waiting: ${pending.waitingHours} hrs
                            </span>
                        </div>
                        <p class="text-xs text-gray-400">Uploaded: ${pending.uploadTime ? pending.uploadTime.toLocaleString() : 'Unknown'}</p>
                    </div>
                `).join('')}
            </div>
        </div>
        `;
    }).join('');
}

// Toggle functions for collapsible sections
function toggleResponseHistory(taskNumber) {
    const content = document.getElementById(`responses-${taskNumber}`);
    const icon = document.getElementById(`response-icon-${taskNumber}`);
    if (content.classList.contains('hidden')) {
        content.classList.remove('hidden');
        icon.classList.remove('fa-chevron-down');
        icon.classList.add('fa-chevron-up');
    } else {
        content.classList.add('hidden');
        icon.classList.remove('fa-chevron-up');
        icon.classList.add('fa-chevron-down');
    }
}

function toggleHandledHistory(taskNumber) {
    const content = document.getElementById(`handled-${taskNumber}`);
    const icon = document.getElementById(`handled-icon-${taskNumber}`);
    if (content.classList.contains('hidden')) {
        content.classList.remove('hidden');
        icon.classList.remove('fa-chevron-down');
        icon.classList.add('fa-chevron-up');
    } else {
        content.classList.add('hidden');
        icon.classList.remove('fa-chevron-up');
        icon.classList.add('fa-chevron-down');
    }
}

function togglePendingHistory(taskNumber) {
    const content = document.getElementById(`pending-${taskNumber}`);
    const icon = document.getElementById(`pending-icon-${taskNumber}`);
    if (content.classList.contains('hidden')) {
        content.classList.remove('hidden');
        icon.classList.remove('fa-chevron-down');
        icon.classList.add('fa-chevron-up');
    } else {
        content.classList.add('hidden');
        icon.classList.remove('fa-chevron-up');
        icon.classList.add('fa-chevron-down');
    }
}

// Close details modal
function closeDetailsModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('detailsModal');
    modal.classList.add('hidden');
    document.body.style.overflow = '';
}

// Render failure analysis for videographer modal
function renderFailureAnalysis(tasks) {
    // Collect all rejection events with their classes
    const rejectionClasses = {};
    let totalRejections = 0;

    tasks.forEach(task => {
        if (!task.versions) return;

        task.versions.forEach(version => {
            if (!version.lifecycle || version.lifecycle.length === 0) return;

            version.lifecycle.forEach(event => {
                const stage = event.stage ? event.stage.toLowerCase() : '';

                // Count rejection events (rejected/editing by HOD, returned by HOS)
                if (stage === 'rejected' || stage === 'editing' || stage === 'returned') {
                    const rejClass = event.rejection_class || 'Unclassified';

                    if (!rejectionClasses[rejClass]) {
                        rejectionClasses[rejClass] = {
                            count: 0,
                            tasks: new Set()
                        };
                    }

                    rejectionClasses[rejClass].count++;
                    rejectionClasses[rejClass].tasks.add(task.task_number || task['Task Number']);
                    totalRejections++;
                }
            });
        });
    });

    // Convert to array and sort by count
    const sortedRejections = Object.entries(rejectionClasses)
        .map(([className, data]) => ({
            className,
            count: data.count,
            taskCount: data.tasks.size,
            percentage: totalRejections > 0 ? ((data.count / totalRejections) * 100).toFixed(1) : 0
        }))
        .sort((a, b) => b.count - a.count);

    if (sortedRejections.length === 0) {
        return `
            <div class="text-center py-12">
                <i class="fas fa-check-circle text-6xl text-green-400 mb-4"></i>
                <p class="text-xl text-gray-300">No rejections recorded</p>
                <p class="text-sm text-gray-500 mt-2">This videographer has a clean track record!</p>
            </div>
        `;
    }

    // Create visual breakdown
    let html = `
        <div class="space-y-4">
            <div class="glass-card p-6 rounded-xl bg-white bg-opacity-5">
                <div class="text-center mb-6">
                    <p class="text-4xl font-bold text-red-400">${totalRejections}</p>
                    <p class="text-sm text-gray-400 mt-1">Total Rejections</p>
                </div>
            </div>
    `;

    sortedRejections.forEach((rejection, index) => {
        const colors = [
            'bg-red-500',
            'bg-orange-500',
            'bg-yellow-500',
            'bg-blue-500',
            'bg-purple-500',
            'bg-pink-500',
            'bg-indigo-500'
        ];
        const color = colors[index % colors.length];

        html += `
            <div class="glass-card p-4 rounded-xl bg-white bg-opacity-5 hover:bg-opacity-10 transition-all">
                <div class="flex items-center justify-between mb-3">
                    <div class="flex items-center space-x-3">
                        <div class="w-3 h-3 rounded-full ${color}"></div>
                        <h5 class="font-semibold text-white">${rejection.className}</h5>
                    </div>
                    <div class="text-right">
                        <p class="text-2xl font-bold text-white">${rejection.count}</p>
                        <p class="text-xs text-gray-400">${rejection.percentage}% of all rejections</p>
                    </div>
                </div>
                <div class="w-full bg-gray-700 rounded-full h-3 overflow-hidden">
                    <div class="${color} h-full rounded-full transition-all duration-500" style="width: ${rejection.percentage}%"></div>
                </div>
                <p class="text-xs text-gray-400 mt-2">
                    <i class="fas fa-tasks mr-1"></i>
                    Occurred in ${rejection.taskCount} task${rejection.taskCount !== 1 ? 's' : ''}
                </p>
            </div>
        `;
    });

    html += `</div>`;
    return html;
}

// Create distribution chart for videographer modal
function createModalDistributionChart(pending, rejected, returned, submitted, accepted) {
    const ctx = document.getElementById('modalDistributionChart');
    if (!ctx) return;

    // Destroy existing chart if it exists
    if (modalDistributionChartInstance) {
        modalDistributionChartInstance.destroy();
    }

    modalDistributionChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Pending HOD', 'Rejected by HOD', 'Rejected by HOS', 'Pending HOS', 'Accepted'],
            datasets: [{
                label: 'Version Count',
                data: [pending, rejected, returned, submitted, accepted],
                backgroundColor: [
                    'rgba(234, 179, 8, 0.8)',   // yellow for pending
                    'rgba(239, 68, 68, 0.8)',   // red for rejected
                    'rgba(251, 146, 60, 0.8)',  // orange for returned
                    'rgba(59, 130, 246, 0.8)',  // blue for submitted
                    'rgba(34, 197, 94, 0.8)'    // green for accepted
                ],
                borderColor: [
                    'rgba(234, 179, 8, 1)',
                    'rgba(239, 68, 68, 1)',
                    'rgba(251, 146, 60, 1)',
                    'rgba(59, 130, 246, 1)',
                    'rgba(34, 197, 94, 1)'
                ],
                borderWidth: 2,
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    padding: 12,
                    titleFont: {
                        size: 14
                    },
                    bodyFont: {
                        size: 13
                    },
                    callbacks: {
                        label: function(context) {
                            return `${context.parsed.y} version${context.parsed.y !== 1 ? 's' : ''}`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: '#9CA3AF',
                        font: {
                            size: 12
                        },
                        stepSize: 1
                    },
                    grid: {
                        color: 'rgba(75, 85, 99, 0.3)'
                    }
                },
                x: {
                    ticks: {
                        color: '#9CA3AF',
                        font: {
                            size: 12
                        }
                    },
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

// Navigation helper functions for modal
function scrollToSection(index) {
    const container = document.getElementById('modalScrollContainer');
    if (!container) return;

    const sectionWidth = container.offsetWidth;
    container.scrollTo({
        left: sectionWidth * index,
        behavior: 'smooth'
    });
}

function scrollSections(direction) {
    const container = document.getElementById('modalScrollContainer');
    if (!container) return;

    const sectionWidth = container.offsetWidth;
    const currentScroll = container.scrollLeft;
    const currentSection = Math.round(currentScroll / sectionWidth);
    const newSection = Math.max(0, Math.min(2, currentSection + direction));

    scrollToSection(newSection);
}

function updateNavigationDots() {
    const container = document.getElementById('modalScrollContainer');
    if (!container) return;

    const sectionWidth = container.offsetWidth;
    const currentScroll = container.scrollLeft;
    const currentSection = Math.round(currentScroll / sectionWidth);

    const dots = document.querySelectorAll('.modal-nav-dot');
    dots.forEach((dot, index) => {
        if (index === currentSection) {
            dot.classList.add('active', 'bg-indigo-500', 'w-8');
            dot.classList.remove('bg-gray-600', 'w-3');
        } else {
            dot.classList.remove('active', 'bg-indigo-500', 'w-8');
            dot.classList.add('bg-gray-600', 'w-3');
        }
    });
}
