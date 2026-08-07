import { fetchIncidents } from "@/lib/incidents";

// Endpoint utilisé par le composant client pour rafraîchir la liste sans
// recharger la page (polling live). Lit Supabase côté serveur avec la clé
// service_role (jamais exposée au navigateur).
export const dynamic = "force-dynamic";

export async function GET() {
  const incidents = await fetchIncidents();
  return Response.json(incidents);
}