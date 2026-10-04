import type { City } from "../api/types";

export type RouteMapProps = {
  cities: City[];
  paths: string[][];
  selectedId: string | null;
};

export function RouteMap(_props: RouteMapProps) {
  return <section data-stub="RouteMap" />;
}
