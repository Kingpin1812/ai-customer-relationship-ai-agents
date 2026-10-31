const TOKEN_KEY = "workflow.session";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly category: string,
    message: string,
    readonly correlationId: string | null = null,
    readonly details: unknown = null,
  ) {
    super(message);
  }
}

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage blocked: the session lasts until the page reloads.
  }
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "network", "The server could not be reached. Check that it is running.");
  }
  if (response.ok) return response;

  if (response.status === 401 && token) {
    setToken(null);
    // Outside React on purpose: any request anywhere can end the session.
    if (!window.location.pathname.startsWith("/login")) window.location.assign("/login?expired=1");
  }
  let category = "unknown";
  let message = "Something went wrong. Please try again.";
  let correlationId: string | null = null;
  let details: unknown = null;
  try {
    const { error } = await response.json();
    category = error.category;
    message = error.message;
    correlationId = error.correlation_id;
    details = error.details ?? null;
    if (Array.isArray(details) && details.length > 0) {
      message = details.map((d: { message: string }) => d.message.replace(/^Value error, /, "")).join(" ");
    }
  } catch {
    // Not one of our JSON errors, usually the dev proxy with the API down.
    if (response.status >= 500) message = "The server could not be reached. Check that it is running.";
  }
  throw new ApiError(response.status, category, message, correlationId, details);
}

export async function apiGet<T>(path: string): Promise<T> {
  return (await send(path)).json();
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method: "POST" };
  if (body !== undefined) init.body = JSON.stringify(body);
  return (await send(path, init)).json();
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return (await send(path, { method: "PATCH", body: JSON.stringify(body) })).json();
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  return (await send(path, { method: "POST", body: form })).json();
}

export async function fetchArtifactBlob(artifactId: string): Promise<Blob> {
  return (await send(`/artifacts/${artifactId}/download`)).blob();
}

export async function downloadArtifact(artifactId: string, filename: string) {
  const url = URL.createObjectURL(await fetchArtifactBlob(artifactId));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
