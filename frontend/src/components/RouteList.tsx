import type { ExplainedRoute } from "../api/types";

export type RouteListProps = {
  routes: ExplainedRoute[];
  selectedId: string | null;
  onSelect: (routeId: string) => void;
};

export function RouteList(_props: RouteListProps) {
  return <section data-stub="RouteList" />;
}
