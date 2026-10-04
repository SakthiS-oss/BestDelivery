import { useEffect, useState } from "react";

import { fetchBacktest, toError } from "../api/client";
import type { BacktestEvent, BacktestReport, BacktestSample } from "../api/types";

export type BacktestPageProps = {
  onReplay: (sample: BacktestSample) => void;
};

export function BacktestPage({ onReplay }: BacktestPageProps) {
  const [report, setReport] = useState<BacktestReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchBacktest()
      .then((body) => {
        if (!cancelled) {
          setReport(body);
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(toError(reason).message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return <p className="p-6 text-sm text-zinc-400">Loading the historical replay…</p>;
  }
  if (error || !report) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <h1 className="text-lg font-semibold">Historical replay</h1>
        <p role="alert" className="mt-3 text-sm text-red-300">
          {error ?? "No report is available."}
        </p>
        <p className="mt-3 text-sm text-zinc-400">
          From the repo root, run <code className="text-zinc-200">python scripts/backtest.py</code>. The page reads the
          saved report. It does not recompute routes.
        </p>
      </div>
    );
  }

  const events = Array.isArray(report.events) ? report.events : [];
  if (events.length === 0) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <h1 className="text-lg font-semibold">Historical replay</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-400">{report.disclaimer}</p>
        <p className="mt-4 text-sm text-zinc-400">
          This report lists no events. From the repo root, run{" "}
          <code className="text-zinc-200">python scripts/backtest.py</code> to build one.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col gap-4 overflow-y-auto p-6">
      <div>
        <h1 className="text-lg font-semibold">Historical replay</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-400">{report.disclaimer}</p>
      </div>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Events tested" value={String(report.events_tested)} />
        <Stat label="Through danger" value={String(report.routes_through_danger)} />
        <Stat label="Avoided" value={String(report.routes_avoided)} />
        <Stat label="Avg extra hours" value={formatHours(report.average_extra_hours)} />
      </dl>
      <div className="overflow-x-auto rounded-lg border border-zinc-800">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-zinc-800 text-xs uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="px-3 py-2 font-medium">Event</th>
              <th className="px-3 py-2 font-medium">As of</th>
              <th className="px-3 py-2 font-medium">Through danger</th>
              <th className="px-3 py-2 font-medium">Avoided</th>
              <th className="px-3 py-2 font-medium">Avg extra hours</th>
              <th className="px-3 py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <EventRow key={event.event_id} event={event} onReplay={onReplay} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EventRow({ event, onReplay }: { event: BacktestEvent; onReplay: (sample: BacktestSample) => void }) {
  const sample = event.samples.find((item) => item.avoided) ?? event.samples[0];
  return (
    <tr className="border-b border-zinc-900 align-top">
      <td className="px-3 py-3">
        <p className="font-medium text-zinc-100">{event.event_name}</p>
        <p className="mt-1 text-xs text-zinc-500">{event.affected_cities.join(", ")}</p>
      </td>
      <td className="px-3 py-3 text-zinc-300">{event.as_of.slice(0, 10)}</td>
      <td className="px-3 py-3">{event.routes_through_danger}</td>
      <td className="px-3 py-3">{event.routes_avoided}</td>
      <td className="px-3 py-3">{formatHours(event.average_extra_hours)}</td>
      <td className="px-3 py-3 text-right">
        {sample ? (
          <button
            type="button"
            onClick={() => onReplay(sample)}
            className="rounded-md border border-zinc-700 px-2 py-1 text-xs text-zinc-200 hover:border-zinc-500"
          >
            Replay
          </button>
        ) : (
          <span className="text-xs text-zinc-500">No sample</span>
        )}
      </td>
    </tr>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 px-3 py-2">
      <dt className="text-xs text-zinc-500">{label}</dt>
      <dd className="mt-1 text-lg font-medium">{value}</dd>
    </div>
  );
}

function formatHours(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "n/a";
  }
  return value.toFixed(1);
}
