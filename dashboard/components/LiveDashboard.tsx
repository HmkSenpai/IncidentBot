"use client";

import { useEffect, useState } from "react";
import type { Incident } from "@/lib/types";
import { FILTERS, filterIncidents, statusOf } from "@/lib/status";
import type { IncidentFilter } from "@/lib/status";
import styles from "@/app/page.module.css";
import { } from "@/lib/status";
import {
  filterByDateRange,
  searchIncidents,} from "@/lib/status";
import type { DateRange } from "@/lib/status";
// Intervalle de rafraîchissement du tableau de bord (en direct).
const POLL_MS = 6000;

function formatDate(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function formatTime(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "-";
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

function badgeMeta(inc: Incident): {
  label: string;
  kind: "open" | "update" | "end";
} {
  if (inc.is_end) return { label: "END", kind: "end" };
  const etat = (inc.etat ?? "").trim();
  if (/update/i.test(etat)) return { label: etat.toUpperCase(), kind: "update" };
  if (/new/i.test(etat)) return { label: "NEW", kind: "open" };
  return { label: etat || "EN COURS", kind: "open" };
}

function DownloadIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={styles.downloadIcon}
      aria-hidden="true"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <path d="M7 10l5 5 5-5" />
      <path d="M12 15V3" />
    </svg>
  );
}
function SearchIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={styles.searchIcon}
      aria-hidden="true"
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}
// ---- SVG icons (Lucide/Heroicons) --------------------------------------

function StatIcon({ name }: { name: "total" | "open" | "closed" | "sites" }) {
  const paths: Record<string, React.ReactNode> = {
    total: (
      <>
        <path d="M3 3h18v18H3z" />
        <path d="M3 9h18" />
      </>
    ),
    open: (
      <>
        <circle cx="12" cy="12" r="10" />
        <path d="M12 6v6l4 2" />
      </>
    ),
    closed: (
      <>
        <path d="M20 6 9 17l-5-5" />
        <rect x="3" y="3" width="18" height="18" rx="2" />
      </>
    ),
    sites: (
      <>
        <path d="M12 21s-7-5.2-7-11a7 7 0 0 1 14 0c0 5.8-7 11-7 11z" />
        <circle cx="12" cy="10" r="2.5" />
      </>
    ),
  };
  return (
    <svg
      className={styles.statIcon}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

function StatCard({
  label,
  value,
  icon,
  accent,
}: {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <div className={`${styles.statCard} ${accent ? styles.statAccent : ""}`}>
      <div className={styles.statIconWrap}>{icon}</div>
      <div className={styles.statValue}>{value}</div>
      <div className={styles.statLabel}>{label}</div>
    </div>
  );
}

export default function LiveDashboard({ initial }: { initial: Incident[] }) {
  const [items, setItems] = useState<Incident[]>(initial);
  const [filter, setFilter] = useState<IncidentFilter>("tous");
  const [search, setSearch] = useState("");
  const [dateRange, setDateRange] = useState<DateRange>({ from: "", to: "" });

  // Rafraîchit les données sans recharger la page ("En direct").
  useEffect(() => {
    let disposed = false;

    const tick = async () => {
      try {
        const res = await fetch("/api/incidents", { cache: "no-store" });
        if (!res.ok) return;
        const data = (await res.json()) as Incident[];
        if (!disposed) setItems(data);
      } catch {
        // réseau indisponible : on garde les données actuelles
      }
    };

    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      disposed = true;
      clearInterval(id);
    };
  }, []);

 const filtered = filterByDateRange(
  searchIncidents(filterIncidents(items, filter), search),
  dateRange
);

  const total = items.length;
  const ended = items.filter((i) => statusOf(i) === "end").length;
  const open = items.filter((i) => statusOf(i) === "open").length;
  const fresh = items.filter((i) => statusOf(i) === "new").length;
  const sites = new Set(items.map((i) => i.site).filter(Boolean)).size;

  const tabCount = (f: IncidentFilter) =>
    f === "tous" ? total : f === "termines" ? ended : f === "encours" ? open : fresh;

  const empty = items.length === 0;

  return (
    <>
      <section className={styles.stats}>
        <StatCard label="Au total" value={total} icon={<StatIcon name="total" />} accent />
        <StatCard label="Terminés (END)" value={ended} icon={<StatIcon name="closed" />} />
        <StatCard label="En cours / UPDATE" value={open} icon={<StatIcon name="open" />} />
        <StatCard label="Sites distincts" value={sites} icon={<StatIcon name="sites" />} />
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Historique des incidents</h2>
          <span className={styles.count}>
            {filtered.length} ligne(s)
            {!empty && (
              <span className={styles.liveHint}>
                · mis à jour en direct
              </span>
            )}
          </span>
        </div>
  <div className={styles.searchWrap}>
  <SearchIcon />
  <input
    type="text"
    value={search}
    onChange={(e) => setSearch(e.target.value)}
    placeholder="Rechercher par CTT, site ..."
    className={styles.searchInput}
    aria-label="Rechercher un incident"
  />
  {search && (
    <button
      type="button"
      className={styles.searchClear}
      onClick={() => setSearch("")}
      aria-label="Effacer la recherche"
    >
      ×
    </button>
  )}
</div>
<div className={styles.dateRangeWrap}>
  <input
    type="date"
    value={dateRange.from}
    onChange={(e) =>
      setDateRange((r) => ({ ...r, from: e.target.value }))
    }
    className={styles.dateInput}
    aria-label="Date de début"
  />
  <span className={styles.dateSep}>→</span>
  <input
    type="date"
    value={dateRange.to}
    onChange={(e) =>
      setDateRange((r) => ({ ...r, to: e.target.value }))
    }
    className={styles.dateInput}
    aria-label="Date de fin"
  />
  {(dateRange.from || dateRange.to) && (
    <button
      type="button"
      className={styles.searchClear}
      onClick={() => setDateRange({ from: "", to: "" })}
      aria-label="Effacer les dates"
    >
      ×
    </button>
  )}
</div>
        <nav className={styles.tabs} aria-label="Filtrer par état">
          {FILTERS.map((f) => {
            const active = filter === f.value;
            return (
              <button
                key={f.value}
                type="button"
                aria-pressed={active}
                className={`${styles.tab} ${active ? styles.tabActive : ""}`}
                onClick={() => setFilter(f.value)}
              >
                {f.label}
                <span className={styles.tabCount}>{tabCount(f.value)}</span>
              </button>
            );
          })}
        </nav>

        {empty ? (
          <div className={styles.empty}>
            Aucun incident enregistré pour le moment. Lancez le pipeline
            (whatsapp.py / generator.py) pour insérer vos premières lignes.
          </div>
        ) : (
          <IncidentTable incidents={filtered} />
        )}
      </section>
    </>
  );
}

function IncidentTable({ incidents }: { incidents: Incident[] }) {
  const [selected, setSelected] = useState<Incident | null>(null);

  if (incidents.length === 0) {
    return <div className={styles.empty}>Aucun incident dans cette catégorie.</div>;
  }

  return (
    <>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={`${styles.stickyCol} ${styles.stickyFirst}`}>CTT</th>
              <th>Site</th>
              <th>État</th>
              <th>Début</th>
              <th>Fin</th>
              <th>Porteur</th>
              <th>Cause</th>
              <th>Réglé</th>
              <th className={`${styles.stickyCol} ${styles.stickyLast}`}>Fiche</th>
            </tr>
          </thead>
          <tbody>
            {incidents.map((inc) => {
              const badge = badgeMeta(inc);
              return (
                <tr
                  key={inc.id}
                  className={styles.rowClickable}
                  onClick={() => setSelected(inc)}
                  tabIndex={0}
                  role="button"
                  aria-label={`Ouvrir le détail de l'incident ${inc.tt ?? "sans TT"}`}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelected(inc);
                    }
                  }}
                >
                  <td className={`${styles.mono} ${styles.stickyCol} ${styles.stickyFirst}`}>
                    {inc.tt ?? "-"}
                  </td>
                  <td className={styles.strong}>{inc.site ?? "-"}</td>
                  <td>
                    <span className={`${styles.badge} ${styles[`badge${badge.kind}`]}`}>
                      {badge.label}
                    </span>
                  </td>
                  <td>
                    <div className={styles.dateCell}>{formatDate(inc.debut)}</div>
                    <div className={styles.timeCell}>{formatTime(inc.debut)}</div>
                  </td>
                  <td>
                    <div className={styles.dateCell}>{formatDate(inc.fin)}</div>
                    <div className={styles.timeCell}>{formatTime(inc.fin)}</div>
                  </td>
                  <td>{inc.porteur ?? "-"}</td>
                  <td className={styles.truncate} title={inc.cause ?? ""}>
                    {inc.cause ?? "-"}
                  </td>
                  <td>
                    {inc.is_end ? (
                      <span className={styles.isEnd}>✓</span>
                    ) : (
                      <span className={styles.isOpen}>●</span>
                    )}
                  </td>
                  <td
                    className={`${styles.stickyCol} ${styles.stickyLast} ${styles.actionsCell}`}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {inc.docx_url ? (
                      <a
                        className={styles.download}
                        href={inc.docx_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        download={inc.docx_name ?? undefined}
                        title={`Télécharger ${inc.docx_name ?? "la fiche"}`}
                      >
                        <DownloadIcon />
                        <span>Fiche</span>
                      </a>
                    ) : (
                      <span className={styles.noFiche}>-</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {selected && <IncidentDialog incident={selected} onClose={() => setSelected(null)} />}
    </>
  );
}

function IncidentDialog({
  incident,
  onClose,
}: {
  incident: Incident;
  onClose: () => void;
}) {
  const badge = badgeMeta(incident);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div
        className={styles.ficheDialog}
        role="dialog"
        aria-modal="true"
        aria-label={`Incident ${incident.tt ?? ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className={styles.ficheHeader}>
          <div className={styles.ficheTitleRow}>
            <h3 className={styles.ficheTt}>{incident.tt ?? "Incident"}</h3>
            <span className={`${styles.badge} ${styles[`badge${badge.kind}`]}`}>
              {badge.label}
            </span>
            <button className={styles.ficheClose} onClick={onClose} aria-label="Fermer">
              ×
            </button>
          </div>
          <div className={styles.ficheMeta}>
            {incident.site ? <span>{incident.site}</span> : null}
            {incident.debut ? (
              <span>
                Début · {formatDate(incident.debut)} {formatTime(incident.debut)}
              </span>
            ) : null}
            {incident.porteur ? <span>Porteur · {incident.porteur}</span> : null}
          </div>
        </header>

        <div className={styles.ficheBody}>
          <p className={styles.ficheLabel}>Message reçu sur WhatsApp</p>
          <pre className={styles.raw}>{incident.raw_message || "-"}</pre>
        </div>

        <footer className={styles.ficheFooter}>
          {incident.docx_url ? (
            <a
              className={styles.downloadPrimary}
              href={incident.docx_url}
              target="_blank"
              rel="noopener noreferrer"
              download={incident.docx_name ?? undefined}
            >
              <DownloadIcon />
              <span>Télécharger la fiche</span>
            </a>
          ) : (
            <span className={styles.noFiche}>Fiche non disponible</span>
          )}
        </footer>
      </div>
    </div>
  );
}