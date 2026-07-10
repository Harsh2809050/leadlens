import { StatTile } from "./ui.jsx";

export default function StatStrip({ competitors, b2bLeads, venues, individuals }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatTile label="Competitors" value={competitors} tone="indigo" />
      <StatTile label="B2B decision-makers" value={b2bLeads} tone="teal" />
      <StatTile label="B2C venues" value={venues} tone="amber" />
      <StatTile label="B2C public contacts" value={individuals} tone="rose" />
    </div>
  );
}
