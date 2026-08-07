import { fetchIncidents } from "@/lib/incidents";
import { FILTERS, filterIncidents, countByStatus, FILTER_TO_STATUS } from "@/lib/status";
import type { IncidentFilter } from "@/lib/status";
import IncidentBrowser from "@/components/IncidentBrowser";
import styles from "./page.module.css";

// Données toujours fraîches à chaque requête : on lit Supabase au moment où le
// client charge la page, pas lors du build (pas de pré-render statique).
export const dynamic = "force-dynamic";

// Valeurs de searchParams acceptées pour l'onglet « statut ».
const VALID_FILTERS: IncidentFilter[] = ["tous", "termines", "encours", "nouveaux"];

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

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ statut?: string }>;
}) {
  const { statut } = await searchParams;
  const filter: IncidentFilter =
    statut && (VALID_FILTERS as string[]).includes(statut)
      ? (statut as IncidentFilter)
      : "tous";

  const incidents = await fetchIncidents();

  const counts = countByStatus(incidents);
  const total = counts.tous;
  const ended = counts.end;
  const open = counts.open;
  const sites = new Set(incidents.map((i) => i.site).filter(Boolean)).size;

  const filtered = filterIncidents(incidents, filter);

  const tabCount = (f: (typeof FILTERS)[number]["value"]) =>
    f === "tous" ? counts.tous : counts[FILTER_TO_STATUS[f]];

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <div className={styles.eyebrow}>Camtel · Maroua</div>
          <h1 className={styles.title}>Incidents Mobile</h1>
          <p className={styles.subtitle}>
            Fiches de relevé générées depuis WhatsApp - stockées dans Supabase
          </p>
        </div>
        <div className={styles.updated}>
          <span className={styles.bullet} aria-hidden="true" />
          En direct
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
          <span className={styles.count}>{filtered.length} ligne(s)</span>
        </div>

        <nav className={styles.tabs} aria-label="Filtrer par état">
          {FILTERS.map((f) => {
            const active = filter === f.value;
            return (
              <a
                key={f.value}
                href={`?statut=${f.value}`}
                aria-current={active ? "page" : undefined}
                className={`${styles.tab} ${active ? styles.tabActive : ""}`}
              >
                {f.label}
                <span className={styles.tabCount}>{tabCount(f.value)}</span>
              </a>
            );
          })}
        </nav>

        <IncidentBrowser incidents={filtered} />
      </section>

      <footer className={styles.footer}>
        <span className={styles.footerText}>
          Réalisé par <strong>Hmksenpai</strong>
        </span>
        <span className={styles.footerSep} aria-hidden="true" />
        <nav className={styles.footerLinks} aria-label="À propos du créateur">
          <a
            href="https://cloudfoliooo.netlify.app/"
            target="_blank"
            rel="noopener noreferrer"
            className={styles.footerLink}
          >
            Portfolio
          </a>
          <a
            href="https://github.com/HmkSenpai"
            target="_blank"
            rel="noopener noreferrer"
            className={styles.footerLink}
          >
            GitHub
          </a>
        </nav>
      </footer>
    </main>
  );
}