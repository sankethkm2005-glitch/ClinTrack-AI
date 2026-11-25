/**
 * Shared Vanilla JS API client and Phase 1 health-check initializer.
 */

const API_BASE = "/api";

async function apiRequest(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  // Attach CSRF token for mutating requests if stored
  const csrfToken = localStorage.getItem("clintrace_csrf");
  if (csrfToken && ["POST", "PUT", "PATCH", "DELETE"].includes((options.method || "").toUpperCase())) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers,
    ...options,
  });

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail = typeof data === "object" && data?.detail ? data.detail : response.statusText;
    throw new Error(detail || "Request failed");
  }

  return data;
}

async function checkSystemHealth() {
  const badge = document.getElementById("health-badge");
  const detail = document.getElementById("health-detail");
  if (!badge || !detail) return;

  try {
    const data = await apiRequest("/health");
    badge.textContent = data.status === "ok" ? "Online" : "Degraded";
    badge.className = `badge ${data.status === "ok" ? "badge-success" : "badge-error"}`;
    detail.textContent = `Database: ${data.database} | Environment: ${data.environment} | AI provider: ${data.ai_provider}`;
  } catch (err) {
    badge.textContent = "Offline";
    badge.className = "badge badge-error";
    detail.textContent = `Could not reach backend (/api/health): ${err.message}`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide && typeof window.lucide.createIcons === "function") {
    window.lucide.createIcons();
  }
  checkSystemHealth();
});
