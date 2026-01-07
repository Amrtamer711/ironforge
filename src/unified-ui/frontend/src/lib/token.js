const KEY = "authToken";

export function getAuthToken() {
  return localStorage.getItem(KEY);
}

export function setAuthToken(token) {
  if (token) localStorage.setItem(KEY, token);
}

export function clearAuthToken() {
  localStorage.removeItem(KEY);
}
