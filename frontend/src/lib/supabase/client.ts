import { createBrowserClient } from "@supabase/ssr";

export function createClient(
  config = {
    url: process.env.NEXT_PUBLIC_SUPABASE_URL,
    publishableKey: process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  },
) {
  const { url, publishableKey } = config;

  if (!url || !publishableKey) {
    throw new Error("Supabase environment variables are not configured.");
  }

  let parsedUrl: URL;
  try {
    parsedUrl = new URL(url);
  } catch {
    throw new Error("Supabase URL must be an absolute HTTP(S) URL.");
  }
  if (!["http:", "https:"].includes(parsedUrl.protocol) || parsedUrl.username || parsedUrl.password) {
    throw new Error("Supabase URL must be an absolute HTTP(S) URL.");
  }

  return createBrowserClient(parsedUrl.toString().replace(/\/$/, ""), publishableKey);
}
