import { createClient } from "@supabase/supabase-js";

// Ce module n'est importé QUE dans des Server Components (côté serveur).
// Les variables d'environnement sont lues sur le serveur uniquement, jamais
// envoyées au navigateur.
const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export function getSupabaseAdmin() {
  // serveur-only : la clé service_role n'est pas exposée au client.
  const svcKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !anonKey || !svcKey) {
    throw new Error(
      "Variables Supabase manquantes. Renommez .env.local à la racine du repo " +
        "en dashboard/.env.local (NEXT_PUBLIC_SUPABASE_URL, " +
        "NEXT_PUBLIC_SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY)."
    );
  }
  // service_role bypass RLS : utile côté serveur pour lire toutes les lignes.
  return createClient(url, svcKey);
}