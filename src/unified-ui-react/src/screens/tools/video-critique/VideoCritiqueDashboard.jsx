import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Chart,
  ArcElement,
  BarElement,
  CategoryScale,
  DoughnutController,
  PieController,
  BarController,
  Legend,
  LinearScale,
  Tooltip,
} from "chart.js";
import {
  AlertTriangle,
  Calendar,
  CheckCircle2,
  ChevronDown,
  Clock,
  RefreshCw,
  Video,
} from "lucide-react";

import * as videoCritiqueApi from "../../../api/videoCritique";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { LoadingEllipsis } from "../../../components/ui/loading-ellipsis";
import { Modal } from "../../../components/ui/modal";
import { SelectDropdown } from "../../../components/ui/select-dropdown";
import { SoftCard } from "../../../components/ui/soft-card";
import {
  computeQuickStats,
  computeSummaryVideographers,
  countVersionStages,
  getPendingReviews,
  getResponseTimeData,
  getTasksWithRejections,
  getTasksWithVersionsInState,
  isTaskOverdue,
  parseDateFromBackend,
} from "../../../lib/videoCritiqueMetrics";

Chart.register(
  ArcElement,
  BarElement,
  CategoryScale,
  DoughnutController,
  PieController,
  BarController,
  Legend,
  LinearScale,
  Tooltip
);

const STATUS_COLORS = {
  pending: "rgba(234, 179, 8, 0.7)",
  rejected: "rgba(239, 68, 68, 0.7)",
  returned: "rgba(249, 115, 22, 0.7)",
  submitted: "rgba(59, 130, 246, 0.7)",
  accepted: "rgba(34, 197, 94, 0.7)",
};
const MONTH_OPTIONS = [
  { value: 1, label: "January" },
  { value: 2, label: "February" },
  { value: 3, label: "March" },
  { value: 4, label: "April" },
  { value: 5, label: "May" },
  { value: 6, label: "June" },
  { value: 7, label: "July" },
  { value: 8, label: "August" },
  { value: 9, label: "September" },
  { value: 10, label: "October" },
  { value: 11, label: "November" },
  { value: 12, label: "December" },
];

function getYearOptions(currentYear) {
  const start = currentYear - 4;
  const end = currentYear + 1;
  const years = [];
  for (let year = start; year <= end; year += 1) {
    years.push(year);
  }
  return years;
}

function SummaryCard({ icon: Icon, label, value, helper, accentClass, onClick }) {
  const interactive = Boolean(onClick);
  return (
    <SoftCard
      className={`p-4 ${interactive ? "cursor-pointer hover:shadow-md transition-shadow" : ""}`}
      onClick={onClick}
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={
        interactive
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick?.();
              }
            }
          : undefined
      }
    >
      <div className="flex items-center justify-between gap-3">
        <div className={`h-10 w-10 rounded-xl flex items-center justify-center ${accentClass}`}>
          <Icon size={18} />
        </div>
        <div className="text-2xl font-semibold">{value}</div>
      </div>
      <div className="mt-2 text-xs text-black/55 dark:text-white/60">{label}</div>
      {helper ? <div className="text-xs text-black/45 dark:text-white/55">{helper}</div> : null}
    </SoftCard>
  );
}

function ChartCard({ title, children }) {
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-[260px]">{children}</div>
      </CardContent>
    </Card>
  );
}

function AccordionCard({ title, subtitle, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <SoftCard className="p-3">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 text-left"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
      >
        <div className="min-w-0">
          <div className="text-sm font-semibold text-black/80 dark:text-white/85 truncate">{title}</div>
          {subtitle ? <div className="text-xs text-black/50 dark:text-white/60">{subtitle}</div> : null}
        </div>
        <div className="flex items-center gap-2 text-xs text-black/50 dark:text-white/55">
          <span>{open ? "Hide" : "View"}</span>
          <ChevronDown size={16} className={`transition-transform ${open ? "rotate-180" : ""}`} />
        </div>
      </button>
      {open ? <div className="mt-3 space-y-2 text-xs text-black/60 dark:text-white/65">{children}</div> : null}
    </SoftCard>
  );
}

function ChartCanvas({ type, data, options }) {
  const canvasRef = React.useRef(null);

  React.useEffect(() => {
    if (!canvasRef.current) return undefined;
    const existing = Chart.getChart(canvasRef.current);
    if (existing) existing.destroy();
    const chart = new Chart(canvasRef.current, { type, data, options });
    return () => chart.destroy();
  }, [data, options, type]);

  return <canvas ref={canvasRef} />;
}

function getAcceptanceBarClass(acceptedPct) {
  const value = Number(acceptedPct) || 0;
  if (value >= 80) return "bg-emerald-500/80";
  if (value >= 60) return "bg-amber-500/80";
  return "bg-rose-500/80";
}

function formatDateLabel(value) {
  if (!value) return "--";
  const parsed = parseDateFromBackend(value);
  if (!parsed) return value;
  return parsed.toLocaleDateString();
}

function formatPeriodLabel({ mode, period }) {
  if (!period) return "Current period";
  if (mode === "month") {
    const [year, month] = period.split("-");
    const date = new Date(Number(year), Number(month) - 1, 1);
    return date.toLocaleString(undefined, { month: "long", year: "numeric" });
  }
  if (mode === "year") return period;
  if (mode === "range") {
    const [start, end] = period.split(",");
    return `${start} to ${end}`;
  }
  return period;
}

function buildStatusChartData(counts) {
  return {
    labels: ["Pending", "Rejected", "Returned", "Submitted", "Accepted"],
    datasets: [
      {
        data: [counts.pending, counts.rejected, counts.returned, counts.submitted, counts.accepted],
        backgroundColor: [
          STATUS_COLORS.pending,
          STATUS_COLORS.rejected,
          STATUS_COLORS.returned,
          STATUS_COLORS.submitted,
          STATUS_COLORS.accepted,
        ],
        borderWidth: 0,
      },
    ],
  };
}

function buildTaskStatusCounts(tasks) {
  const counts = {
    Pending: 0,
    Rejected: 0,
    Returned: 0,
    "Submitted to Sales": 0,
    Accepted: 0,
  };
  tasks.forEach((task) => {
    const status = task.status || "";
    if (status.includes("Pending") || status === "Critique" || status === "Raw") counts.Pending += 1;
    else if (status === "Rejected" || status === "Editing") counts.Rejected += 1;
    else if (status === "Returned") counts.Returned += 1;
    else if (status === "Submitted to Sales") counts["Submitted to Sales"] += 1;
    else if (status === "Accepted" || status === "Done") counts.Accepted += 1;
  });
  return counts;
}

function renderTaskList(tasks) {
  if (!tasks.length) {
    return <div className="text-sm text-black/60 dark:text-white/65">No tasks found.</div>;
  }
  return (
    <div className="space-y-3">
      {tasks.map((task) => (
        <div
          key={task.task_number}
          className="rounded-xl border border-black/5 dark:border-white/10 bg-white/60 dark:bg-white/5 p-3"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="text-sm font-semibold text-black/80 dark:text-white/85 truncate">
                #{task.task_number} - {task.brand}
              </div>
              <div className="text-xs text-black/50 dark:text-white/60">
                {task.status} - {task.videographer || "Unassigned"}
              </div>
            </div>
            <div className="text-right text-xs text-black/50 dark:text-white/60">
              <div>Film: {formatDateLabel(task.filming_deadline)}</div>
              <div>Due: {formatDateLabel(task.submission_date)}</div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function renderTasksWithVersions(tasks) {
  if (!tasks.length) {
    return <div className="text-sm text-black/60 dark:text-white/65">No versions found.</div>;
  }
  return (
    <div className="space-y-4">
      {tasks.map((task) => (
        <div key={task.task_number} className="rounded-xl border border-black/5 dark:border-white/10 p-3">
          <div className="text-sm font-semibold text-black/80 dark:text-white/85">
            #{task.task_number} - {task.brand}
          </div>
          <div className="mt-2 space-y-2">
            {(task.versions || []).map((version) => (
              <div key={version.version} className="rounded-lg bg-black/5 dark:bg-white/5 p-2 text-xs">
                <div className="font-semibold">Version {version.version}</div>
                <div className="mt-1 text-black/50 dark:text-white/60">
                  {(version.lifecycle || [])
                    .map((event) => `${event.stage} (${event.at || ""})`)
                    .join(" -> ")}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function renderTasksWithRejections(tasks) {
  if (!tasks.length) {
    return <div className="text-sm text-black/60 dark:text-white/65">No rejection events.</div>;
  }
  return (
    <div className="space-y-4">
      {tasks.map((task) => (
        <div key={task.task_number} className="rounded-xl border border-black/5 dark:border-white/10 p-3">
          <div className="text-sm font-semibold text-black/80 dark:text-white/85">
            #{task.task_number} - {task.brand}
          </div>
          <div className="mt-2 space-y-2">
            {task.rejectionEvents.map((entry, idx) => (
              <div key={`${task.task_number}-${idx}`} className="rounded-lg bg-black/5 dark:bg-white/5 p-2 text-xs">
                <div className="font-semibold">Version {entry.version}</div>
                <div className="text-black/50 dark:text-white/60">
                  {entry.event.rejection_class || "Unclassified"} - {entry.event.rejection_comments || "No notes"}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function renderPendingReviews(reviews) {
  if (!reviews.length) {
    return <div className="text-sm text-black/60 dark:text-white/65">No pending reviews.</div>;
  }

  const grouped = reviews.reduce((acc, review) => {
    const taskNumber = review.task.task_number;
    if (!acc[taskNumber]) {
      acc[taskNumber] = { task: review.task, versions: [] };
    }
    acc[taskNumber].versions.push(review);
    return acc;
  }, {});

  return (
    <div className="space-y-3">
      {Object.values(grouped).map((group) => (
        <AccordionCard
          key={group.task.task_number}
          title={`#${group.task.task_number} - ${group.task.brand}`}
          subtitle={group.task.videographer ? `Videographer: ${group.task.videographer}` : "Videographer: --"}
        >
          {group.versions.map((version) => (
            <div key={`${group.task.task_number}-${version.version.version}`} className="rounded-lg bg-black/5 dark:bg-white/5 p-2">
              <div className="font-semibold">Version {version.version.version}</div>
              <div>Waiting: {version.waitingHours ?? "--"} hrs</div>
              <div>Uploaded: {version.uploadTime ? version.uploadTime.toLocaleString() : "--"}</div>
            </div>
          ))}
        </AccordionCard>
      ))}
    </div>
  );
}

function renderResponseTimes(responseTimes) {
  if (!responseTimes.length) {
    return <div className="text-sm text-black/60 dark:text-white/65">No response data.</div>;
  }

  const grouped = responseTimes.reduce((acc, entry) => {
    const taskNumber = entry.task.task_number;
    if (!acc[taskNumber]) {
      acc[taskNumber] = { task: entry.task, responses: [] };
    }
    acc[taskNumber].responses.push(entry);
    return acc;
  }, {});

  return (
    <div className="space-y-3">
      {Object.values(grouped).map((group) => (
        <AccordionCard
          key={group.task.task_number}
          title={`#${group.task.task_number} - ${group.task.brand}`}
          subtitle={group.task.videographer ? `Videographer: ${group.task.videographer}` : "Videographer: --"}
        >
          {group.responses.map((response, idx) => (
            <div key={`${group.task.task_number}-${idx}`} className="rounded-lg bg-black/5 dark:bg-white/5 p-2">
              <div className="font-semibold">Version {response.version.version}</div>
              <div>Decision: {response.decision}</div>
              <div>Response: {response.responseHours} hrs</div>
              <div>Uploaded: {response.uploadTime ? response.uploadTime.toLocaleString() : "--"}</div>
              <div>Reviewed: {response.reviewTime ? response.reviewTime.toLocaleString() : "--"}</div>
              {response.rejectionClass ? <div>Class: {response.rejectionClass}</div> : null}
              {response.comments ? <div>Notes: {response.comments}</div> : null}
            </div>
          ))}
        </AccordionCard>
      ))}
    </div>
  );
}

export function VideoCritiqueDashboard() {
  const now = new Date();
  const currentYear = now.getFullYear();
  const [dateMode, setDateMode] = useState("month");
  const [selectedYear, setSelectedYear] = useState(currentYear);
  const [selectedMonth, setSelectedMonth] = useState(now.getMonth() + 1);
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const [rangeOpen, setRangeOpen] = useState(false);
  const [detailsType, setDetailsType] = useState(null);
  const [activeVideographer, setActiveVideographer] = useState(null);
  const yearOptions = getYearOptions(currentYear);
  const yearSelectOptions = useMemo(
    () => yearOptions.map((year) => ({ value: year, label: String(year) })),
    [yearOptions]
  );
  const dateModeOptions = useMemo(
    () => [
      { value: "month", label: "Month" },
      { value: "year", label: "Year" },
      { value: "range", label: "Range" },
    ],
    []
  );

  const period = useMemo(() => {
    if (dateMode === "month") {
      return `${selectedYear}-${String(selectedMonth).padStart(2, "0")}`;
    }
    if (dateMode === "year") {
      return `${selectedYear}`;
    }
    if (dateMode === "range" && rangeStart && rangeEnd) {
      return `${rangeStart},${rangeEnd}`;
    }
    return "";
  }, [dateMode, rangeStart, rangeEnd, selectedMonth, selectedYear]);

  const dashboardQuery = useQuery({
    queryKey: ["video-critique", "dashboard", dateMode, period],
    queryFn: () => videoCritiqueApi.getDashboardFull({ mode: dateMode, period }),
  });

  const data = dashboardQuery.data || {};
  const tasks = data.tasks || [];
  const summary = data.summary || {};
  const pie = data.pie || {};
  const reviewer = data.reviewer || {};
  const summaryVideographers =
    data.summary_videographers && Object.keys(data.summary_videographers).length
      ? data.summary_videographers
      : computeSummaryVideographers(tasks);
  const videographers = data.videographers || {};

  const quickStats = useMemo(() => computeQuickStats(tasks), [tasks]);
  const statusCounts = useMemo(() => countVersionStages(tasks), [tasks]);
  const pendingReviews = useMemo(() => getPendingReviews(tasks), [tasks]);
  const responseTimes = useMemo(() => getResponseTimeData(tasks), [tasks]);

  const completionChartData = useMemo(
    () => ({
      labels: ["Completed", "Not Completed"],
      datasets: [
        {
          data: [pie.completed || 0, pie.not_completed || 0],
          backgroundColor: ["rgba(34, 197, 94, 0.7)", "rgba(239, 68, 68, 0.7)"],
          borderWidth: 0,
        },
      ],
    }),
    [pie.completed, pie.not_completed]
  );

  const statusStartedChart = useMemo(() => {
    const started = quickStats.tasksStarted || 0;
    const completed = pie.completed || 0;
    const notCompletedStarted = Math.max(started - completed, 0);
    return {
      labels: ["Completed", "Not Completed"],
      datasets: [
        {
          data: [completed, notCompletedStarted],
          backgroundColor: ["rgba(34, 197, 94, 0.7)", "rgba(239, 68, 68, 0.7)"],
          borderWidth: 0,
        },
      ],
    };
  }, [quickStats.tasksStarted, pie.completed]);

  const statusBarChartData = useMemo(() => buildStatusChartData(statusCounts), [statusCounts]);

  const sortedVideographers = useMemo(() => {
    return Object.entries(summaryVideographers).sort((a, b) => b[1].total - a[1].total);
  }, [summaryVideographers]);

  const detailsOpen = Boolean(detailsType);
  const videographerOpen = Boolean(activeVideographer);
  const activeVideographerStats = activeVideographer ? summaryVideographers[activeVideographer] : null;
  const activeVideographerTasks = activeVideographer ? videographers[activeVideographer] || [] : [];

  const pendingHODVersions = useMemo(() => getTasksWithVersionsInState(tasks, "pending"), [tasks]);
  const pendingHOSVersions = useMemo(() => getTasksWithVersionsInState(tasks, "submitted"), [tasks]);
  const rejectedHODTasks = useMemo(() => getTasksWithRejections(tasks, "hod"), [tasks]);
  const rejectedHOSTasks = useMemo(() => getTasksWithRejections(tasks, "hos"), [tasks]);

  const acceptanceRejectionDist = useMemo(() => {
    const classCounts = {};
    let acceptedCount = 0;
    let rejectedCount = 0;

    tasks.forEach((task) => {
      (task.versions || []).forEach((version) => {
        const lifecycle = version.lifecycle || [];
        if (!lifecycle.length) return;
        const latest = lifecycle[lifecycle.length - 1];
        const latestStage = (latest?.stage || "").toLowerCase();
        if (latestStage === "accepted" || latestStage === "done") {
          acceptedCount += 1;
        }
        if (latestStage === "rejected" || latestStage === "editing" || latestStage === "returned") {
          rejectedCount += 1;
        }
        lifecycle.forEach((event) => {
          const stage = (event.stage || "").toLowerCase();
          if (stage === "rejected" || stage === "editing" || stage === "returned") {
            const key = event.rejection_class || "Unclassified";
            classCounts[key] = (classCounts[key] || 0) + 1;
          }
        });
      });
    });

    const total = acceptedCount + rejectedCount;
    const acceptedPct = total ? ((acceptedCount / total) * 100).toFixed(1) : "0";
    const rejectedPct = total ? ((rejectedCount / total) * 100).toFixed(1) : "0";

    const sortedClasses = Object.entries(classCounts).sort((a, b) => b[1] - a[1]);
    return { acceptedPct, rejectedPct, classes: sortedClasses, totalRejections: rejectedCount };
  }, [tasks]);

  if (dashboardQuery.isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Video Critique Dashboard</CardTitle>
        </CardHeader>
        <CardContent>
          <LoadingEllipsis text="Loading dashboard" className="text-sm text-black/60 dark:text-white/65" />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4 min-h-0 pb-4">
      <div className="flex flex-wrap items-center justify-between gap-3 px-1">
        <div>
          <div className="text-sm font-semibold text-black/80 dark:text-white/85">Video Critique Dashboard</div>
          <div className="text-xs text-black/50 dark:text-white/60">
            {formatPeriodLabel({ mode: dateMode, period })}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SelectDropdown
            value={dateMode}
            options={dateModeOptions}
            onChange={setDateMode}
            className="sm:w-[200px]"
          />

          {dateMode === "month" ? (
            <>
              <SelectDropdown
                value={selectedMonth}
                options={MONTH_OPTIONS}
                onChange={setSelectedMonth}
                className="sm:w-[200px]"
              />
              <SelectDropdown
                value={selectedYear}
                options={yearSelectOptions}
                onChange={setSelectedYear}
                className="sm:w-[200px]"
              />
            </>
          ) : null}

          {dateMode === "year" ? (
            <SelectDropdown
              value={selectedYear}
              options={yearSelectOptions}
              onChange={setSelectedYear}
              className="sm:w-[200px]"
            />
          ) : null}

          {dateMode === "range" ? (
            <Button variant="ghost" className="rounded-2xl" onClick={() => setRangeOpen(true)}>
              <Calendar size={16} className="mr-2" />
              Pick Range
            </Button>
          ) : null}

          <Button variant="ghost" className="rounded-2xl" onClick={() => dashboardQuery.refetch()}>
            <RefreshCw size={16} className="mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <SummaryCard
          icon={Video}
          label="Total Tasks"
          value={summary.total || 0}
          helper="Tasks created"
          accentClass="bg-black/5 dark:bg-white/10 text-black/70 dark:text-white/80"
          onClick={() => setDetailsType("total_created")}
        />
        <SummaryCard
          icon={CheckCircle2}
          label="Assigned"
          value={summary.assigned || 0}
          helper="Assigned to videographers"
          accentClass="bg-blue-500/10 text-blue-700 dark:text-blue-200"
          onClick={() => setDetailsType("total_assigned")}
        />
        <SummaryCard
          icon={Clock}
          label="Tasks Started"
          value={quickStats.tasksStarted || 0}
          helper="Filming date passed"
          accentClass="bg-yellow-500/10 text-yellow-700 dark:text-yellow-200"
          onClick={() => setDetailsType("total_started")}
        />
        <SummaryCard
          icon={AlertTriangle}
          label="Late Tasks"
          value={quickStats.lateTasks || 0}
          helper="Submission overdue"
          accentClass="bg-red-500/10 text-red-700 dark:text-red-200"
          onClick={() => setDetailsType("total_late")}
        />
        <SummaryCard
          icon={Video}
          label="Uploads"
          value={summary.uploads || 0}
          helper="Total versions"
          accentClass="bg-purple-500/10 text-purple-700 dark:text-purple-200"
          onClick={() => setDetailsType("upload_ratio")}
        />
        <SummaryCard
          icon={CheckCircle2}
          label="Completed"
          value={pie.completed || 0}
          helper="Accepted or done"
          accentClass="bg-emerald-500/10 text-emerald-700 dark:text-emerald-200"
          onClick={() => setDetailsType("completed")}
        />
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <SummaryCard
          icon={Clock}
          label="Pending HOD"
          value={quickStats.pendingHOD || 0}
          helper="Versions in critique"
          accentClass="bg-yellow-500/10 text-yellow-700 dark:text-yellow-200"
          onClick={() => setDetailsType("pending_hod")}
        />
        <SummaryCard
          icon={Clock}
          label="Pending HOS"
          value={quickStats.pendingHOS || 0}
          helper="Submitted to sales"
          accentClass="bg-blue-500/10 text-blue-700 dark:text-blue-200"
          onClick={() => setDetailsType("pending_hos")}
        />
        <SummaryCard
          icon={AlertTriangle}
          label="Rejected by HOD"
          value={quickStats.rejectionsByHOD || 0}
          helper="Editing / rejected"
          accentClass="bg-red-500/10 text-red-700 dark:text-red-200"
          onClick={() => setDetailsType("rejected_hod")}
        />
        <SummaryCard
          icon={AlertTriangle}
          label="Rejected by HOS"
          value={quickStats.rejectionsByHOS || 0}
          helper="Returned"
          accentClass="bg-orange-500/10 text-orange-700 dark:text-orange-200"
          onClick={() => setDetailsType("rejected_hos")}
        />
        <SummaryCard
          icon={Video}
          label="Upload Ratio"
          value={quickStats.uploadRatio || "0"}
          helper="Avg versions/task"
          accentClass="bg-black/5 dark:bg-white/10 text-black/70 dark:text-white/80"
          onClick={() => setDetailsType("upload_ratio")}
        />
        <SummaryCard
          icon={CheckCircle2}
          label="Acceptance Rate"
          value={`${summary.accepted_pct || 0}%`}
          helper="Accepted vs reviewed"
          accentClass="bg-emerald-500/10 text-emerald-700 dark:text-emerald-200"
          onClick={() => setDetailsType("acceptance_rate")}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <ChartCard title="Completion Overview">
          <ChartCanvas type="doughnut" data={completionChartData} options={{ maintainAspectRatio: false }} />
        </ChartCard>
        <ChartCard title="Started vs Completed">
          <ChartCanvas type="doughnut" data={statusStartedChart} options={{ maintainAspectRatio: false }} />
        </ChartCard>
        <ChartCard title="Status Distribution">
          <ChartCanvas
            type="bar"
            data={statusBarChartData}
            options={{
              maintainAspectRatio: false,
              indexAxis: "y",
              scales: {
                x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(148,163,184,0.2)" } },
                y: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(148,163,184,0.2)" } },
              },
            }}
          />
        </ChartCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Reviewer Performance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-black/60 dark:text-white/60">Avg response time</span>
                <span className="font-semibold">{reviewer.avg_response_display || "0 hrs"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-black/60 dark:text-white/60">Handled</span>
                <span className="font-semibold">{reviewer.handled || 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-black/60 dark:text-white/60">Accepted by HOS</span>
                <span className="font-semibold">{reviewer.accepted || 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-black/60 dark:text-white/60">Success rate</span>
                <span className="font-semibold">{reviewer.handled_percent || 0}%</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-black/60 dark:text-white/60">Pending reviews</span>
                <span className="font-semibold">{pendingReviews.count || 0}</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <Button
                  variant="secondary"
                  className="rounded-2xl w-full justify-center h-auto py-2 whitespace-normal text-center leading-snug"
                  onClick={() => setDetailsType("response_time")}
                >
                  View response times
                </Button>
                <Button
                  variant="secondary"
                  className="rounded-2xl w-full justify-center h-auto py-2 whitespace-normal text-center leading-snug"
                  onClick={() => setDetailsType("pending_reviews")}
                >
                  View pending reviews
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Videographers</CardTitle>
          </CardHeader>
          <CardContent>
            {sortedVideographers.length ? (
              <div className="grid gap-3 md:grid-cols-2">
                {sortedVideographers.map(([name, stats]) => (
                  <div
                    key={name}
                    className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/60 dark:bg-white/5 p-4 cursor-pointer hover:shadow-md transition-shadow"
                    onClick={() => setActiveVideographer(name)}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm font-semibold text-black/80 dark:text-white/85">{name}</div>
                        <div className="text-xs text-black/50 dark:text-white/60">{stats.total} tasks</div>
                      </div>
                      <div className="text-right">
                        <div className="text-lg font-semibold">{stats.accepted_pct}%</div>
                        <div className="text-xs text-black/50 dark:text-white/60">Acceptance</div>
                      </div>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-black/60 dark:text-white/60">
                      <div>Started: {stats.started}</div>
                      <div>Late: {stats.late}</div>
                      <div>Completed: {stats.completed}</div>
                      <div>Uploads: {stats.uploads}</div>
                    </div>
                    <div className="mt-3 h-2 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
                      <div
                        className={`h-full ${getAcceptanceBarClass(stats.accepted_pct)}`}
                        style={{ width: `${stats.accepted_pct}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-black/60 dark:text-white/65">No videographer data.</div>
            )}
          </CardContent>
        </Card>
      </div>

      <Modal
        open={detailsOpen}
        onClose={() => setDetailsType(null)}
        title="Details"
        maxWidth="820px"
      >
        {detailsType === "total_created" ? renderTaskList(tasks) : null}
        {detailsType === "total_assigned" ? renderTaskList(tasks.filter((task) => task.status !== "Not assigned yet")) : null}
        {detailsType === "total_started" ? (
          renderTaskList(
            tasks.filter((task) => {
              const filmingDate = parseDateFromBackend(task.filming_deadline || "");
              if (!filmingDate) return false;
              const today = new Date();
              today.setHours(0, 0, 0, 0);
              return filmingDate <= today;
            })
          )
        ) : null}
        {detailsType === "total_late" ? renderTaskList(tasks.filter(isTaskOverdue)) : null}
        {detailsType === "completed" ? renderTaskList(tasks.filter((task) => task.status === "Accepted" || task.status === "Done")) : null}
        {detailsType === "pending_hod" ? renderTasksWithVersions(pendingHODVersions.map((entry) => ({
          ...entry.task,
          versions: [entry.version],
        }))) : null}
        {detailsType === "pending_hos" ? renderTasksWithVersions(pendingHOSVersions.map((entry) => ({
          ...entry.task,
          versions: [entry.version],
        }))) : null}
        {detailsType === "rejected_hod" ? renderTasksWithRejections(rejectedHODTasks) : null}
        {detailsType === "rejected_hos" ? renderTasksWithRejections(rejectedHOSTasks) : null}
        {detailsType === "upload_ratio" ? renderTasksWithVersions(tasks.filter((task) => task.versions?.length)) : null}
        {detailsType === "acceptance_rate" ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <SoftCard className="p-4 text-center">
                <div className="text-2xl font-semibold text-emerald-600">{acceptanceRejectionDist.acceptedPct}%</div>
                <div className="text-xs text-black/50 dark:text-white/60">Acceptance</div>
              </SoftCard>
              <SoftCard className="p-4 text-center">
                <div className="text-2xl font-semibold text-red-600">{acceptanceRejectionDist.rejectedPct}%</div>
                <div className="text-xs text-black/50 dark:text-white/60">Rejection</div>
              </SoftCard>
            </div>
            <div>
              <div className="text-sm font-semibold text-black/70 dark:text-white/70 mb-2">Rejection classes</div>
              {acceptanceRejectionDist.classes.length ? (
                <div className="space-y-2">
                  {acceptanceRejectionDist.classes.map(([label, count]) => (
                    <div key={label} className="rounded-lg bg-black/5 dark:bg-white/5 p-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span>{label}</span>
                        <span>{count}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-black/60 dark:text-white/65">No rejection data.</div>
              )}
            </div>
          </div>
        ) : null}
        {detailsType === "response_time" ? renderResponseTimes(responseTimes) : null}
        {detailsType === "pending_reviews" ? renderPendingReviews(pendingReviews.reviews || []) : null}
      </Modal>

      <Modal
        open={videographerOpen}
        onClose={() => setActiveVideographer(null)}
        title={activeVideographer ? `${activeVideographer} Details` : "Videographer"}
        maxWidth="980px"
      >
        {activeVideographer && activeVideographerStats ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <SoftCard className="p-4 text-center">
                <div className="text-2xl font-semibold">{activeVideographerStats.accepted_pct}%</div>
                <div className="text-xs text-black/50 dark:text-white/60">Acceptance rate</div>
              </SoftCard>
              <SoftCard className="p-4 text-center">
                <div className="text-2xl font-semibold">{activeVideographerStats.late}</div>
                <div className="text-xs text-black/50 dark:text-white/60">Late tasks</div>
              </SoftCard>
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              <SummaryCard
                icon={Clock}
                label="Pending"
                value={countVersionStages(activeVideographerTasks).pending}
                accentClass="bg-yellow-500/10 text-yellow-700 dark:text-yellow-200"
              />
              <SummaryCard
                icon={AlertTriangle}
                label="Rejected"
                value={countVersionStages(activeVideographerTasks).rejected}
                accentClass="bg-red-500/10 text-red-700 dark:text-red-200"
              />
              <SummaryCard
                icon={CheckCircle2}
                label="Accepted"
                value={countVersionStages(activeVideographerTasks).accepted}
                accentClass="bg-emerald-500/10 text-emerald-700 dark:text-emerald-200"
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <ChartCard title="Version Distribution">
                <ChartCanvas
                  type="bar"
                  data={buildStatusChartData(countVersionStages(activeVideographerTasks))}
                  options={{ maintainAspectRatio: false, indexAxis: "y" }}
                />
              </ChartCard>
              <ChartCard title="All Tasks Status">
                <ChartCanvas
                  type="pie"
                  data={{
                    labels: Object.keys(buildTaskStatusCounts(activeVideographerTasks)),
                    datasets: [
                      {
                        data: Object.values(buildTaskStatusCounts(activeVideographerTasks)),
                        backgroundColor: [
                          STATUS_COLORS.pending,
                          STATUS_COLORS.rejected,
                          STATUS_COLORS.returned,
                          STATUS_COLORS.submitted,
                          STATUS_COLORS.accepted,
                        ],
                        borderWidth: 0,
                      },
                    ],
                  }}
                  options={{ maintainAspectRatio: false }}
                />
              </ChartCard>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <ChartCard title="Overdue Tasks">
                <ChartCanvas
                  type="pie"
                  data={{
                    labels: Object.keys(buildTaskStatusCounts(activeVideographerTasks.filter(isTaskOverdue))),
                    datasets: [
                      {
                        data: Object.values(buildTaskStatusCounts(activeVideographerTasks.filter(isTaskOverdue))),
                        backgroundColor: [
                          STATUS_COLORS.pending,
                          STATUS_COLORS.rejected,
                          STATUS_COLORS.returned,
                          STATUS_COLORS.submitted,
                          STATUS_COLORS.accepted,
                        ],
                        borderWidth: 0,
                      },
                    ],
                  }}
                  options={{ maintainAspectRatio: false }}
                />
              </ChartCard>
              <Card>
                <CardHeader>
                  <CardTitle>Failure Analysis</CardTitle>
                </CardHeader>
                <CardContent>
                  {renderTasksWithRejections(getTasksWithRejections(activeVideographerTasks, "hod"))}
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle>Version History</CardTitle>
              </CardHeader>
              <CardContent>{renderTasksWithVersions(activeVideographerTasks)}</CardContent>
            </Card>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={rangeOpen}
        onClose={() => setRangeOpen(false)}
        title="Select date range"
        maxWidth="520px"
      >
        <div className="space-y-4">
          <div className="grid gap-3">
            <label className="text-xs text-black/60 dark:text-white/60">Start date</label>
            <input
              type="date"
              value={rangeStart}
              onChange={(e) => setRangeStart(e.target.value)}
              className="rounded-2xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-xs"
            />
          </div>
          <div className="grid gap-3">
            <label className="text-xs text-black/60 dark:text-white/60">End date</label>
            <input
              type="date"
              value={rangeEnd}
              onChange={(e) => setRangeEnd(e.target.value)}
              className="rounded-2xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-3 py-2 text-xs"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" className="rounded-2xl" onClick={() => setRangeOpen(false)}>
              Cancel
            </Button>
            <Button className="rounded-2xl" onClick={() => setRangeOpen(false)}>
              Apply
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
