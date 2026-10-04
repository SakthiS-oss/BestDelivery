/** Wire types for POST /api/plan. Field names match the JSON body. */

export type FactorName =
  | "hazard_risk"
  | "news_risk"
  | "delay_hours"
  | "travel_hours"
  | "deadline_slack_hours";

export type City = {
  id: string;
  name: string;
  state: string;
  lat: number;
  lon: number;
};

export type Hop = {
  origin_id: string;
  dest_id: string;
  road_miles: number;
  drive_hours: number;
};

export type Route = {
  id: string;
  city_ids: string[];
  hops: Hop[];
  total_miles: number;
  travel_hours: number;
};

export type Factor = {
  name: FactorName;
  value: number;
  unit: string;
  evidence_ids: string[];
};

export type RouteScore = {
  factors: Factor[];
  travel_cost_hours: number;
  risk_cost_hours: number;
  total_cost_hours: number;
  eta: string;
  meets_deadline: boolean;
};

export type Citation = {
  source: "distance" | "disaster" | "news" | "score";
  record_id: string;
  field: string;
  value: string;
};

export type ExplainedRoute = {
  route: Route;
  score: RouteScore;
  explanation: string;
  citations: Citation[];
};

export type PlanRequest = {
  start_city: string;
  end_city: string;
  deadline_at: string | null;
  deadline_days: number | null;
  as_of: string;
};

export type PlanResponse = {
  as_of: string;
  deadline_at: string;
  routes: ExplainedRoute[];
};

export type HealthResponse = {
  status: string;
  use_mock_data: boolean;
};
