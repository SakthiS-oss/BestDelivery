import type { PlanWeights, RouteResult } from "../api/types";
import { deadlineLabel, deadlineTone, formatHours, hourParts, samePath, signedHours } from "../display";

export type RouteListProps = {
  routes: RouteResult[];
  baseline: RouteResult | null;
  weights: PlanWeights | null;
  selectedId: string | null;
  compare: boolean;
  onSelect: (routeId: string) => void;
  onCompare: (value: boolean) => void;
};

export function RouteList({ routes, baseline, weights, selectedId, compare, onSelect, onCompare }: RouteListProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
        <h2 className="text-sm font-medium text-zinc-200">Routes</h2>
        <label className="flex items-center gap-2 text-xs text-zinc-400">
          <input
            type="checkbox"
            checked={compare}
            onChange={(event) => onCompare(event.target.checked)}
            disabled={!baseline}
            className="accent-emerald-500"
          />
          Compare fastest
        </label>
      </div>
      <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-3">
        {routes.length === 0 ? (
          <p className="px-1 text-sm text-zinc-500">Plan a trip to rank routes.</p>
        ) : null}
        {compare && baseline ? (
          <RouteCard
            route={baseline}
            rankLabel="Fastest"
            weights={weights}
            selected={selectedId === baseline.id}
            baseline={baseline}
            compare
            onSelect={onSelect}
          />
        ) : null}
        {routes.map((route, index) => (
          <RouteCard
            key={route.id}
            route={route}
            rankLabel={`#${index + 1}`}
            weights={weights}
            selected={selectedId === route.id}
            baseline={baseline}
            compare={compare}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );
}

function RouteCard({
  route,
  rankLabel,
  weights,
  selected,
  baseline,
  compare,
  onSelect,
}: {
  route: RouteResult;
  rankLabel: string;
  weights: PlanWeights | null;
  selected: boolean;
  baseline: RouteResult | null;
  compare: boolean;
  onSelect: (routeId: string) => void;
}) {
  const tone = deadlineTone(route);
  const parts = weights ? hourParts(route, weights) : null;
  const total = parts ? parts.drive + parts.hazard + parts.news : route.total_hours;
  const matchesBaseline = baseline ? samePath(route, baseline) : false;
  const badgeClass =
    tone === "miss"
      ? "bg-red-950 text-red-300"
      : tone === "tight"
        ? "bg-amber-950 text-amber-300"
        : "bg-emerald-950 text-emerald-300";

  return (
    <button
      type="button"
      onClick={() => onSelect(route.id)}
      className={`rounded-lg border px-3 py-3 text-left ${
        selected ? "border-emerald-500 bg-zinc-900" : "border-zinc-800 bg-zinc-950 hover:border-zinc-600"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs uppercase tracking-wide text-zinc-500">{rankLabel}</p>
          <p className="mt-1 text-sm text-zinc-200">{route.cities.map((city) => city.name).join(" → ")}</p>
        </div>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${badgeClass}`}>{deadlineLabel(tone)}</span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <div>
          <dt className="text-xs text-zinc-500">Total hours</dt>
          <dd className="font-medium">{formatHours(route.total_hours)}</dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500">Delay estimate</dt>
          <dd className="font-medium">{formatHours(route.delay_hours_estimate)}</dd>
        </div>
      </dl>
      {parts ? <Breakdown parts={parts} total={total} /> : null}
      {compare && baseline && route.id !== baseline.id ? (
        <p className="mt-2 text-xs text-zinc-400">
          {matchesBaseline
            ? "Same path as the fastest route."
            : `Versus fastest: ${signedHours(route.extra_drive_hours)} drive, ${signedHours(route.total_score - baseline.total_score)} score.`}
        </p>
      ) : null}
      {route.note ? <p className="mt-2 text-xs leading-5 text-zinc-500">{route.note}</p> : null}
    </button>
  );
}

function Breakdown({ parts, total }: { parts: { drive: number; hazard: number; news: number }; total: number }) {
  const safe = total > 0 ? total : 1;
  const segments = [
    { key: "drive", label: "Drive", hours: parts.drive, className: "bg-zinc-400" },
    { key: "hazard", label: "Hazard", hours: parts.hazard, className: "bg-red-400" },
    { key: "news", label: "News", hours: parts.news, className: "bg-amber-300" },
  ];
  return (
    <div className="mt-3">
      <div className="flex h-2 overflow-hidden rounded-full bg-zinc-800">
        {segments.map((segment) => (
          <span
            key={segment.key}
            className={segment.className}
            style={{ width: `${(segment.hours / safe) * 100}%` }}
          />
        ))}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-zinc-400">
        {segments.map((segment) => (
          <li key={segment.key} className="flex items-center gap-1">
            <span className={`inline-block h-2 w-2 rounded-sm ${segment.className}`} />
            {segment.label} {formatHours(segment.hours)}
          </li>
        ))}
      </ul>
    </div>
  );
}
