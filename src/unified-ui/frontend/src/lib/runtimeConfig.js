export const runtimeConfig = {
    // Prefer server-injected config (same as old project), fallback to Vite env
    SUPABASE_URL: window.SUPABASE_URL || import.meta.env.VITE_SUPABASE_URL || "",
    SUPABASE_ANON_KEY: window.SUPABASE_ANON_KEY || import.meta.env.VITE_SUPABASE_ANON_KEY || "",
  
  // If you ever proxy to a different host, set VITE_API_BASE_URL.
  // Otherwise keep empty (same-origin).
  API_BASE_URL: window.API_BASE_URL || import.meta.env.VITE_API_BASE_URL || "",
};
  
