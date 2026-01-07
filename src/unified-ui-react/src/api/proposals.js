import { apiRequest } from "./http";
import { getLocations, getLocationByKey } from "./locations";

export async function generate(data) {
  return apiRequest("/api/sales/proposals", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export { getLocations, getLocationByKey };

export async function getHistory() {
  return apiRequest("/api/sales/proposals/history");
}
