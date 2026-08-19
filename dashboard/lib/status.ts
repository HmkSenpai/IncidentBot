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

// Recherche libre sur TT, site, localisation et dates (début/fin).
// Insensible à la casse, tolère un texte partiel.
export function searchIncidents(
  incidents: Incident[],
  query: string
): Incident[] {
  const q = query.trim().toLowerCase();
  if (!q) return incidents;

  return incidents.filter((inc) => {
    const haystack = [
      inc.tt,
      inc.site,
      inc.localisation,
      inc.debut,
      inc.fin,
      inc.etat,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(q);
  });
}