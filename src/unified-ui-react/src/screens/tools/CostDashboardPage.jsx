import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Chart,
  ArcElement,
  BarElement,
  CategoryScale,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from "chart.js";
import {
  BarChart3,
  Calendar,
  Coins,
  DollarSign,
  Hash,
  LineChart,
  PieChart,
  User,
} from "lucide-react";

import { costsApi } from "../../api";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { FormField } from "../../components/ui/form-field";
import { LoadingEllipsis } from "../../components/ui/loading-ellipsis";
import { Modal } from "../../components/ui/modal";
import { SoftCard } from "../../components/ui/soft-card";
import { canAccessAdmin, hasPermission, useAuth } from "../../state/auth";

Chart.register(
  ArcElement,
  BarElement,
  CategoryScale,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip
);

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const CHART_COLORS = [
  "#3b82f6",
  "#6366f1",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#14b8a6",
  "#ec4899",
  "#0ea5e9",
  "#22c55e",
];

function formatDateLabel(date) {
  if (!date) return "";
  return `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}

function toDateParam(date) {
  if (!date) return "";
  return date.toISOString().split("T")[0];
}

function getLast7DaysRange() {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 6);
  return { start, end };
}

function SummaryCard({ icon: Icon, label, value, accentClass }) {
  return (
    <SoftCard className="p-4">
      <div className="flex items-center justify-between gap-3">
        <div className={`h-10 w-10 rounded-xl flex items-center justify-center ${accentClass}`}>
          <Icon size={18} />
        </div>
        <div className="text-2xl font-semibold">{value}</div>
      </div>
      <div className="mt-2 text-xs text-black/55 dark:text-white/60">{label}</div>
    </SoftCard>
  );
}

function ChartCard({ title, icon: Icon, children }) {
  return (
    <SoftCard className="p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-black/80 dark:text-white/85">
        <Icon size={16} className="text-black/50 dark:text-white/50" />
        {title}
      </div>
      <div className="mt-3 h-[320px]">{children}</div>
    </SoftCard>
  );
}

function ChartCanvas({ type, data, options }) {
  const canvasRef = React.useRef(null);

  React.useEffect(() => {
    if (!canvasRef.current) return;
    const chart = new Chart(canvasRef.current, { type, data, options });
    return () => chart.destroy();
  }, [data, options, type]);

  return <canvas ref={canvasRef} />;
}

export function CostDashboardPage() {
  const { user } = useAuth();
  const canViewCosts = hasPermission(user, "core:ai_costs:read") || canAccessAdmin(user);
  const [dateMode, setDateMode] = useState("month");
  const now = new Date();
  const [selectedYear, setSelectedYear] = useState(now.getFullYear());
  const [selectedMonth, setSelectedMonth] = useState(now.getMonth());
  const [rangeStart, setRangeStart] = useState(null);
  const [rangeEnd, setRangeEnd] = useState(null);
  const [rangePicking, setRangePicking] = useState("start");
  const [dateModalOpen, setDateModalOpen] = useState(false);

  const rangeValues = useMemo(() => {
    if (dateMode === "month") {
      return {
        start: new Date(selectedYear, selectedMonth, 1),
        end: new Date(selectedYear, selectedMonth + 1, 0),
      };
    }
    if (dateMode === "year") {
      return {
        start: new Date(selectedYear, 0, 1),
        end: new Date(selectedYear, 11, 31),
      };
    }
    if (dateMode === "range" && rangeStart && rangeEnd) {
      return { start: rangeStart, end: rangeEnd };
    }
    return getLast7DaysRange();
  }, [dateMode, rangeEnd, rangeStart, selectedMonth, selectedYear]);

  const dateLabel = useMemo(() => {
    if (dateMode === "month") {
      return `${MONTHS[selectedMonth]} ${selectedYear}`;
    }
    if (dateMode === "year") {
      return `${selectedYear}`;
    }
    if (dateMode === "range" && rangeStart && rangeEnd) {
      return `${formatDateLabel(rangeStart)} - ${formatDateLabel(rangeEnd)}`;
    }
    return "Last 7 Days";
  }, [dateMode, rangeEnd, rangeStart, selectedMonth, selectedYear]);

  const startDate = toDateParam(rangeValues.start);
  const endDate = toDateParam(rangeValues.end);

  const costsQuery = useQuery({
    queryKey: ["costs", startDate, endDate],
    queryFn: () => costsApi.getCosts({ startDate, endDate }),
    enabled: canViewCosts,
  });

  if (!canViewCosts) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Restricted</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-black/60 dark:text-white/65">
          You don&apos;t have access to the cost dashboard.
        </CardContent>
      </Card>
    );
  }

  const summary = costsQuery.data?.summary || {};
  const totalCost = summary.total_cost || 0;
  const totalCalls = summary.total_calls || 0;
  const avgCost = totalCalls ? totalCost / totalCalls : 0;
  const totalInput = summary.total_input_tokens || 0;
  const cachedInput = summary.total_cached_tokens || 0;
  const cacheRate = totalInput ? (cachedInput / totalInput) * 100 : 0;

  const callTypeData = useMemo(() => {
    const byCallType = summary.by_call_type || {};
    return {
      labels: Object.keys(byCallType).map((k) => k.replaceAll("_", " ")),
      datasets: [
        {
          data: Object.values(byCallType).map((v) => v.cost || 0),
          backgroundColor: CHART_COLORS,
          borderWidth: 0,
        },
      ],
    };
  }, [summary.by_call_type]);

  const workflowData = useMemo(() => {
    const byWorkflow = summary.by_workflow || {};
    return {
      labels: Object.keys(byWorkflow).map((k) => (k ? k.replaceAll("_", " ") : "unclassified")),
      datasets: [
        {
          data: Object.values(byWorkflow).map((v) => v.cost || 0),
          backgroundColor: CHART_COLORS,
          borderWidth: 0,
        },
      ],
    };
  }, [summary.by_workflow]);

  const timelineData = useMemo(() => {
    const dailyCosts = summary.daily_costs || [];
    return {
      labels: dailyCosts.map((d) => d.date),
      datasets: [
        {
          label: "Daily Cost",
          data: dailyCosts.map((d) => d.cost || 0),
          borderColor: "#3b82f6",
          backgroundColor: "rgba(59, 130, 246, 0.15)",
          fill: true,
          tension: 0.4,
          borderWidth: 2,
        },
      ],
    };
  }, [summary.daily_costs]);

  const tokenData = useMemo(() => {
    const totalOutput = summary.total_output_tokens || 0;
    const totalReasoning = summary.total_reasoning_tokens || 0;
    const uncachedInput = totalInput - cachedInput;
    return {
      labels: ["Input Tokens", "Output Tokens", "Reasoning Tokens"],
      datasets: [
        {
          label: "Uncached Input",
          data: [uncachedInput, 0, 0],
          backgroundColor: "#3b82f6",
          borderWidth: 0,
        },
        {
          label: "Cached Input",
          data: [cachedInput, 0, 0],
          backgroundColor: "#10b981",
          borderWidth: 0,
        },
        {
          label: "Output",
          data: [0, totalOutput, 0],
          backgroundColor: "#f59e0b",
          borderWidth: 0,
        },
        {
          label: "Reasoning",
          data: [0, 0, totalReasoning],
          backgroundColor: "#6366f1",
          borderWidth: 0,
        },
      ],
    };
  }, [cachedInput, summary.total_output_tokens, summary.total_reasoning_tokens, totalInput]);

  const recentCalls = summary.calls || [];
  const byUser = summary.by_user || {};

  function handleRangePick(year, month, day) {
    const date = new Date(year, month, day);
    if (rangePicking === "start") {
      setRangeStart(date);
      setRangeEnd(null);
      setRangePicking("end");
      return;
    }
    if (rangeStart && date >= rangeStart) {
      setRangeEnd(date);
    } else {
      setRangeStart(date);
      setRangeEnd(null);
      setRangePicking("end");
    }
  }

  function renderMonthPicker() {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <Button variant="ghost" size="sm" className="rounded-xl" onClick={() => setSelectedYear((y) => y - 1)}>
            Prev
          </Button>
          <div className="text-sm font-semibold">{selectedYear}</div>
          <Button variant="ghost" size="sm" className="rounded-xl" onClick={() => setSelectedYear((y) => y + 1)}>
            Next
          </Button>
        </div>
        <div className="grid grid-cols-3 gap-2">
          {MONTHS.map((month, index) => {
            const active = index === selectedMonth;
            return (
              <button
                key={month}
                type="button"
                onClick={() => setSelectedMonth(index)}
                className={`rounded-xl px-3 py-2 text-sm font-semibold transition ${
                  active
                    ? "bg-black text-white dark:bg-white dark:text-black"
                    : "bg-black/5 dark:bg-white/10 text-black/70 dark:text-white/70 hover:bg-black/10 dark:hover:bg-white/15"
                }`}
              >
                {month}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  function renderYearPicker() {
    const current = new Date().getFullYear();
    const years = [];
    for (let y = current - 5; y <= current + 5; y += 1) years.push(y);
    return (
      <div className="grid grid-cols-3 gap-2">
        {years.map((year) => {
          const active = year === selectedYear;
          return (
            <button
              key={year}
              type="button"
              onClick={() => setSelectedYear(year)}
              className={`rounded-xl px-3 py-2 text-sm font-semibold transition ${
                active
                  ? "bg-black text-white dark:bg-white dark:text-black"
                  : "bg-black/5 dark:bg-white/10 text-black/70 dark:text-white/70 hover:bg-black/10 dark:hover:bg-white/15"
              }`}
            >
              {year}
            </button>
          );
        })}
      </div>
    );
  }

  function renderRangePicker() {
    const firstDay = new Date(selectedYear, selectedMonth, 1).getDay();
    const daysInMonth = new Date(selectedYear, selectedMonth + 1, 0).getDate();
    const blanks = Array.from({ length: firstDay }, (_, i) => i);

    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <Button
            variant="ghost"
            size="sm"
            className="rounded-xl"
            onClick={() => {
              const next = selectedMonth - 1;
              if (next < 0) {
                setSelectedMonth(11);
                setSelectedYear((y) => y - 1);
              } else {
                setSelectedMonth(next);
              }
            }}
          >
            Prev
          </Button>
          <div className="text-sm font-semibold">
            {MONTHS[selectedMonth]} {selectedYear}
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="rounded-xl"
            onClick={() => {
              const next = selectedMonth + 1;
              if (next > 11) {
                setSelectedMonth(0);
                setSelectedYear((y) => y + 1);
              } else {
                setSelectedMonth(next);
              }
            }}
          >
            Next
          </Button>
        </div>
        <div className="grid grid-cols-7 gap-2 text-xs text-black/50 dark:text-white/55">
          {WEEKDAYS.map((day) => (
            <div key={day} className="text-center font-semibold">
              {day}
            </div>
          ))}
          {blanks.map((idx) => (
            <div key={`blank-${idx}`} />
          ))}
          {Array.from({ length: daysInMonth }, (_, i) => {
            const day = i + 1;
            const date = new Date(selectedYear, selectedMonth, day);
            const isStart = rangeStart && date.toDateString() === rangeStart.toDateString();
            const isEnd = rangeEnd && date.toDateString() === rangeEnd.toDateString();
            const inRange =
              rangeStart && rangeEnd && date >= rangeStart && date <= rangeEnd;
            let classes =
              "rounded-lg px-2 py-1 text-xs font-semibold transition bg-black/5 dark:bg-white/10 text-black/70 dark:text-white/70 hover:bg-black/10 dark:hover:bg-white/15";
            if (isStart || isEnd) {
              classes = "rounded-lg px-2 py-1 text-xs font-semibold bg-black text-white dark:bg-white dark:text-black";
            } else if (inRange) {
              classes = "rounded-lg px-2 py-1 text-xs font-semibold bg-black/10 dark:bg-white/20 text-black dark:text-white";
            }
            return (
              <button
                key={`day-${day}`}
                type="button"
                className={classes}
                onClick={() => handleRangePick(selectedYear, selectedMonth, day)}
              >
                {day}
              </button>
            );
          })}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs text-black/60 dark:text-white/60">
          <SoftCard className="p-3">
            <div className="font-semibold text-black/70 dark:text-white/70">Start Date</div>
            <div className="mt-1">{rangeStart ? formatDateLabel(rangeStart) : "Not selected"}</div>
          </SoftCard>
          <SoftCard className="p-3">
            <div className="font-semibold text-black/70 dark:text-white/70">End Date</div>
            <div className="mt-1">{rangeEnd ? formatDateLabel(rangeEnd) : "Not selected"}</div>
          </SoftCard>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full min-h-0 flex flex-col">
      <div className="flex-1 min-h-0 overflow-y-auto space-y-4 px-2 py-1">
        <SoftCard className="p-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-lg font-semibold">AI Costs Dashboard</div>
            <div className="text-xs text-black/50 dark:text-white/60">Real-time analytics & monitoring</div>
          </div>
          <div className="flex items-center gap-2 text-xs text-black/60 dark:text-white/60">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            Live
          </div>
        </SoftCard>

        <SoftCard className="p-4">
          <FormField label="Date Range">
            <Button
              type="button"
              variant="secondary"
              className="w-full justify-between rounded-2xl"
              onClick={() => setDateModalOpen(true)}
            >
              <span>{dateLabel}</span>
              <Calendar size={16} />
            </Button>
          </FormField>
        </SoftCard>

        {costsQuery.isLoading ? (
          <SoftCard className="p-6">
            <LoadingEllipsis text="Loading dashboard data" className="text-sm text-black/60 dark:text-white/65" />
          </SoftCard>
        ) : costsQuery.isError ? (
          <SoftCard className="p-6 text-center space-y-3">
            <div className="text-base font-semibold">Failed to load data</div>
            <div className="text-sm text-black/60 dark:text-white/65">
              {costsQuery.error?.message || "Unable to fetch costs data."}
            </div>
            <Button className="rounded-2xl" onClick={() => costsQuery.refetch()}>
              Try Again
            </Button>
          </SoftCard>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
              <SummaryCard
                icon={DollarSign}
                label="Total Cost"
                value={`$${totalCost.toFixed(4)}`}
                accentClass="bg-blue-500/10 text-blue-500"
              />
              <SummaryCard
                icon={Coins}
                label="Average Cost per Call"
                value={`$${avgCost.toFixed(4)}`}
                accentClass="bg-purple-500/10 text-purple-500"
              />
              <SummaryCard
                icon={Hash}
                label="Total API Calls"
                value={totalCalls.toLocaleString()}
                accentClass="bg-emerald-500/10 text-emerald-500"
              />
              <SummaryCard
                icon={BarChart3}
                label="Cache Hit Rate"
                value={`${cacheRate.toFixed(1)}%`}
                accentClass="bg-amber-500/10 text-amber-500"
              />
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
              <ChartCard title="Costs by Call Type" icon={PieChart}>
                <ChartCanvas
                  type="doughnut"
                  data={callTypeData}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                      legend: {
                        position: "bottom",
                        labels: { color: "#94a3b8", padding: 12 },
                      },
                      tooltip: {
                        callbacks: {
                          label: (context) => {
                            const label = context.label || "";
                            const value = context.parsed || 0;
                            return `${label}: $${Number(value).toFixed(4)}`;
                          },
                        },
                      },
                    },
                  }}
                />
              </ChartCard>
              <ChartCard title="Costs by Workflow" icon={PieChart}>
                <ChartCanvas
                  type="doughnut"
                  data={workflowData}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                      legend: {
                        position: "bottom",
                        labels: { color: "#94a3b8", padding: 12 },
                      },
                      tooltip: {
                        callbacks: {
                          label: (context) => {
                            const label = context.label || "";
                            const value = context.parsed || 0;
                            return `${label}: $${Number(value).toFixed(4)}`;
                          },
                        },
                      },
                    },
                  }}
                />
              </ChartCard>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
              <ChartCard title="Daily Cost Timeline" icon={LineChart}>
                <ChartCanvas
                  type="line"
                  data={timelineData}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                      y: { beginAtZero: true, ticks: { color: "#94a3b8" }, grid: { color: "#e2e8f0" } },
                      x: { ticks: { color: "#94a3b8" }, grid: { display: false } },
                    },
                  }}
                />
              </ChartCard>
              <ChartCard title="Token Usage" icon={BarChart3}>
                <ChartCanvas
                  type="bar"
                  data={tokenData}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                      legend: { position: "bottom", labels: { color: "#94a3b8", padding: 12 } },
                      tooltip: {
                        callbacks: {
                          label: (context) =>
                            `${context.dataset.label}: ${Number(context.parsed.y).toLocaleString()} tokens`,
                        },
                      },
                    },
                    scales: {
                      y: { beginAtZero: true, stacked: true, ticks: { color: "#94a3b8" }, grid: { color: "#e2e8f0" } },
                      x: { stacked: true, ticks: { color: "#94a3b8" }, grid: { display: false } },
                    },
                  }}
                />
              </ChartCard>
            </div>

            <SoftCard className="p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-black/80 dark:text-white/85">
                <User size={16} className="text-black/50 dark:text-white/50" />
                Per-Salesperson Breakdown
              </div>
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                {Object.keys(byUser).length ? (
                  Object.entries(byUser).map(([userId, stats]) => (
                    <SoftCard key={userId} className="p-4">
                      <div className="flex items-center justify-between">
                        <div className="h-9 w-9 rounded-xl bg-purple-500/10 text-purple-500 flex items-center justify-center">
                          <User size={16} />
                        </div>
                        <div className="text-lg font-semibold text-emerald-500">
                          ${Number(stats.cost || 0).toFixed(4)}
                        </div>
                      </div>
                      <div className="mt-2 text-sm font-semibold">{userId}</div>
                      <div className="mt-2 flex items-center justify-between text-xs text-black/55 dark:text-white/60">
                        <span>{stats.calls || 0} calls</span>
                        <span>{Number(stats.tokens || 0).toLocaleString()} tokens</span>
                      </div>
                    </SoftCard>
                  ))
                ) : (
                  <div className="text-sm text-black/60 dark:text-white/65">No user data available.</div>
                )}
              </div>
            </SoftCard>

            <SoftCard className="p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-black/80 dark:text-white/85">
                <BarChart3 size={16} className="text-black/50 dark:text-white/50" />
                Recent API Calls
              </div>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-black/5 dark:border-white/10 text-black/50 dark:text-white/60">
                      <th className="text-left py-2 px-3 font-semibold">Timestamp</th>
                      <th className="text-left py-2 px-3 font-semibold">User</th>
                      <th className="text-left py-2 px-3 font-semibold">Call Type</th>
                      <th className="text-left py-2 px-3 font-semibold">Workflow</th>
                      <th className="text-left py-2 px-3 font-semibold">Model</th>
                      <th className="text-right py-2 px-3 font-semibold">Tokens</th>
                      <th className="text-right py-2 px-3 font-semibold">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(recentCalls || []).slice(0, 50).map((call) => {
                      const timestamp = call.timestamp ? new Date(call.timestamp).toLocaleString() : "—";
                      const userName = call.user_id || "-";
                      const callType = call.call_type ? call.call_type.replaceAll("_", " ") : "-";
                      const workflow = call.workflow ? call.workflow.replaceAll("_", " ") : "-";
                      const model = call.model || "-";
                      const tokens = `${call.input_tokens || 0} + ${call.output_tokens || 0}${
                        call.cached_input_tokens ? ` (${call.cached_input_tokens} cached)` : ""
                      }`;
                      const cost = call.total_cost != null ? `$${Number(call.total_cost).toFixed(4)}` : "-";

                      return (
                        <tr key={call.id || `${call.timestamp}-${userName}`} className="border-b border-black/5 dark:border-white/10">
                          <td className="py-2 px-3">{timestamp}</td>
                          <td className="py-2 px-3 text-black/70 dark:text-white/75">{userName}</td>
                          <td className="py-2 px-3">
                            <span className="rounded-full bg-blue-500/10 text-blue-500 px-2 py-0.5 text-xs">
                              {callType}
                            </span>
                          </td>
                          <td className="py-2 px-3">
                            <span className="rounded-full bg-purple-500/10 text-purple-500 px-2 py-0.5 text-xs">
                              {workflow}
                            </span>
                          </td>
                          <td className="py-2 px-3 text-black/70 dark:text-white/75">{model}</td>
                          <td className="py-2 px-3 text-right text-black/70 dark:text-white/75">{tokens}</td>
                          <td className="py-2 px-3 text-right font-semibold text-emerald-500">{cost}</td>
                        </tr>
                      );
                    })}
                    {!recentCalls?.length ? (
                      <tr>
                        <td colSpan={7} className="py-6 text-center text-black/50 dark:text-white/60">
                          No API calls recorded yet.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </SoftCard>
          </>
        )}
      </div>

      <Modal open={dateModalOpen} onClose={() => setDateModalOpen(false)} title="Select Date Range" maxWidth="720px">
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-2">
            {[
              { key: "month", label: "Month" },
              { key: "year", label: "Year" },
              { key: "range", label: "Range" },
            ].map((mode) => (
              <button
                key={mode.key}
                type="button"
                onClick={() => {
                  setDateMode(mode.key);
                  if (mode.key === "range") {
                    setRangeStart(null);
                    setRangeEnd(null);
                    setRangePicking("start");
                  }
                }}
                className={`rounded-xl px-3 py-2 text-sm font-semibold transition ${
                  dateMode === mode.key
                    ? "bg-black text-white dark:bg-white dark:text-black"
                    : "bg-black/5 dark:bg-white/10 text-black/70 dark:text-white/70 hover:bg-black/10 dark:hover:bg-white/15"
                }`}
              >
                {mode.label}
              </button>
            ))}
          </div>

          {dateMode === "month" ? renderMonthPicker() : null}
          {dateMode === "year" ? renderYearPicker() : null}
          {dateMode === "range" ? renderRangePicker() : null}

          <div className="flex justify-end gap-2">
            <Button variant="ghost" className="rounded-2xl" onClick={() => setDateModalOpen(false)}>
              Close
            </Button>
            <Button className="rounded-2xl" onClick={() => setDateModalOpen(false)}>
              Apply
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
