import type { PlanWeights } from "../api/types";

export type ScoresPanelProps = {
  weights: PlanWeights | null;
  onClose: () => void;
};

const DEFAULTS: PlanWeights = { drive: 1, hazard: 8, news: 4 };

export function ScoresPanel({ weights, onClose }: ScoresPanelProps) {
  const drive = weights?.drive ?? DEFAULTS.drive;
  const hazard = weights?.hazard ?? DEFAULTS.hazard;
  const news = weights?.news ?? DEFAULTS.news;

  return (
    <section className="absolute inset-y-0 left-0 z-[1100] w-full max-w-md overflow-y-auto border-r border-zinc-700 bg-zinc-950 p-5 shadow-xl">
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-base font-semibold">How scores work</h2>
        <button type="button" onClick={onClose} className="text-xs text-zinc-400 hover:text-zinc-100">
          Close
        </button>
      </div>
      <p className="mt-2 text-sm leading-6 text-zinc-400">
        {weights
          ? "These weights are the ones on the plan currently on screen."
          : "These are the default weights. A plan response can carry different ones."}
      </p>
      <p className="mt-4 font-mono text-sm leading-6 text-zinc-100">
        delay = {hazard} × hazard_risk + {news} × news_risk
        <br />
        score = {drive} × drive_hours + delay
      </p>
      <dl className="mt-4 space-y-3 text-sm leading-6 text-zinc-300">
        <div>
          <dt className="font-medium text-zinc-100">Hazard risk, 0 to 1</dt>
          <dd className="text-zinc-400">
            Each event within 100 miles adds severity × recency × proximity. The city score is that sum, capped at 1.
            Severity starts from the alert (green 0.25, yellow 0.45, orange 0.70, red 1.00) and can rise with reported
            deaths and injuries. Recency halves every 14 days. Proximity falls to 0 at 100 miles. The lookback is 30
            days, and only events that had already started by the as-of time are included. A road segment takes the
            highest score among five sample points.
          </dd>
        </div>
        <div>
          <dt className="font-medium text-zinc-100">News risk, 0 to 1</dt>
          <dd className="text-zinc-400">
            A headline counts when it is classified as relevant and as affecting road travel. It adds (severity / 3) ×
            recency, with severity from 0 to 3 and a 7-day half-life. The lookback is 7 days, and the city score is the
            sum capped at 1. An edge uses the higher news score of its two cities.
          </dd>
        </div>
        <div>
          <dt className="font-medium text-zinc-100">Deadline</dt>
          <dd className="text-zinc-400">
            Total hours are drive time plus delay. Overnight rest of 8 hours is added after each 10-hour driving day
            beyond the first. The route meets the deadline when that elapsed time is within the deadline. The badge
            says Tight when the spare time is under 12 hours.
          </dd>
        </div>
        <div>
          <dt className="font-medium text-zinc-100">Map colors</dt>
          <dd className="text-zinc-400">
            A segment is green, yellow, or red from the higher of its hazard and news scores: under 0.33, from 0.33 to
            under 0.66, and 0.66 or more.
          </dd>
        </div>
      </dl>
      <p className="mt-4 text-xs leading-5 text-zinc-500">
        The numbers are computed in Python. A language model, when one is used, only writes the explanation from those
        numbers.
      </p>
    </section>
  );
}
