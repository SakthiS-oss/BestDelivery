import { useEffect, useMemo, useState, type FormEvent } from "react";

import type { CityOption, PlanRequest } from "../api/types";
import { dateInputValue } from "../display";

export type ReplaySeed = {
  token: number;
  start: string;
  end: string;
  asOf: string;
  deadline: string;
};

export type RouteFormProps = {
  cities: CityOption[];
  loading: boolean;
  error: string | null;
  replay: ReplaySeed | null;
  onSubmit: (request: PlanRequest) => void;
};

export function RouteForm({ cities, loading, error, replay, onSubmit }: RouteFormProps) {
  const [start, setStart] = useState("Dallas, TX");
  const [end, setEnd] = useState("Atlanta, GA");
  const [deadline, setDeadline] = useState(() => dateInputValue(4));
  const [asOf, setAsOf] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (!replay) {
      return;
    }
    setStart(replay.start);
    setEnd(replay.end);
    setDeadline(replay.deadline);
    setAsOf(replay.asOf);
    setLocalError(null);
    onSubmit({
      start: replay.start,
      end: replay.end,
      deadline: `${replay.deadline}T23:59:59Z`,
      as_of_date: replay.asOf,
    });
  }, [replay]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (start.trim().toLowerCase() === end.trim().toLowerCase()) {
      setLocalError("Start and end must be different cities.");
      return;
    }
    if (asOf && deadline <= asOf) {
      setLocalError("Deadline must be after the as-of date.");
      return;
    }
    setLocalError(null);
    const request: PlanRequest = {
      start: start.trim(),
      end: end.trim(),
      deadline: `${deadline}T23:59:59Z`,
    };
    if (asOf) {
      request.as_of_date = asOf;
    }
    onSubmit(request);
  }

  const message = localError ?? error;

  return (
    <form onSubmit={submit} className="flex flex-col gap-4 p-4">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Chokepoint</h1>
        <p className="mt-1 text-sm text-zinc-400">Rank truck routes by drive time, hazards, and news.</p>
      </div>
      <CityField label="Start" value={start} cities={cities} onChange={setStart} />
      <CityField label="End" value={end} cities={cities} onChange={setEnd} />
      <label className="flex flex-col gap-1 text-sm">
        <span className="text-zinc-400">Deadline</span>
        <input
          type="date"
          required
          value={deadline}
          onChange={(event) => setDeadline(event.target.value)}
          className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-zinc-100"
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="text-zinc-400">As of</span>
        <input
          type="date"
          value={asOf}
          onChange={(event) => setAsOf(event.target.value)}
          className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-zinc-100"
        />
        <span className="text-xs text-zinc-500">Optional. Replay hazards and news known on this day.</span>
      </label>
      <button
        type="submit"
        disabled={loading}
        className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-wait disabled:bg-zinc-700"
      >
        {loading ? "Planning…" : "Plan routes"}
      </button>
      {message ? <p className="text-sm text-red-300">{message}</p> : null}
    </form>
  );
}

function CityField({
  label,
  value,
  cities,
  onChange,
}: {
  label: string;
  value: string;
  cities: CityOption[];
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const matches = useMemo(() => {
    const query = value.trim().toLowerCase();
    const pool = query
      ? cities.filter((city) => city.label.toLowerCase().includes(query) || city.name.toLowerCase().includes(query))
      : cities;
    return pool.slice(0, 8);
  }, [cities, value]);

  const inputId = label.toLowerCase().replace(/\s+/g, "-");
  return (
    <div className="relative flex flex-col gap-1 text-sm">
      <label htmlFor={inputId} className="text-zinc-400">
        {label}
      </label>
      <input
        id={inputId}
        required
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        placeholder="City, ST"
        className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-zinc-100 placeholder:text-zinc-600"
        autoComplete="off"
      />
      {open && matches.length > 0 ? (
        <ul className="absolute top-full z-20 mt-1 max-h-48 w-full overflow-auto rounded-md border border-zinc-700 bg-zinc-900 py-1 shadow-lg">
          {matches.map((city) => (
            <li key={city.id}>
              <button
                type="button"
                className="w-full px-3 py-1.5 text-left text-sm hover:bg-zinc-800"
                onMouseDown={(event) => {
                  event.preventDefault();
                  onChange(city.label);
                  setOpen(false);
                }}
              >
                {city.label}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
