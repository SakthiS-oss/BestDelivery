import type { CityRiskDetail } from "../api/types";

export type CityPanelProps = {
  detail: CityRiskDetail | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
};

export function CityPanel({ detail, loading, error, onClose }: CityPanelProps) {
  if (!detail && !loading && !error) {
    return null;
  }

  return (
    <section className="absolute bottom-3 left-3 right-3 z-[1000] max-h-[42%] overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-950/95 p-3 shadow-lg">
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-sm font-medium">{detail ? detail.city.label : "City risk"}</h2>
        <button type="button" onClick={onClose} className="text-xs text-zinc-400 hover:text-zinc-100">
          Close
        </button>
      </div>
      {loading ? <p className="mt-2 text-sm text-zinc-400">Loading risk…</p> : null}
      {error ? <p className="mt-2 text-sm text-red-300">{error}</p> : null}
      {detail ? <Detail detail={detail} /> : null}
    </section>
  );
}

function Detail({ detail }: { detail: CityRiskDetail }) {
  const events = detail.hazard.events ?? [];
  const articles = detail.news.articles ?? [];
  const direction = detail.news.trend?.direction;

  return (
    <div className="mt-2 grid gap-3 sm:grid-cols-2">
      <div>
        <p className="text-xs uppercase tracking-wide text-zinc-500">Hazards</p>
        <p className="mt-1 text-sm">Score {detail.hazard.score.toFixed(2)}</p>
        <ul className="mt-2 space-y-1 text-sm text-zinc-300">
          {events.length === 0 ? <li className="text-zinc-500">No hazards in range.</li> : null}
          {events.slice(0, 5).map((event) => (
            <li key={event.event_id}>
              {event.event_name || event.event_type || event.event_id}
              {event.alert_level ? ` · ${event.alert_level}` : ""}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-zinc-500">News</p>
        <p className="mt-1 text-sm">
          Score {detail.news.score.toFixed(2)}
          {direction ? ` · ${direction}` : ""}
        </p>
        <ul className="mt-2 space-y-1 text-sm text-zinc-300">
          {articles.length === 0 ? <li className="text-zinc-500">No road-affecting headlines.</li> : null}
          {articles.slice(0, 5).map((article) => (
            <li key={article.id}>
              {article.headline}
              <span className="block text-xs text-zinc-500">{article.date.slice(0, 10)}</span>
            </li>
          ))}
        </ul>
      </div>
      {detail.warnings.length > 0 ? <p className="text-xs text-amber-300 sm:col-span-2">{detail.warnings.join(" ")}</p> : null}
    </div>
  );
}
