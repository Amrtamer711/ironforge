import { createClient } from "@supabase/supabase-js";
import { runtimeConfig } from "./runtimeConfig";

let client = null;

export function getSupabaseClient() {
  if (client) return client;

  const { SUPABASE_URL, SUPABASE_ANON_KEY } = runtimeConfig;
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) return null;

  client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  return client;
}
