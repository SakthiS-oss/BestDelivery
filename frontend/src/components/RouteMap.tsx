import { useEffect, useRef } from "react";
import { Circle, CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { LatLngBoundsExpression, LatLngExpression } from "leaflet";

import type { City, HazardEvent, RouteResult } from "../api/types";
import { edgeBetween, riskColor, samePath } from "../display";

export type RouteMapProps = {
  routes: RouteResult[];
  baseline: RouteResult | null;
  selectedId: string | null;
  compare: boolean;
  hazards: HazardEvent[];
  loading: boolean;
  onCity: (city: City) => void;
};

export function RouteMap({ routes, baseline, selectedId, compare, hazards, loading, onCity }: RouteMapProps) {
  const drawn = routes.filter((route) => route.id !== "baseline");
  const showBaseline = compare && baseline && !drawn.some((route) => samePath(route, baseline));
  const focus = [...drawn, ...(showBaseline && baseline ? [baseline] : [])];

  return (
    <div className="absolute inset-0">
      <MapContainer center={[39.5, -96]} zoom={4} zoomControl className="h-full w-full">
        <TileLayer
          attribution='&copy; OpenStreetMap'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitToRoutes routes={focus} />
        {showBaseline && baseline ? (
          <RouteLines route={baseline} selected={selectedId === baseline.id} muted={selectedId !== baseline.id} />
        ) : null}
        {drawn.map((route) => (
          <RouteLines
            key={route.id}
            route={route}
            selected={route.id === selectedId || (baseline != null && selectedId === baseline.id && samePath(route, baseline))}
            muted={false}
          />
        ))}
        {hazards.map((event) => (
          <HazardCircle key={event.event_id} event={event} />
        ))}
        <CityStops routes={focus} onCity={onCity} />
      </MapContainer>
      <div className="pointer-events-none absolute left-3 top-20 z-[1000] flex gap-3 rounded-md border border-zinc-700 bg-zinc-950/90 px-3 py-2 text-xs text-zinc-300">
        <Legend swatch="#34d399" label="Low" />
        <Legend swatch="#fbbf24" label="Mid" />
        <Legend swatch="#f87171" label="High" />
      </div>
      {loading ? (
        <div className="absolute inset-0 z-[1000] flex items-center justify-center bg-zinc-950/60 text-sm text-zinc-100">
          Scoring routes…
        </div>
      ) : null}
    </div>
  );
}

function Legend({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block h-2 w-4 rounded-sm" style={{ background: swatch }} />
      {label}
    </span>
  );
}

function FitToRoutes({ routes }: { routes: RouteResult[] }) {
  const map = useMap();
  const routesRef = useRef(routes);
  routesRef.current = routes;
  const signature = routes.map((route) => route.cities.map((city) => city.id).join(">")).join("|");

  useEffect(() => {
    const points: LatLngExpression[] = routesRef.current.flatMap((route) =>
      route.cities.map((city) => [city.lat, city.lon] as LatLngExpression),
    );
    if (points.length === 0) {
      return;
    }
    map.fitBounds(points as LatLngBoundsExpression, { padding: [36, 36] });
  }, [map, signature]);

  return null;
}

function RouteLines({ route, selected, muted }: { route: RouteResult; selected: boolean; muted: boolean }) {
  const stops = route.cities;
  return (
    <>
      {stops.slice(0, -1).map((origin, index) => {
        const dest = stops[index + 1];
        if (!dest) {
          return null;
        }
        const edge = edgeBetween(route, origin, dest);
        const color = muted || !edge ? "#d4d4d8" : riskColor(edge.hazard_risk, edge.news_risk);
        const positions: LatLngExpression[] = [
          [origin.lat, origin.lon],
          [dest.lat, dest.lon],
        ];
        return (
          <Polyline
            key={`${route.id}-${origin.id}-${dest.id}`}
            positions={positions}
            pathOptions={{
              color,
              weight: selected ? 6 : 3,
              opacity: selected ? 0.95 : 0.55,
              dashArray: muted ? "7 8" : undefined,
            }}
          />
        );
      })}
    </>
  );
}

function HazardCircle({ event }: { event: HazardEvent }) {
  if (typeof event.lat !== "number" || typeof event.lon !== "number") {
    return null;
  }
  const severity = typeof event.severity === "number" ? event.severity : 0.4;
  const alert = (event.alert_level ?? "").toLowerCase();
  const color = alert === "red" ? "#ef4444" : alert === "orange" ? "#fb923c" : alert === "yellow" ? "#facc15" : "#38bdf8";
  return (
    <Circle
      center={[event.lat, event.lon]}
      radius={Math.max(28_000, severity * 90_000)}
      pathOptions={{ color, fillColor: color, fillOpacity: 0.18, weight: 1 }}
    >
      <Tooltip>
        {event.event_name || event.event_type || "Hazard"}
        {event.alert_level ? ` · ${event.alert_level}` : ""}
      </Tooltip>
    </Circle>
  );
}

function CityStops({ routes, onCity }: { routes: RouteResult[]; onCity: (city: City) => void }) {
  const cities = new Map<string, City>();
  for (const route of routes) {
    for (const city of route.cities) {
      cities.set(city.id, city);
    }
  }
  return (
    <>
      {[...cities.values()].map((city) => (
        <CircleMarker
          key={city.id}
          center={[city.lat, city.lon]}
          radius={6}
          pathOptions={{ color: "#fafafa", weight: 2, fillColor: "#18181b", fillOpacity: 1 }}
          eventHandlers={{ click: () => onCity(city) }}
        >
          <Tooltip>{city.name}</Tooltip>
        </CircleMarker>
      ))}
    </>
  );
}
