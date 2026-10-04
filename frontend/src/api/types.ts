/** Wire types for the planner API. Field names match the JSON bodies. */

export type City = {
  id: string;
  name: string;
  state: string;
  lat: number;
  lon: number;
};

export type RiskFactor = {
  name: string;
  value: number;
  unit: string;
  event_id?: string | null;
};

export type CityRisk = {
  city_id: string;
  name: string;
  state: string;
  hazard_risk: number;
  news_risk: number;
  factors: RiskFactor[];
  events: string[];
  headlines: string[];
};

export type EdgeRisk = {
  origin_id: string;
  dest_id: string;
  drive_hours: number;
  road_miles: number;
  hazard_risk: number;
  news_risk: number;
  delay_hours: number;
  factors: RiskFactor[];
  events: string[];
};

export type RouteResult = {
  id: string;
  cities: City[];
  city_risks: CityRisk[];
  edge_risks: EdgeRisk[];
  drive_hours: number;
  hazard_risk_max: number;
  hazard_risk_avg: number;
  news_risk_max: number;
  news_risk_avg: number;
  delay_hours_estimate: number;
  total_hours: number;
  total_score: number;
  meets_deadline: boolean;
  deadline_margin_hours: number;
  extra_drive_hours: number;
  avoided_cities: string[];
  note: string;
};

export type PlanWeights = {
  drive: number;
  hazard: number;
  news: number;
};

export type PlanRequest = {
  start: string;
  end: string;
  deadline: string;
  as_of_date?: string;
};

export type RouteExplanation = {
  id: string;
  explanation: string;
};

export type PlanResponse = {
  as_of: string;
  deadline_hours: number;
  weights: PlanWeights;
  baseline: RouteResult;
  routes: RouteResult[];
  warnings: string[];
  explanations: RouteExplanation[];
  recommendation: string;
  explanation_source: "model" | "template";
};

export type CityOption = {
  id: string;
  name: string;
  state: string;
  label: string;
  lat: number;
  lon: number;
};

export type HazardEvent = {
  event_id: string;
  event_name?: string;
  event_type?: string;
  lat?: number;
  lon?: number;
  alert_level?: string;
  severity?: number;
  contribution?: number;
  city?: string;
};

export type NewsArticle = {
  id: string;
  headline: string;
  date: string;
  event_type?: string;
  severity?: number;
};

export type CityRiskDetail = {
  city: CityOption;
  as_of_date: string;
  hazard: {
    score: number;
    factors: RiskFactor[];
    events: HazardEvent[];
  };
  news: {
    score: number;
    factors: RiskFactor[];
    articles: NewsArticle[];
    trend?: {
      direction: string;
      current_road_events: number;
      prior_road_events: number;
    };
  };
  warnings: string[];
};

export type HealthResponse = {
  status: string;
  use_mock_data: boolean;
  snowflake: string;
  ollama: string;
};

export type BacktestSample = {
  start: string;
  end: string;
  as_of_date: string;
  deadline_date: string;
  baseline_cities: string[];
  proposed_cities: string[];
  through_danger: boolean;
  avoided: boolean;
  extra_drive_hours: number;
};

export type BacktestEvent = {
  event_id: string;
  event_name: string;
  event_start: string;
  as_of: string;
  affected_cities: string[];
  routes_tested: number;
  routes_through_danger: number;
  routes_avoided: number;
  average_extra_hours: number | null;
  samples: BacktestSample[];
};

export type BacktestReport = {
  disclaimer: string;
  as_of_offset_days: number;
  events_tested: number;
  routes_tested: number;
  routes_through_danger: number;
  routes_avoided: number;
  average_extra_hours: number | null;
  events: BacktestEvent[];
};
