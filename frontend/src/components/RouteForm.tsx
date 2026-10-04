import type { PlanRequest } from "../api/types";

export type RouteFormProps = {
  onSubmit: (request: PlanRequest) => void;
};

export function RouteForm(_props: RouteFormProps) {
  return <section data-stub="RouteForm" />;
}
