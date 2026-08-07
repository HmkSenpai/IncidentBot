import { fetchIncidents } from "@/lib/incidents";
import LiveDashboard from "@/components/LiveDashboard";
import styles from "./page.module.css";

// Données toujours fraîches à chaque requête : on lit Supabase au moment où le
// client charge la page, pas lors du build (pas de pré-render statique).
export const dynamic = "force-dynamic";

export default async function Home() {
  const incidents = await fetchIncidents();

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

      {/* Stats, filtres, tableau et modale sont pilotés côté client et se
          rafraîchissent automatiquement (polling) sans recharger la page. */}
      <LiveDashboard initial={incidents} />

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