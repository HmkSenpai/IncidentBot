"use client";

import { useEffect, useRef, useState } from "react";
import type { Incident } from "@/lib/types";
import { statusOf } from "@/lib/status";
import styles from "@/app/page.module.css";

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

export default function IncidentBrowser({ incidents }: { incidents: Incident[] }) {
  const [selected, setSelected] = useState<Incident | null>(null);

  if (incidents.length === 0) {
    return (
      <div className={styles.empty}>
        Aucun incident dans cette catégorie pour le moment.
      </div>
    );
  }

  return (
    <>
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

      {selected && (
        <IncidentDialog
          incident={selected}
          onClose={() => setSelected(null)}
        />
      )}
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
  const panelRef = useRef<HTMLDivElement>(null);
  const badge = badgeMeta(incident);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div
        ref={panelRef}
        className={styles.ficheDialog}
        role="dialog"
        aria-modal="true"
        aria-label={`Incident ${incident.tt ?? ""}`}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <header className={styles.ficheHeader}>
          <div className={styles.ficheTitleRow}>
            <h3 className={styles.ficheTt}>{incident.tt ?? "Incident"}</h3>
            <span className={`${styles.badge} ${styles[`badge${badge.kind}`]}`}>
              {badge.label}
            </span>
            <button
              className={styles.ficheClose}
              onClick={onClose}
              aria-label="Fermer"
            >
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
          <pre className={styles.raw}>
            {incident.raw_message || "-"}
          </pre>
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