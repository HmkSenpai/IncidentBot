import { fetchIncidents } from "@/lib/incidents";
import type { Incident } from "@/lib/types";
import styles from "./page.module.css";

// Données toujours fraîches à chaque requête : on lit Supabase au moment où le
// client charge la page, pas lors du build (pas de pré-render statique).
export const dynamic = "force-dynamic";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

// ---- SVG icons (Lucide/Heroicons, pas d'emoji) ---------------------------

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

// ---- Badge d'état --------------------------------------------------------
function stateMeta(inc: Incident): { label: string; kind: "open" | "update" | "end" } {
  if (inc.is_end) return { label: "END", kind: "end" };
  const etat = (inc.etat ?? "").trim();
  if (/update/i.test(etat)) return { label: etat.toUpperCase(), kind: "update" };
  if (/new/i.test(etat)) return { label: "NEW", kind: "open" };
  return { label: etat || "EN COURS", kind: "open" };
}

function stateBadge(inc: Incident) {
  return stateMeta(inc);
}

// ---- SVG de téléchargement ---------------------------------------------
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

function IncidentTable({ incidents }: { incidents: Incident[] }) {
  if (incidents.length === 0) {
    return (
      <div className={styles.empty}>
        Aucun incident enregistré pour le moment. Lancez le pipeline
        (whatsapp.py / generator.py) pour insérer vos premières lignes.
      </div>
    );
  }

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th className={`${styles.stickyCol} ${styles.stickyFirst}`}>TT</th>
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
            const badge = stateBadge(inc);
            return (
              <tr key={inc.id}>
                <td
                  className={`${styles.mono} ${styles.stickyCol} ${styles.stickyFirst}`}
                >
                  {inc.tt ?? "—"}
                </td>
                <td className={styles.strong}>{inc.site ?? "—"}</td>
                <td>
                  <span
                    className={`${styles.badge} ${styles[`badge${badge.kind}`]}`}
                  >
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
                <td>{inc.porteur ?? "—"}</td>
                <td className={styles.truncate} title={inc.cause ?? ""}>
                  {inc.cause ?? "—"}
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
                >
                  <DownloadLink incident={inc} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DownloadLink({ incident }: { incident: Incident }) {
  if (!incident.docx_url) {
    return <span className={styles.noFiche}>—</span>;
  }
  return (
    <a
      className={styles.download}
      href={incident.docx_url}
      target="_blank"
      rel="noopener noreferrer"
      download={incident.docx_name ?? undefined}
      title={`Télécharger ${incident.docx_name ?? "la fiche"}`}
    >
      <DownloadIcon />
      <span>Fiche</span>
    </a>
  );
}

export default async function Home() {
  const incidents = await fetchIncidents();

  const total = incidents.length;
  const ended = incidents.filter((i) => i.is_end).length;
  const open = total - ended;
  const sites = new Set(incidents.map((i) => i.site).filter(Boolean)).size;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <div className={styles.eyebrow}>Camtel · Maroua</div>
          <h1 className={styles.title}>Incidents Mobile</h1>
          <p className={styles.subtitle}>
            Fiches de relevé générées depuis WhatsApp — stockées dans Supabase
          </p>
        </div>
        <div className={styles.updated}>
          <span className={styles.dot} />
          Temps réel
        </div>
      </header>

      <section className={styles.stats}>
        <StatCard
          label="Au total"
          value={total}
          icon={<StatIcon name="total" />}
          accent
        />
        <StatCard
          label="Terminés (END)"
          value={ended}
          icon={<StatIcon name="closed" />}
        />
        <StatCard
          label="En cours / UPDATE"
          value={open}
          icon={<StatIcon name="open" />}
        />
        <StatCard
          label="Sites distincts"
          value={sites}
          icon={<StatIcon name="sites" />}
        />
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Historique des incidents</h2>
          <span className={styles.count}>{total} ligne(s)</span>
        </div>
        <IncidentTable incidents={incidents} />
      </section>
    </main>
  );
}