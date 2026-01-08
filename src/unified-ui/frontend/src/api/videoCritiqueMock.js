import {
  computePie,
  computeQuickStats,
  computeReviewerStats,
  computeSummary,
  computeSummaryVideographers,
  countVersionStages,
  getPendingReviews,
  getResponseTimeData,
  groupTasksByVideographer,
} from "../lib/videoCritiqueMetrics";

const MOCK_TASKS = [
  {
    task_number: 2217,
    brand: "City Brand Launch",
    filming_deadline: "17-02-2025",
    submission_date: "20-02-2025",
    status: "Critique",
    videographer: "Alyssa Reed",
    location: "Dubai",
    versions: [
      {
        version: 1,
        lifecycle: [
          { stage: "pending", at: "18-02-2025 10:00:00" },
        ],
      },
    ],
  },
  {
    task_number: 2216,
    brand: "Mall LED Loop",
    filming_deadline: "16-02-2025",
    submission_date: "19-02-2025",
    status: "Submitted to Sales",
    videographer: "Ravi Sharma",
    location: "Dubai",
    versions: [
      {
        version: 1,
        lifecycle: [
          { stage: "pending", at: "17-02-2025 09:00:00" },
          { stage: "submitted to sales", at: "18-02-2025 11:30:00" },
        ],
      },
    ],
  },
  {
    task_number: 2215,
    brand: "Festival Teaser",
    filming_deadline: "15-02-2025",
    submission_date: "18-02-2025",
    status: "Returned",
    videographer: "Alyssa Reed",
    location: "Abu Dhabi",
    versions: [
      {
        version: 1,
        lifecycle: [
          { stage: "pending", at: "15-02-2025 10:00:00" },
          { stage: "submitted", at: "16-02-2025 12:00:00" },
          {
            stage: "returned",
            at: "17-02-2025 15:30:00",
            rejection_class: "Lighting",
            rejection_comments: "Exposure too dark",
            rejected_by: "Head of Sales",
          },
        ],
      },
    ],
  },
  {
    task_number: 2214,
    brand: "Luxury Auto Montage",
    filming_deadline: "14-02-2025",
    submission_date: "17-02-2025",
    status: "Editing",
    videographer: "Noah Chen",
    location: "Sharjah",
    versions: [
      {
        version: 1,
        lifecycle: [
          { stage: "pending", at: "14-02-2025 09:30:00" },
          {
            stage: "rejected",
            at: "15-02-2025 12:10:00",
            rejection_class: "Artwork Color",
            rejection_comments: "Incorrect color profile",
            rejected_by: "Reviewer",
          },
        ],
      },
    ],
  },
  {
    task_number: 2213,
    brand: "Airport Arrival Hero",
    filming_deadline: "12-02-2025",
    submission_date: "15-02-2025",
    status: "Accepted",
    videographer: "Noah Chen",
    location: "Dubai",
    versions: [
      {
        version: 1,
        lifecycle: [
          { stage: "pending", at: "12-02-2025 10:00:00" },
          { stage: "submitted to sales", at: "13-02-2025 15:00:00" },
          { stage: "accepted", at: "14-02-2025 12:00:00" },
        ],
      },
    ],
  },
  {
    task_number: 2212,
    brand: "Retail Weekend Promo",
    filming_deadline: "10-02-2025",
    submission_date: "13-02-2025",
    status: "Done",
    videographer: "Ravi Sharma",
    location: "Ajman",
    versions: [
      {
        version: 1,
        lifecycle: [
          { stage: "pending", at: "10-02-2025 10:00:00" },
          { stage: "submitted", at: "11-02-2025 14:00:00" },
          { stage: "done", at: "12-02-2025 10:00:00" },
        ],
      },
    ],
  },
  {
    task_number: 2211,
    brand: "Harbor Night Loop",
    filming_deadline: "18-02-2025",
    submission_date: "21-02-2025",
    status: "Editing",
    videographer: "Alyssa Reed",
    location: "Dubai",
    versions: [
      {
        version: 1,
        lifecycle: [
          { stage: "pending", at: "16-02-2025 11:00:00" },
          {
            stage: "editing",
            at: "17-02-2025 13:00:00",
            rejection_class: "Environment Too Dark",
            rejection_comments: "Please brighten the surrounding scene",
            rejected_by: "Reviewer",
          },
        ],
      },
    ],
  },
  {
    task_number: 2210,
    brand: "City Center Countdown",
    filming_deadline: "22-02-2025",
    submission_date: "25-02-2025",
    status: "Assigned to Alyssa",
    videographer: "Alyssa Reed",
    location: "Dubai",
    versions: [],
  },
  {
    task_number: 2209,
    brand: "Expo Walkthrough",
    filming_deadline: "24-02-2025",
    submission_date: "27-02-2025",
    status: "Not assigned yet",
    videographer: "Unassigned",
    location: "Abu Dhabi",
    versions: [],
  },
  {
    task_number: 2208,
    brand: "Weekend Highlights",
    filming_deadline: "13-02-2025",
    submission_date: "16-02-2025",
    status: "Submitted to Sales",
    videographer: "Ravi Sharma",
    location: "Sharjah",
    versions: [
      {
        version: 1,
        lifecycle: [
          { stage: "pending", at: "13-02-2025 09:00:00" },
          {
            stage: "rejected",
            at: "14-02-2025 10:30:00",
            rejection_class: "Lighting",
            rejection_comments: "Flicker in the panel",
            rejected_by: "Reviewer",
          },
        ],
      },
      {
        version: 2,
        lifecycle: [
          { stage: "pending", at: "15-02-2025 12:15:00" },
          { stage: "submitted", at: "16-02-2025 14:40:00" },
        ],
      },
    ],
  },
];

const MOCK_HISTORY = {
  session_id: "vc-session-01",
  messages: [
    {
      id: "vc-msg-1",
      role: "assistant",
      content:
        "Good morning. Upload a cut or describe the request, and I will log the critique, checklist, and next steps.",
      timestamp: "2025-02-18T08:40:12+04:00",
    },
  ],
  message_count: 1,
  last_updated: "2025-02-18T08:40:12+04:00",
};
const MOCK_WORKFLOWS = [
  {
    workflow_id: "workflow-2217",
    task_number: 2217,
    folder_name: "City Brand Launch",
    status: "pending_reviewer",
    created_at: "2025-02-18T09:10:00+04:00",
    reviewer_approved: false,
    hos_approved: false,
  },
];

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function chunkText(text, size) {
  const chunks = [];
  let cursor = 0;
  while (cursor < text.length) {
    chunks.push(text.slice(cursor, cursor + size));
    cursor += size;
  }
  return chunks;
}

function buildReply(message, hasFile) {
  const trimmed = (message || "").trim();
  const base = trimmed
    ? `Thanks for the details on "${trimmed}".`
    : "Thanks for the upload.";
  const header = hasFile
    ? "I reviewed the file and captured the critique highlights below:"
    : "Here is a quick critique outline to confirm before I log the request:";
  return [
    `${base} ${header}`,
    "",
    "- Narrative clarity: tighten the opening 3 seconds.",
    "- Visual hierarchy: spotlight the primary CTA earlier.",
    "- Audio mix: reduce music by about 3dB under VO.",
    "- Export: keep 1080x1920, 29.97fps.",
    "",
    "Reply with any edits or confirm if I should submit to the reviewer.",
  ].join("\n");
}

function buildApprovalActions(workflowId) {
  return [
    { action_id: "approve_reviewer", label: "Approve", workflow_id: workflowId, variant: "secondary" },
    { action_id: "reject_reviewer", label: "Reject", workflow_id: workflowId, variant: "ghost" },
  ];
}

function createAbortGuard(signal) {
  let aborted = false;
  if (signal) {
    if (signal.aborted) {
      aborted = true;
    } else {
      signal.addEventListener(
        "abort",
        () => {
          aborted = true;
        },
        { once: true }
      );
    }
  }
  return () => aborted;
}

function isVideoFile(file) {
  if (!file) return false;
  if (file.type && file.type.startsWith("video/")) return true;
  const name = file.name || "";
  return /\.(mp4|mov|avi|mkv|webm)$/i.test(name);
}

function buildDashboardData() {
  const summary = computeSummary(MOCK_TASKS);
  const pie = computePie(MOCK_TASKS);
  const reviewer = computeReviewerStats(MOCK_TASKS);
  const summaryVideographers = computeSummaryVideographers(MOCK_TASKS);
  const videographers = groupTasksByVideographer(MOCK_TASKS);
  const quickStats = computeQuickStats(MOCK_TASKS);
  const statusCounts = countVersionStages(MOCK_TASKS);
  const pendingReviews = getPendingReviews(MOCK_TASKS);
  const responseTimes = getResponseTimeData(MOCK_TASKS);

  return {
    mode: "month",
    period: "2025-02",
    tasks: MOCK_TASKS,
    summary,
    pie,
    reviewer,
    summary_videographers: summaryVideographers,
    videographers,
    quick_stats: quickStats,
    status_counts: statusCounts,
    pending_reviews: pendingReviews,
    response_times: responseTimes,
  };
}

export async function getDashboardFull({ mode, period } = {}) {
  await delay(240);
  return {
    ...buildDashboardData(),
    mode: mode || "month",
    period: period || "2025-02",
  };
}

export async function getDashboardOverview() {
  await delay(240);
  return buildDashboardData();
}

export async function getDashboardStats() {
  await delay(160);
  return computeSummary(MOCK_TASKS);
}

export async function getDashboardWorkload() {
  await delay(180);
  const summaryVideographers = computeSummaryVideographers(MOCK_TASKS);
  const workload = Object.entries(summaryVideographers).map(([name, stats]) => ({
    name,
    active_tasks: Math.max(stats.total - stats.completed, 0),
    completed_today: 1,
    pending_review: Math.round(stats.total / 3),
  }));
  return {
    videographers: workload,
    total_videographers: workload.length,
  };
}

export async function getDashboardUpcomingShoots() {
  await delay(180);
  return {
    shoots: MOCK_TASKS.slice(0, 4).map((task) => ({
      date: task.filming_deadline || "",
      task_number: task.task_number,
      brand: task.brand,
      location: task.location,
      videographer: task.videographer,
      time_block: "day",
    })),
    count: 4,
  };
}

export async function getDashboardByStatus() {
  await delay(180);
  const counts = countVersionStages(MOCK_TASKS);
  return {
    by_status: {
      Pending: counts.pending,
      Rejected: counts.rejected,
      Returned: counts.returned,
      "Submitted to Sales": counts.submitted,
      Accepted: counts.accepted,
    },
    total: MOCK_TASKS.length,
  };
}

export async function getDashboardByLocation() {
  await delay(180);
  const byLocation = {};
  MOCK_TASKS.forEach((task) => {
    const key = task.location || "Unknown";
    byLocation[key] = (byLocation[key] || 0) + 1;
  });
  return { by_location: byLocation, total: MOCK_TASKS.length };
}

export async function getDashboardByVideographer() {
  await delay(180);
  const byVideographer = {};
  MOCK_TASKS.forEach((task) => {
    const key = task.videographer || "Unassigned";
    byVideographer[key] = (byVideographer[key] || 0) + 1;
  });
  return { by_videographer: byVideographer, total: MOCK_TASKS.length };
}

export async function getHistory() {
  await delay(200);
  return MOCK_HISTORY;
}

export async function uploadFile({ file, message, sessionId }) {
  await delay(200);
  const resolvedSessionId = sessionId || `vc-session-${Date.now()}`;
  const fileId = `vc-file-${Date.now()}`;

  if (isVideoFile(file)) {
    return {
      success: true,
      file_id: fileId,
      filename: file?.name || "upload",
      type: "video",
      message: "Video received. Which task number is this for?",
      session_id: resolvedSessionId,
    };
  }

  return {
    success: true,
    file_id: fileId,
    filename: file?.name || "upload",
    file_url: URL.createObjectURL(file),
    type: "image",
    response: buildReply(message, true),
    session_id: resolvedSessionId,
    timestamp: new Date().toISOString(),
  };
}

export async function uploadAttachment({ file }) {
  await delay(200);
  return {
    file_id: `vc-asset-${Date.now()}`,
    filename: file?.name || "attachment",
    file_url: URL.createObjectURL(file),
  };
}

export async function uploadVideo({ file, taskNumber }) {
  await delay(260);
  return {
    success: true,
    file_id: `vc-video-${Date.now()}`,
    workflow_id: `workflow-${Date.now()}`,
    version: 1,
    message: `Video uploaded successfully (v1) for task #${taskNumber}`,
  };
}

export async function sendCommand({ command, args, sessionId }) {
  await delay(200);
  const resolvedSessionId = sessionId || `vc-session-${Date.now()}`;
  const normalized = (command || "").toLowerCase();
  const details = (args || "").trim();

  if (!normalized) {
    return {
      success: false,
      command: "",
      error: "Unknown command: /. Use /help for available commands.",
      session_id: resolvedSessionId,
    };
  }

  if (normalized === "help") {
    return {
      success: true,
      command: normalized,
      response:
        "**Video Critique Commands**\n\n" +
        "- /log or /design - Start a new design request\n" +
        "- /recent - Export recent task data\n" +
        "- /edit <task_number> - Edit an existing task\n" +
        "- /delete <task_number> - Delete a task\n\n" +
        "You can also paste briefs or upload images/videos.",
      session_id: resolvedSessionId,
    };
  }

  if (normalized === "log" || normalized === "design") {
    return {
      success: true,
      command: normalized,
      response: buildReply(details || "I want to log a design request", false),
      session_id: resolvedSessionId,
    };
  }

  if (normalized === "edit") {
    return {
      success: true,
      command: normalized,
      response: details
        ? "Editing task " + details + ". Which fields should I update?"
        : "Please provide a task number: /edit <task_number>",
      session_id: resolvedSessionId,
    };
  }

  if (normalized === "delete") {
    return {
      success: true,
      command: normalized,
      response: details
        ? "Delete request queued for task " + details + ". Confirm to proceed."
        : "Please provide a task number: /delete <task_number>",
      session_id: resolvedSessionId,
    };
  }

  if (normalized === "recent") {
    return {
      success: true,
      command: normalized,
      response: "Preparing the latest export. I will send the download link shortly.",
      session_id: resolvedSessionId,
    };
  }

  return {
    success: false,
    command: normalized,
    error: "Unknown command: /" + normalized + ". Use /help for available commands.",
    session_id: resolvedSessionId,
  };
}

export async function sendAction({ actionId, workflowId }) {
  await delay(200);
  if (actionId === "reject_reviewer" || actionId === "return_hos") {
    return {
      success: true,
      message: "Please provide rejection details.",
      requires_form: true,
      form_type: actionId === "return_hos" ? "return" : "rejection",
      workflow_id: workflowId,
    };
  }
  return {
    success: true,
    message: `Action ${actionId} applied for ${workflowId}.`,
  };
}

export async function submitForm({ formType, workflowId }) {
  await delay(200);
  return {
    success: true,
    message: `${formType} submitted for ${workflowId}.`,
  };
}

export async function getFormConfig(formType) {
  await delay(120);
  if (formType === "return") {
    return {
      title: "Return for Revision",
      submit_text: "Submit",
      fields: [
        {
          id: "category",
          label: "Category",
          type: "select",
          required: true,
          options: [
            { value: "technical", label: "Technical Issue" },
            { value: "content", label: "Content Issue" },
            { value: "quality", label: "Quality Issue" },
            { value: "missing", label: "Missing Elements" },
            { value: "other", label: "Other" },
          ],
        },
        {
          id: "reason",
          label: "Details",
          type: "textarea",
          required: true,
          placeholder: "Please describe what needs to be revised...",
        },
      ],
    };
  }
  return {
    title: "Reject Video",
    submit_text: "Submit",
    fields: [
      {
        id: "category",
        label: "Category",
        type: "select",
        required: true,
        options: [
          { value: "technical", label: "Technical Issue" },
          { value: "content", label: "Content Issue" },
          { value: "quality", label: "Quality Issue" },
          { value: "missing", label: "Missing Elements" },
          { value: "other", label: "Other" },
        ],
      },
      {
        id: "reason",
        label: "Details",
        type: "textarea",
        required: true,
        placeholder: "Please describe what needs to be fixed...",
      },
    ],
  };
}

export async function getPendingWorkflows() {
  await delay(150);
  return {
    count: MOCK_WORKFLOWS.length,
    workflows: MOCK_WORKFLOWS,
  };
}

export async function getWorkflowStatus(workflowId) {
  await delay(150);
  const workflow = MOCK_WORKFLOWS.find((item) => item.workflow_id === workflowId);
  if (!workflow) {
    return { workflow_id: workflowId, found: false };
  }
  return {
    found: true,
    ...workflow,
  };
}

export function resolveFileUrl(file) {
  if (file?.preview_url) return file.preview_url;
  if (file?.file_url) return file.file_url;
  if (file?.url) return file.url;
  return null;
}

export async function streamMessage({ sessionId, message, fileIds, onEvent, onDone, onError, signal }) {
  const isAborted = createAbortGuard(signal);

  try {
    const resolvedSessionId = sessionId || `vc-session-${Date.now()}`;
    if (isAborted()) return;

    await delay(180);
    if (isAborted()) return;

    const reply = buildReply(message, false);
    const chunks = chunkText(reply, 48);
    for (const chunk of chunks) {
      if (isAborted()) return;
      onEvent?.({ type: "delta", content: chunk });
      await delay(90);
    }

    if (isAborted()) return;
    onEvent?.({ type: "text_done", content: reply });
    if (fileIds?.length) {
      onEvent?.({
        type: "files",
        files: fileIds.map((id, idx) => ({
          file_id: id,
          filename: idx === 0 ? "Brief.pdf" : `Attachment-${idx + 1}.pdf`,
          file_url: `https://example.com/mock-${id}.pdf`,
        })),
      });
    }
    if ((message || "").toLowerCase().includes("approval")) {
      onEvent?.({
        type: "actions",
        actions: buildApprovalActions(MOCK_WORKFLOWS[0].workflow_id),
      });
    }
    onEvent?.({ type: "done", session_id: resolvedSessionId });
    onDone?.();
  } catch (err) {
    onEvent?.({ type: "error", message: err?.message || "Stream failed" });
    onError?.(err);
    throw err;
  }
}
