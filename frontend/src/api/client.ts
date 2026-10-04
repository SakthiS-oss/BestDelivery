/** API client. Calls are unimplemented until the frontend step. */

import type { HealthResponse, PlanRequest, PlanResponse } from "./types";

export function apiBaseUrl(): string {
  /** Base URL for the FastAPI server, from VITE_API_BASE_URL. */
  throw new Error("Not implemented");
}

export async function fetchHealth(): Promise<HealthResponse> {
  /** GET /api/health. */
  throw new Error("Not implemented");
}

export async function planDelivery(request: PlanRequest): Promise<PlanResponse> {
  /** POST /api/plan. */
  throw new Error("Not implemented");
}
