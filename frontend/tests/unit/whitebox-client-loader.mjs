// Substitute only browser SDK wiring; the application access rules remain real.
export async function resolve(specifier, context, nextResolve) {
  if (specifier === "@/lib/supabase/client") {
    return {
      url: `data:text/javascript,${encodeURIComponent("export function createClient() { return globalThis.__whiteboxSupabase; }")}`,
      shortCircuit: true,
    };
  }
  return nextResolve(specifier, context);
}
