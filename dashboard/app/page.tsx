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
    hour: "2-digit",
    minute: "2-digit",
  });
}

function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string | number;
  accent?: boolean;
}) {
  return (
    <div className={`${styles.statCard} ${accent ? styles.statAccent : ""}`}>
      <div className={styles.statValue}>{value}</div>
      <div className={styles.statLabel}>{label}</div>
    </div>
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
            <th>TT</th>
            <th>Site</th>
            <th>État</th>
            <th>Début</th>
            <th>Fin</th>
            <th>Porteur</th>
            <th>Cause</th>
            <th>Créé le</th>
            <th>Fiche</th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((inc) => (
            <tr key={inc.id}>
              <td className={styles.mono}>{inc.tt ?? "—"}</td>
              <td>{inc.site ?? "—"}</td>
              <td>
                <span
                  className={`${styles.badge} ${
                    inc.is_end ? styles.badgeEnd : styles.badgeOpen
                  }`}
                >
                  {inc.is_end ? "END" : inc.etat ?? "en cours"}
                </span>
              </td>
              <td>{formatDate(inc.debut)}</td>
              <td>{formatDate(inc.fin)}</td>
              <td>{inc.porteur ?? "—"}</td>
              <td className={styles.truncate} title={inc.cause ?? ""}>
                {inc.cause ?? "—"}
              </td>
              <td>{formatDate(inc.created_at)}</td>
              <td>
                <DownloadLink incident={inc} />
              </td>
            </tr>
          ))}
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
    >
      Télécharger
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
          <h1 className={styles.title}>Incidents CAMTEL</h1>
          <p className={styles.subtitle}>
            Fiches de relevé générées depuis WhatsApp — stockées dans Supabase
          </p>
        </div>
      </header>

      <section className={styles.stats}>
        <StatCard label="Incidents au total" value={total} accent />
        <StatCard label="Terminés (END)" value={ended} />
        <StatCard label="En cours / UPDATE" value={open} />
        <StatCard label="Sites distincts" value={sites} />
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Historique</h2>
        <IncidentTable incidents={incidents} />
      </section>
    </main>
  );
}