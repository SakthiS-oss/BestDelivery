/** Small display helpers shared by the map and the route cards. */

import type { City, EdgeRisk, PlanWeights, RouteResult } from "./api/types";

export type DeadlineTone = "on-time" | "tight" | "miss";

export type HourParts = {
  drive: number;
  hazard: number;
  news: number;
};

const TIGHT_MARGIN_HOURS = 12;

export function deadlineTone(route: RouteResult): DeadlineTone {
  if (!route.meets_deadline) {
    return "miss";
  }
  if (route.deadline_margin_hours < TIGHT_MARGIN_HOURS) {
    return "tight";
  }
  return "on-time";
}

export function deadlineLabel(tone: DeadlineTone): string {
  if (tone === "miss") {
    return "Will miss";
  }
  if (tone === "tight") {
    return "Tight";
  }
  return "On time";
}

export function riskColor(hazard: number, news: number): string {
  const score = Math.max(hazard, news);
  if (score >= 0.66) {
    return "#f87171";
  }
  if (score >= 0.33) {
    return "#fbbf24";
  }
  return "#34d399";
}

export function hourParts(route: RouteResult, weights: PlanWeights): HourParts {
  let hazard = 0;
  let news = 0;
  for (const edge of route.edge_risks) {
    hazard += weights.hazard * edge.hazard_risk;
    news += weights.news * edge.news_risk;
  }
  return { drive: route.drive_hours, hazard, news };
}

export function edgeBetween(route: RouteResult, origin: City, dest: City): EdgeRisk | undefined {
  return route.edge_risks.find(
    (edge) =>
      (edge.origin_id === origin.id && edge.dest_id === dest.id) ||
      (edge.origin_id === dest.id && edge.dest_id === origin.id),
  );
}

export function samePath(left: RouteResult, right: RouteResult): boolean {
  if (left.cities.length !== right.cities.length) {
    return false;
  }
  return left.cities.every((city, index) => city.id === right.cities[index]?.id);
}

export function formatHours(value: number): string {
  return `${value.toFixed(1)} h`;
}

export function signedHours(value: number): string {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(1)} h`;
}

export function cityLabel(city: City): string {
  return `${city.name}, ${city.state}`;
}

export function dateInputValue(daysAhead: number): string {
  const date = new Date();
  date.setDate(date.getDate() + daysAhead);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}
