export function parseDateFromBackend(dateStr) {
  if (!dateStr || dateStr === "NA") return null;

  if (dateStr.includes("T")) {
    const parsed = new Date(dateStr);
    if (!Number.isNaN(parsed.getTime())) return parsed;
  }

  const parts = dateStr.split(" ");
  const datePart = parts[0];
  const timePart = parts[1];
  const dateParts = datePart.split("-");

  if (dateParts.length === 3) {
    const day = Number(dateParts[0]);
    const month = Number(dateParts[1]) - 1;
    const year = Number(dateParts[2]);

    if (Number.isNaN(day) || Number.isNaN(month) || Number.isNaN(year)) return null;

    if (timePart) {
      const timeParts = timePart.split(":");
      const hours = Number(timeParts[0] || 0);
      const minutes = Number(timeParts[1] || 0);
      const seconds = Number(timeParts[2] || 0);
      const dt = new Date(year, month, day, hours, minutes, seconds);
      return Number.isNaN(dt.getTime()) ? null : dt;
    }

    const dt = new Date(year, month, day);
    dt.setHours(0, 0, 0, 0);
    return Number.isNaN(dt.getTime()) ? null : dt;
  }

  return null;
}

export function getLatestStage(version) {
  if (!version?.lifecycle?.length) return "";
  const latest = version.lifecycle[version.lifecycle.length - 1];
  return (latest?.stage || "").toLowerCase();
}

export function groupTasksByVideographer(tasks) {
  const grouped = {};
  tasks.forEach((task) => {
    const name = task.videographer || task.Videographer || "Unassigned";
    if (!grouped[name]) grouped[name] = [];
    grouped[name].push(task);
  });
  return grouped;
}

export function countVersionStages(tasks) {
  const counts = {
    pending: 0,
    rejected: 0,
    returned: 0,
    submitted: 0,
    accepted: 0,
  };

  tasks.forEach((task) => {
    (task.versions || []).forEach((version) => {
      const stage = getLatestStage(version);
      if (stage === "pending" || stage === "critique") counts.pending += 1;
      else if (stage === "rejected" || stage === "editing") counts.rejected += 1;
      else if (stage === "returned") counts.returned += 1;
      else if (stage === "submitted" || stage === "submitted to sales") counts.submitted += 1;
      else if (stage === "accepted" || stage === "done") counts.accepted += 1;
    });
  });

  return counts;
}

export function computeSummary(tasks) {
  const total = tasks.length;
  const assigned = tasks.filter((task) => {
    const name = task.videographer || task.Videographer || "Unassigned";
    return name && name !== "Unassigned" && task.status !== "Not assigned yet";
  }).length;

  let uploads = 0;
  tasks.forEach((task) => {
    uploads += (task.versions || []).length;
  });

  const counts = countVersionStages(tasks);
  const totalReviewed = counts.accepted + counts.submitted + counts.rejected + counts.returned;
  const acceptedPct = totalReviewed > 0 ? Math.round(((counts.accepted + counts.submitted) / totalReviewed) * 100) : 0;

  return {
    total,
    assigned,
    uploads,
    pending: counts.pending,
    rejected: counts.rejected,
    returned: counts.returned,
    submitted_to_sales: counts.submitted,
    accepted_videos: counts.accepted,
    accepted_pct: acceptedPct,
  };
}

export function computePie(tasks) {
  const completed = tasks.filter((task) => task.status === "Accepted" || task.status === "Done").length;
  return {
    completed,
    not_completed: tasks.length - completed,
  };
}

export function computeReviewerStats(tasks) {
  let totalResponseHours = 0;
  let responseCount = 0;
  let handledCount = 0;
  let acceptedByHOS = 0;
  let returnedByHOS = 0;

  tasks.forEach((task) => {
    (task.versions || []).forEach((version) => {
      const lifecycle = version.lifecycle || [];
      if (lifecycle.length < 2) return;

      let uploadTime = null;
      for (const event of lifecycle) {
        const stage = (event.stage || "").toLowerCase();
        if (stage === "pending" || stage === "critique") {
          uploadTime = parseDateFromBackend(event.at);
          break;
        }
      }

      let reviewTime = null;
      let reviewDecision = null;
      for (const event of lifecycle) {
        const stage = (event.stage || "").toLowerCase();
        if (stage === "rejected" || stage === "editing" || stage === "accepted" || stage === "submitted" || stage === "submitted to sales") {
          reviewTime = parseDateFromBackend(event.at);
          reviewDecision = stage;
          break;
        }
      }

      if (!uploadTime || !reviewTime || !reviewDecision) return;

      handledCount += 1;
      const responseHours = Math.round((reviewTime - uploadTime) / (1000 * 60 * 60));
      totalResponseHours += responseHours;
      responseCount += 1;

      if (reviewDecision === "accepted" || reviewDecision === "submitted" || reviewDecision === "submitted to sales") {
        let hasHOSAccepted = false;
        let hasHOSReturned = false;
        lifecycle.forEach((event) => {
          const stage = (event.stage || "").toLowerCase();
          if (stage === "accepted" || stage === "done") hasHOSAccepted = true;
          if (stage === "returned") hasHOSReturned = true;
        });
        if (hasHOSAccepted) acceptedByHOS += 1;
        if (hasHOSReturned) returnedByHOS += 1;
      }
    });
  });

  const avgResponseHours = responseCount > 0 ? Math.round(totalResponseHours / responseCount) : 0;
  const avgResponseDisplay = avgResponseHours > 0 ? `${avgResponseHours} hrs` : "0 hrs";
  const totalWithHOSDecision = acceptedByHOS + returnedByHOS;
  const handledPercent = totalWithHOSDecision > 0 ? Math.round((acceptedByHOS / totalWithHOSDecision) * 100) : 0;

  return {
    avg_response_display: avgResponseDisplay,
    handled: handledCount,
    accepted: acceptedByHOS,
    handled_percent: handledPercent,
  };
}

export function computeSummaryVideographers(tasks) {
  const grouped = groupTasksByVideographer(tasks);
  const summary = {};
  const now = new Date();
  now.setHours(0, 0, 0, 0);

  Object.entries(grouped).forEach(([name, vgTasks]) => {
    let completed = 0;
    let uploads = 0;
    let late = 0;
    let started = 0;

    vgTasks.forEach((task) => {
      if (task.status === "Accepted" || task.status === "Done") completed += 1;
      uploads += (task.versions || []).length;

      const filmingDate = parseDateFromBackend(task.filming_deadline || task.filming_date || "");
      if (filmingDate && filmingDate <= now) started += 1;

      const submissionDate = parseDateFromBackend(task.submission_date || "");
      if (submissionDate && submissionDate <= now && task.status !== "Accepted" && task.status !== "Done") {
        late += 1;
      }
    });

    const counts = countVersionStages(vgTasks);
    const totalReviewed = counts.accepted + counts.submitted + counts.rejected + counts.returned;
    const acceptedPct = totalReviewed > 0 ? Math.round(((counts.accepted + counts.submitted) / totalReviewed) * 100) : 0;

    summary[name] = {
      total: vgTasks.length,
      started,
      late,
      completed,
      uploads,
      accepted_pct: acceptedPct,
    };
  });

  return summary;
}

export function getTasksWithVersionsInState(tasks, state) {
  const matches = [];
  tasks.forEach((task) => {
    (task.versions || []).forEach((version) => {
      const stage = getLatestStage(version);
      const normalized = stage === "submitted to sales" ? "submitted" : stage;
      if (normalized === state) {
        matches.push({ task, version, stage });
      }
    });
  });
  return matches;
}

export function getTasksWithRejections(tasks, rejectionType) {
  const matches = [];
  tasks.forEach((task) => {
    const rejectionEvents = [];
    (task.versions || []).forEach((version) => {
      (version.lifecycle || []).forEach((event) => {
        const stage = (event.stage || "").toLowerCase();
        const isHod = rejectionType === "hod" && (stage === "rejected" || stage === "editing");
        const isHos = rejectionType === "hos" && stage === "returned";
        if (isHod || isHos) {
          rejectionEvents.push({
            version: version.version,
            event,
            stage,
          });
        }
      });
    });
    if (rejectionEvents.length) {
      matches.push({
        ...task,
        rejectionEvents,
        rejectionCount: rejectionEvents.length,
      });
    }
  });
  return matches;
}

export function getPendingReviews(tasks) {
  const pendingTasks = getTasksWithVersionsInState(tasks, "pending");
  const pendingReviews = [];

  pendingTasks.forEach(({ task, version }) => {
    let uploadTime = null;
    (version.lifecycle || []).forEach((event) => {
      const stage = (event.stage || "").toLowerCase();
      if (stage === "pending" || stage === "critique") {
        uploadTime = parseDateFromBackend(event.at);
      }
    });
    const hoursWaiting = uploadTime ? Math.round((Date.now() - uploadTime.getTime()) / (1000 * 60 * 60)) : null;
    pendingReviews.push({
      task,
      version,
      uploadTime,
      waitingHours: hoursWaiting,
    });
  });

  return { count: pendingReviews.length, reviews: pendingReviews };
}

export function getResponseTimeData(tasks) {
  const responseTimes = [];

  tasks.forEach((task) => {
    (task.versions || []).forEach((version) => {
      let uploadTime = null;
      let reviewTime = null;
      let decision = null;
      let rejectionClass = null;
      let comments = null;

      (version.lifecycle || []).forEach((event) => {
        const stage = (event.stage || "").toLowerCase();
        if (!uploadTime && (stage === "pending" || stage === "critique")) {
          uploadTime = parseDateFromBackend(event.at);
        }
        if (!reviewTime && (stage === "rejected" || stage === "editing" || stage === "accepted" || stage === "submitted" || stage === "submitted to sales")) {
          reviewTime = parseDateFromBackend(event.at);
          decision = stage;
          rejectionClass = event.rejection_class || null;
          comments = event.rejection_comments || null;
        }
      });

      if (uploadTime && reviewTime && decision) {
        const responseHours = Math.round((reviewTime - uploadTime) / (1000 * 60 * 60));
        responseTimes.push({
          task,
          version,
          responseHours,
          uploadTime,
          reviewTime,
          decision,
          rejectionClass,
          comments,
        });
      }
    });
  });

  return responseTimes;
}

export function computeQuickStats(tasks) {
  const summary = computeSummary(tasks);
  const pie = computePie(tasks);
  const now = new Date();
  now.setHours(0, 0, 0, 0);

  let tasksStarted = 0;
  let lateTasks = 0;
  let totalVersionsFromCompleted = 0;
  let completedTaskCount = 0;
  let rejectionsByHOD = 0;
  let rejectionsByHOS = 0;

  tasks.forEach((task) => {
    const filmingDate = parseDateFromBackend(task.filming_deadline || task.filming_date || "");
    if (filmingDate && filmingDate <= now) tasksStarted += 1;

    const submissionDate = parseDateFromBackend(task.submission_date || "");
    if (submissionDate && submissionDate <= now && task.status !== "Accepted" && task.status !== "Done") {
      lateTasks += 1;
    }

    if (task.status === "Accepted" || task.status === "Done") {
      completedTaskCount += 1;
      totalVersionsFromCompleted += (task.versions || []).length;
    }

    (task.versions || []).forEach((version) => {
      (version.lifecycle || []).forEach((event) => {
        const stage = (event.stage || "").toLowerCase();
        if (stage === "rejected" || stage === "editing") rejectionsByHOD += 1;
        if (stage === "returned") rejectionsByHOS += 1;
      });
    });
  });

  const uploadRatio = completedTaskCount > 0 ? (totalVersionsFromCompleted / completedTaskCount).toFixed(2) : "0";

  const pendingVersions = getTasksWithVersionsInState(tasks, "pending");
  const submittedVersions = getTasksWithVersionsInState(tasks, "submitted");

  return {
    summary,
    pie,
    tasksStarted,
    lateTasks,
    pendingHOD: pendingVersions.length,
    pendingHOS: submittedVersions.length,
    rejectionsByHOD,
    rejectionsByHOS,
    uploadRatio,
  };
}

export function isTaskOverdue(task) {
  const submissionDate = parseDateFromBackend(task.submission_date || "");
  if (!submissionDate) return false;
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return submissionDate < now && task.status !== "Accepted" && task.status !== "Done";
}
