// Node resolve hook for unit tests: maps the "@/" alias used by src/ to frontend/src/
// and resolves extensionless specifiers to .ts/.tsx or index files, as Next.js does.
const SRC_ROOT = new URL("../../src/", import.meta.url);
const SUFFIXES = ["", ".ts", ".tsx", "/index.ts", "/index.tsx"];

async function resolveWithSuffixes(baseHref, context, nextResolve) {
  let lastError;
  for (const suffix of SUFFIXES) {
    try {
      return await nextResolve(baseHref + suffix, context);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

export async function resolve(specifier, context, nextResolve) {
  if (specifier.startsWith("@/")) {
    return resolveWithSuffixes(new URL(specifier.slice(2), SRC_ROOT).href, context, nextResolve);
  }
  const isRelative = specifier.startsWith("./") || specifier.startsWith("../");
  if (!isRelative || !context.parentURL) return nextResolve(specifier, context);
  try {
    return await nextResolve(specifier, context);
  } catch (error) {
    if (error?.code !== "ERR_MODULE_NOT_FOUND") throw error;
    return resolveWithSuffixes(new URL(specifier, context.parentURL).href, context, nextResolve);
  }
}
