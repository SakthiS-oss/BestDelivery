import { Explanation } from "./components/Explanation";
import { RouteForm } from "./components/RouteForm";
import { RouteList } from "./components/RouteList";
import { RouteMap } from "./components/RouteMap";

export function App() {
  return (
    <main className="min-h-screen p-6">
      <h1 className="text-2xl font-semibold">Chokepoint</h1>
      <RouteForm
        onSubmit={() => {
          throw new Error("Not implemented");
        }}
      />
      <RouteMap cities={[]} paths={[]} selectedId={null} />
      <RouteList routes={[]} selectedId={null} onSelect={() => undefined} />
      <Explanation route={null} />
    </main>
  );
}
