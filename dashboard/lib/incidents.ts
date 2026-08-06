import "server-only";
import { getSupabaseAdmin } from "./supabase";
import type { Incident } from "./types";

/**
 * Récupère la liste des incidents, du plus récent au plus ancien.
 * Fonction serveur uniquement : elle utilise la clé service_role et ne
 * s'exécute jamais dans le navigateur.
 */
export async function fetchIncidents(): Promise<Incident[]> {
  const supabase = getSupabaseAdmin();
  const { data, error } = await supabase
    .from("incidents")
    .select("*")
    .order("created_at", { ascending: false });

  if (error) {
    // Table pas encore créée (migration non appliquée) : on log sans planter
    // la page, pour que le dashboard s'affiche avec un état "à configurer".
    console.error("[dashboard] Erreur fetch incidents :", error.message);
    return [];
  }
  return (data ?? []) as Incident[];
}