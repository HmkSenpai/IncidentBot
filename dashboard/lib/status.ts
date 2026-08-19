import type { Incident } from "./types";

export type IncidentStatus = "end" | "open" | "new";

// Filtres proposés dans la barre d'onglets du dashboard.
export const FILTERS = [
  { value: "tous", label: "Tous" },
  { value: "termines", label: "Terminés" },
  { value: "encours", label: "En cours" },
] as const;

export type IncidentFilter = (typeof FILTERS)[number]["value"];

// Statut qualitatif d'un incident : terminé (END), en cours, ou nouveau
// (état NEW, encore jamais passé en UPDATE).
export function statusOf(inc: Incident): IncidentStatus {
  if (inc.is_end) return "end";
  const etat = (inc.etat ?? "").trim();
  if (/update/i.test(etat)) return "open";
  if (/new/i.test(etat)) return "open";
  return "open";
}

export function filterIncidents(
  incidents: Incident[],
  filter: IncidentFilter
): Incident[] {
  if (filter === "tous") return incidents;
  const want = FILTER_TO_STATUS[filter];
  return incidents.filter((inc) => statusOf(inc) === want);
}

// Equivalence filtre (onglet) → statut qualitatif. "tous" n'a pas de statut.
export const FILTER_TO_STATUS: Record<Exclude<IncidentFilter, "tous">, IncidentStatus> = {
  termines: "end",
  encours: "open",
  nouveaux: "open",
};

export function countByStatus(incidents: Incident[]): Record<
  "tous" | IncidentStatus,
  number
> {
  const counts: Record<"tous" | IncidentStatus, number> = {
    tous: incidents.length,
    end: 0,
    open: 0,
    new: 0,
  };
  for (const inc of incidents) counts[statusOf(inc)] += 1;
  return counts;
}