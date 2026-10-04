import type { ExplainedRoute } from "../api/types";

export type ExplanationProps = {
  route: ExplainedRoute | null;
};

export function Explanation(_props: ExplanationProps) {
  return <section data-stub="Explanation" />;
}
