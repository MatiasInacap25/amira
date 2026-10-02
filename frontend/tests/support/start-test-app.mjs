import { cpSync, existsSync, mkdtempSync, rmSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve, sep } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const testRoot = mkdtempSync(join(tmpdir(), "amira-auth-e2e-"));
const excluded = new Set(["node_modules", ".next", ".next-e2e", "test-results", "playwright-report"]);

cpSync(frontendRoot, testRoot, {
  recursive: true,
  filter: (source) => {
    const name = basename(source);
    return !excluded.has(name) && !name.startsWith(".env");
  },
});
symlinkSync(join(frontendRoot, "node_modules"), join(testRoot, "node_modules"), "junction");

const nextCli = join(frontendRoot, "node_modules", "next", "dist", "bin", "next");
if (!existsSync(nextCli)) throw new Error("Local Next.js CLI is unavailable for isolated E2E.");
const env = Object.fromEntries([
  "PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "COMSPEC", "PATHEXT",
  "NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "NEXT_PUBLIC_API_URL",
].flatMap((key) => process.env[key] ? [[key, process.env[key]]] : []));
env.NODE_ENV = "development";
const child = spawn(process.execPath, [nextCli, "dev", "--webpack", "--hostname", "127.0.0.1", "--port", "3179"], {
  cwd: testRoot,
  env,
  stdio: "inherit",
});

const cleanup = () => {
  const temporaryRoot = resolve(tmpdir()) + sep;
  const resolvedTestRoot = resolve(testRoot);
  if (!resolvedTestRoot.startsWith(temporaryRoot)) throw new Error("Refusing to remove an unexpected E2E workspace.");
  try { rmSync(resolvedTestRoot, { recursive: true, force: true }); } catch { /* Windows may briefly retain the temporary junction. */ }
};

child.on("exit", (code, signal) => {
  cleanup();
  process.exitCode = code ?? (signal ? 1 : 0);
});
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}
