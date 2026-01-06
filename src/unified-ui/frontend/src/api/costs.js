import { apiRequest } from "./http";
import { runtimeConfig } from "../lib/runtimeConfig";

export async function getCosts({ startDate, endDate, userId, callType, workflow } = {}) {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  if (userId) params.set("user_id", userId);
  if (callType) params.set("call_type", callType);
  if (workflow) params.set("workflow", workflow);
  const query = params.toString();
  const path = `/costs${query ? `?${query}` : ""}`;
  const baseUrl = runtimeConfig.COSTS_BASE_URL || "http://localhost:8000";
  return apiRequest(path, { baseUrl });
}
