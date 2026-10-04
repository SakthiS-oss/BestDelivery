/** HTTP client for the FastAPI server. */

import type {
  CityOption,
  CityRiskDetail,
  HealthResponse,
  PlanRequest,
  PlanResponse,
} from "./types";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
  return configured.replace(/\/$/, "");
}

export async function fetchHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>("/health");
}

export async function fetchCities(): Promise<CityOption[]> {
  return getJson<CityOption[]>("/cities");
}

export async function fetchCityRisk(name: string, asOf?: string): Promise<CityRiskDetail> {
  const params = new URLSearchParams();
  if (asOf) {
    params.set("as_of_date", asOf);
  }
  const query = params.toString();
  const path = `/city/${encodeURIComponent(name)}/risk${query ? `?${query}` : ""}`;
  return getJson<CityRiskDetail>(path);
}

export function toError(reason: unknown): Error {
  if (reason instanceof ApiError) {
    return reason;
  }
  if (reason instanceof DOMException && (reason.name === "TimeoutError" || reason.name === "AbortError")) {
    return new Error("The request timed out.");
  }
  if (reason instanceof TypeError) {
    return new Error("The API is unreachable. Start it on port 8000.");
  }
  if (reason instanceof Error) {
    return reason;
  }
  return new Error("Something went wrong.");
}

export async function planDelivery(request: PlanRequest): Promise<PlanResponse> {
  const response = await send("/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: AbortSignal.timeout(60_000),
  });
  return readJson<PlanResponse>(response);
}

async function getJson<T>(path: string): Promise<T> {
  const response = await send(path, { signal: AbortSignal.timeout(20_000) });
  return readJson<T>(response);
}

async function send(path: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, init);
  } catch (reason) {
    throw toError(reason);
  }
  if (!response.ok) {
    throw await readError(response);
  }
  return response;
}

async function readJson<T>(response: Response): Promise<T> {
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError("The API returned a response that was not JSON.", response.status);
  }
}

async function readError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    const detail = body.detail;
    if (typeof detail === "string") {
      return new ApiError(detail, response.status);
    }
    if (Array.isArray(detail)) {
      const message = detail
        .map((item) => {
          if (item && typeof item === "object" && "msg" in item) {
            return String(item.msg);
          }
          return "Invalid request";
        })
        .join(" ");
      return new ApiError(message, response.status);
    }
  } catch {
    /* The body was not JSON. */
  }
  return new ApiError(`Request failed (${response.status})`, response.status);
}
