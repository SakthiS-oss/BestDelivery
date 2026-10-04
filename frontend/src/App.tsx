import { useEffect, useState } from "react";

import { fetchCities, fetchCityRisk, fetchHealth, planDelivery } from "./api/client";
import type {
  BacktestSample,
  City,
  CityOption,
  CityRiskDetail,
  HazardEvent,
  HealthResponse,
  PlanRequest,
  PlanResponse,
} from "./api/types";
import { BacktestPage } from "./components/BacktestPage";
import { CityPanel } from "./components/CityPanel";
import { RouteForm, type ReplaySeed } from "./components/RouteForm";
import { RouteList } from "./components/RouteList";
import { RouteMap } from "./components/RouteMap";
import { cityLabel } from "./display";

export function App() {
  const [catalog, setCatalog] = useState<CityOption[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [compare, setCompare] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hazards, setHazards] = useState<HazardEvent[]>([]);
  const [riskByCity, setRiskByCity] = useState<Record<string, CityRiskDetail>>({});
  const [activeCityId, setActiveCityId] = useState<string | null>(null);
  const [cityLoading, setCityLoading] = useState(false);
  const [cityError, setCityError] = useState<string | null>(null);
  const [view, setView] = useState<"planner" | "backtest">("planner");
  const [replay, setReplay] = useState<ReplaySeed | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchHealth(), fetchCities()])
      .then(([healthReport, cities]) => {
        if (cancelled) {
          return;
        }
        setHealth(healthReport);
        setCatalog(cities);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setBootError(reason instanceof Error ? reason.message : "The API is unreachable.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(request: PlanRequest) {
    setLoading(true);
    setError(null);
    setActiveCityId(null);
    setCityError(null);
    try {
      const result = await planDelivery(request);
      const asOf = result.as_of;
      const cities = uniqueCities([result.baseline, ...result.routes]);
      const loaded = await Promise.all(
        cities.map(async (city) => {
          try {
            const detail = await fetchCityRisk(cityLabel(city), asOf);
            return [city.id, detail] as const;
          } catch {
            return null;
          }
        }),
      );
      const nextRisk: Record<string, CityRiskDetail> = {};
      const events: HazardEvent[] = [];
      const seen = new Set<string>();
      for (const row of loaded) {
        if (!row) {
          continue;
        }
        const [cityId, detail] = row;
        nextRisk[cityId] = detail;
        for (const event of detail.hazard.events ?? []) {
          if (!seen.has(event.event_id)) {
            seen.add(event.event_id);
            events.push(event);
          }
        }
      }
      setPlan(result);
      setSelectedId(result.routes[0]?.id ?? result.baseline.id);
      setHazards(events);
      setRiskByCity(nextRisk);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Planning failed.");
    } finally {
      setLoading(false);
    }
  }

  function onCity(city: City) {
    setActiveCityId(city.id);
    setCityError(null);
    if (riskByCity[city.id]) {
      setCityLoading(false);
      return;
    }
    setCityLoading(true);
    fetchCityRisk(cityLabel(city), plan?.as_of)
      .then((detail) => {
        setRiskByCity((current) => ({ ...current, [city.id]: detail }));
      })
      .catch((reason: unknown) => {
        setCityError(reason instanceof Error ? reason.message : "Could not load city risk.");
      })
      .finally(() => setCityLoading(false));
  }

  function onReplay(sample: BacktestSample) {
    setView("planner");
    setCompare(true);
    setReplay({
      token: Date.now(),
      start: sample.start,
      end: sample.end,
      asOf: sample.as_of_date,
      deadline: sample.deadline_date,
    });
  }

  const detail = activeCityId ? riskByCity[activeCityId] ?? null : null;
  const warnings = plan?.warnings ?? [];

  return (
    <div className="flex h-screen flex-col bg-zinc-950 text-zinc-100">
      {health?.use_mock_data ? (
        <div className="border-b border-amber-900 bg-amber-950 px-4 py-2 text-sm text-amber-200">
          Mock data is on. Hazards and news come from local files.
        </div>
      ) : null}
      {bootError ? (
        <div className="border-b border-red-900 bg-red-950 px-4 py-2 text-sm text-red-200">
          {bootError}. Start the API on port 8000.
        </div>
      ) : null}
      {warnings.length > 0 ? (
        <div className="border-b border-amber-900 bg-amber-950/70 px-4 py-2 text-sm text-amber-100">{warnings.join(" ")}</div>
      ) : null}
      <div className="flex gap-2 border-b border-zinc-800 px-4 py-2 text-sm">
        <ViewButton active={view === "planner"} onClick={() => setView("planner")}>
          Planner
        </ViewButton>
        <ViewButton active={view === "backtest"} onClick={() => setView("backtest")}>
          Backtest
        </ViewButton>
      </div>
      {view === "backtest" ? (
        <BacktestPage onReplay={onReplay} />
      ) : (
      <div className="grid min-h-0 flex-1 grid-cols-1 min-[800px]:grid-cols-[240px_minmax(0,1fr)_260px]">
        <aside className="overflow-y-auto border-zinc-800 min-[800px]:border-r">
          <RouteForm cities={catalog} loading={loading} error={error} replay={replay} onSubmit={onSubmit} />
        </aside>
        <section className="relative min-h-[560px] min-[800px]:min-h-0">
          <RouteMap
            routes={plan?.routes ?? []}
            baseline={plan?.baseline ?? null}
            selectedId={selectedId}
            compare={compare}
            hazards={hazards}
            loading={loading}
            onCity={onCity}
          />
          <CityPanel
            detail={detail}
            loading={cityLoading && !detail}
            error={cityError}
            onClose={() => {
              setActiveCityId(null);
              setCityError(null);
            }}
          />
        </section>
        <aside className="min-h-[280px] border-zinc-800 min-[800px]:min-h-0 min-[800px]:border-l">
          <RouteList
            routes={plan?.routes ?? []}
            baseline={plan?.baseline ?? null}
            weights={plan?.weights ?? null}
            selectedId={selectedId}
            compare={compare}
            onSelect={setSelectedId}
            onCompare={setCompare}
          />
        </aside>
      </div>
      )}
    </div>
  );
}

function ViewButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md px-2 py-1 ${active ? "bg-zinc-800 text-zinc-100" : "text-zinc-400 hover:text-zinc-200"}`}
    >
      {children}
    </button>
  );
}

function uniqueCities(routes: { cities: City[] }[]): City[] {
  const cities = new Map<string, City>();
  for (const route of routes) {
    for (const city of route.cities) {
      cities.set(city.id, city);
    }
  }
  return [...cities.values()];
}
