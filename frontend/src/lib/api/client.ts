import type {
  AlertCreate,
  AlertRead,
  AlertRunResult,
  AlertUpdate,
  ApiErrorPayload,
  BookmarkRead,
  ChatRead,
  EmbeddingRequest,
  JobRead,
  NotificationRead,
  OperationRead,
  ProfileCreate,
  ProfileRead,
  ResumeRead,
  SearchRequest,
  SearchResult,
} from "./types";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1"
).replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(
    message: string,
    status: number,
    detail: unknown,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  } catch (error) {
    throw new ApiError(
      error instanceof Error ? error.message : "Could not reach the API",
      0,
      null,
    );
  }

  if (response.status === 204) return undefined as T;

  const payload = (await response.json().catch(() => null)) as ApiErrorPayload | T | null;
  if (!response.ok) {
    const detail = payload && typeof payload === "object" && "detail" in payload
      ? payload.detail
      : payload;
    const message = typeof detail === "string"
      ? detail
      : `API request failed (${response.status})`;
    throw new ApiError(message, response.status, detail);
  }

  return payload as T;
}

const profilePath = (profileName: string) => `/profiles/${encodeURIComponent(profileName)}`;
const jobPath = (jobId: string) => encodeURIComponent(jobId);

export const api = {
  getProfiles: () => request<ProfileRead[]>("/profiles"),
  createProfile: (body: ProfileCreate) => request<ProfileRead>("/profiles", {
    method: "POST",
    body: JSON.stringify(body),
  }),
  getProfile: (profileName: string) => request<ProfileRead>(profilePath(profileName)),
  saveProfileFilters: (profileName: string, filters: Record<string, unknown>) =>
    request<ProfileRead>(`${profilePath(profileName)}/filters`, {
      method: "PUT",
      body: JSON.stringify(filters),
    }),
  updateProfileLocation: (profileName: string, myLocation: string) =>
    request<ProfileRead>(`${profilePath(profileName)}/location`, {
      method: "PUT",
      body: JSON.stringify({ my_location: myLocation }),
    }),

  startSearch: (profileName: string, body: SearchRequest) =>
    request<OperationRead<SearchResult>>(`${profilePath(profileName)}/searches`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  sendChat: (profileName: string, prompt: string, jobIds: string[]) =>
    request<ChatRead>(`${profilePath(profileName)}/chat`, {
      method: "POST",
      body: JSON.stringify({ prompt, job_ids: jobIds }),
    }),

  getBookmarks: (profileName: string) =>
    request<JobRead[]>(`${profilePath(profileName)}/bookmarks`),
  addBookmark: (profileName: string, jobId: string) =>
    request<BookmarkRead>(`${profilePath(profileName)}/bookmarks/${jobPath(jobId)}`, {
      method: "PUT",
    }),
  removeBookmark: (profileName: string, jobId: string) =>
    request<void>(`${profilePath(profileName)}/bookmarks/${jobPath(jobId)}`, {
      method: "DELETE",
    }),

  getResume: (profileName: string) =>
    request<ResumeRead>(`${profilePath(profileName)}/resume`),
  uploadResume: (profileName: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<OperationRead>(`${profilePath(profileName)}/resume`, {
      method: "PUT",
      body,
    });
  },
  deleteResume: (profileName: string) =>
    request<void>(`${profilePath(profileName)}/resume`, { method: "DELETE" }),

  startEmbedding: (profileName: string, body: EmbeddingRequest) =>
    request<OperationRead>(`${profilePath(profileName)}/embeddings`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getAlerts: (profileName: string) =>
    request<AlertRead[]>(`${profilePath(profileName)}/alerts`),
  createAlert: (profileName: string, body: AlertCreate) =>
    request<AlertRead>(`${profilePath(profileName)}/alerts`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateAlert: (profileName: string, alertId: number, body: AlertUpdate) =>
    request<AlertRead>(`${profilePath(profileName)}/alerts/${alertId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteAlert: (profileName: string, alertId: number) =>
    request<void>(`${profilePath(profileName)}/alerts/${alertId}`, { method: "DELETE" }),
  runAlert: (profileName: string, alertId: number) =>
    request<OperationRead<AlertRunResult>>(`${profilePath(profileName)}/alerts/${alertId}/run`, {
      method: "POST",
    }),
  getAlertMatches: (profileName: string, alertId: number) =>
    request<JobRead[]>(`${profilePath(profileName)}/alerts/${alertId}/matches`),
  getNotifications: (profileName: string, unreadOnly = false) =>
    request<NotificationRead[]>(`${profilePath(profileName)}/notifications?unread_only=${unreadOnly}`),
  markNotificationRead: (profileName: string, notificationId: number) =>
    request<NotificationRead>(`${profilePath(profileName)}/notifications/${notificationId}/read`, {
      method: "PATCH",
    }),

  getOperation: <TResult = Record<string, unknown>>(operationId: string) =>
    request<OperationRead<TResult>>(`/operations/${encodeURIComponent(operationId)}`),
};

export async function waitForOperation<TResult>(
  operationId: string,
  options: {
    intervalMs?: number;
    timeoutMs?: number;
    signal?: AbortSignal;
    onProgress?: (operation: OperationRead<TResult>) => void;
  } = {},
): Promise<OperationRead<TResult>> {
  const intervalMs = options.intervalMs ?? 1000;
  const timeoutMs = options.timeoutMs ?? 30 * 60 * 1000;
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    options.signal?.throwIfAborted();
    const operation = await api.getOperation<TResult>(operationId);
    options.onProgress?.(operation);

    if (operation.status === "succeeded") return operation;
    if (operation.status === "failed") {
      throw new ApiError(operation.error ?? "Background operation failed", 500, operation.error);
    }

    await new Promise<void>((resolve, reject) => {
      const onAbort = () => {
        window.clearTimeout(timeout);
        reject(options.signal?.reason ?? new DOMException("Aborted", "AbortError"));
      };
      const timeout = window.setTimeout(() => {
        options.signal?.removeEventListener("abort", onAbort);
        resolve();
      }, intervalMs);
      if (options.signal?.aborted) onAbort();
      else options.signal?.addEventListener("abort", onAbort, { once: true });
    });
  }

  throw new ApiError("Timed out waiting for the operation", 408, null);
}
