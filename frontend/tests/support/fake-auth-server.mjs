import { createServer } from "node:http";
import { generateKeyPairSync, randomUUID, sign } from "node:crypto";

const host = "127.0.0.1";
const port = Number(process.env.AMIRA_TEST_AUTH_PORT ?? 54329);
const issuer = `http://${host}:${port}/auth/v1`;
const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
const publicJwk = { ...publicKey.export({ format: "jwk" }), kid: "amira-e2e", alg: "RS256", use: "sig" };

const user = {
  id: "user-confirmed-e2e",
  aud: "authenticated",
  role: "authenticated",
  email: "confirmed@example.test",
  email_confirmed_at: "2026-10-01T12:00:00.000Z",
  confirmed_at: "2026-10-01T12:00:00.000Z",
  app_metadata: { provider: "email", providers: ["email"] },
  user_metadata: {},
  created_at: "2026-10-01T11:00:00.000Z",
  factors: [],
};

function base64url(value) {
  return Buffer.from(typeof value === "string" ? value : JSON.stringify(value)).toString("base64url");
}

function makeToken() {
  const issuedAt = Math.floor(Date.now() / 1000);
  const header = base64url({ alg: "RS256", typ: "JWT", kid: "amira-e2e" });
  const payload = base64url({
    iss: issuer,
    jti: randomUUID(),
    sub: user.id,
    aud: "authenticated",
    role: "authenticated",
    email: user.email,
    aal: "aal1",
    iat: issuedAt,
    exp: issuedAt + 3600,
  });
  const content = `${header}.${payload}`;
  return `${content}.${sign("RSA-SHA256", Buffer.from(content), privateKey).toString("base64url")}`;
}

function send(response, status, body) {
  response.writeHead(status, {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info",
    "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
    "Content-Type": "application/json",
  });
  response.end(body === undefined ? "" : JSON.stringify(body));
}

const adminTokens = new Set();

const server = createServer((request, response) => {
  const url = new URL(request.url ?? "/", issuer);
  if (request.method === "OPTIONS") return send(response, 204);
  if (url.pathname === "/__health" && request.method === "GET") return send(response, 200, { ok: true });
  if (url.pathname === "/__admin_session" && request.method === "GET") {
    const admin = url.searchParams.get("admin") === "true";
    const token = makeToken();
    if (admin) adminTokens.add(token);
    return send(response, 200, { access_token: token, refresh_token: "fake-admin-refresh", expires_at: Math.floor(Date.now() / 1000) + 3600, user });
  }
  if (url.pathname.startsWith("/api/admin/") && request.method === "GET") {
    const token = request.headers.authorization?.replace(/^Bearer /, "");
    if (!token) return send(response, 401, {});
    if (!adminTokens.has(token)) return send(response, 403, { detail: "Admin access required." });
    if (url.pathname === "/api/admin/me") return send(response, 200, { user_id: user.id, email: user.email });
    if (url.pathname === "/api/admin/badges") return send(response, 200, { documentos: 2, reclamos: 1, "cuentas-bancarias": 0, desembolsos: 0 });
    if (url.pathname === "/api/admin/finance/summary") return send(response, 200, {
      collected: 80000, refunded: 0, net_collected: 80000, payout_due: 72000, payout_due_count: 1,
      payout_blocked_count: 0, payout_paid: 0, commission_gross: 8000, commission_net: 6723, commission_iva: 1277,
      platform_iva: 1277, retained_net: 0, retained_iva: 0,
      service_counts: { in_progress: 0, completed: 1, cancelled: 0 }, pending: { documentos: 2, reclamos: 1 },
    });
    if (url.pathname === "/api/admin/finance/timeseries") return send(response, 200, [
      { day: url.searchParams.get("to"), collected: 80000, commission: 8000 },
    ]);
    if (url.pathname === "/api/admin/finance/movements") return send(response, 200, []);
    if (url.pathname === "/api/admin/finance/providers") return send(response, 200, [
      { provider: "Transportista de prueba", services: 1, gross: 80000, commission: 8000, commission_iva: 1277, net_paid: 0 },
    ]);
    if (url.pathname === "/api/admin/configuration") return send(response, 200, {
      app_env: "test", commission_percent: 10, claim_window_hours: 24, payment_adapter: "simulated", payout_adapter: "simulated",
      admins: [{ user_id: user.id, email: user.email }],
    });
    if (url.pathname === "/api/admin/audit") {
      const action = url.searchParams.get("action") ?? "rating.show";
      const items = [{ id: "audit-1", admin_user_id: user.id, action, entity_type: "rating", entity_id: "rating-1", reason: "Fixture", created_at: "2026-11-20T14:00:00Z" }];
      return send(response, 200, { items, total: 1, limit: 20, offset: 0 });
    }
  }
  if (url.pathname === "/auth/v1/.well-known/jwks.json" && request.method === "GET") {
    return send(response, 200, { keys: [publicJwk] });
  }
  if (url.pathname === "/auth/v1/signup" && request.method === "POST") {
    return send(response, 200, { user: { ...user, email_confirmed_at: null, confirmed_at: null }, session: null });
  }
  if (url.pathname === "/auth/v1/token" && request.method === "POST" && url.searchParams.get("grant_type") === "pkce") {
    let body = "";
    request.on("data", (chunk) => { body += chunk; });
    request.on("end", () => {
      const parsed = JSON.parse(body || "{}");
      if (parsed.auth_code !== "valid-confirmation-code" || !parsed.code_verifier) {
        return send(response, 400, { code: "bad_code_verifier", msg: "Invalid confirmation code." });
      }
      return send(response, 200, {
        access_token: makeToken(),
        token_type: "bearer",
        expires_in: 3600,
        expires_at: Math.floor(Date.now() / 1000) + 3600,
        refresh_token: "fake-confirmed-refresh-token",
        user,
      });
    });
    return;
  }
  if (url.pathname === "/auth/v1/user" && request.method === "GET") {
    return send(response, 200, user);
  }
  if (url.pathname === "/auth/v1/factors" && request.method === "GET") {
    return send(response, 200, { all: [], phone: [], totp: [] });
  }
  if (url.pathname === "/auth/v1/logout" && request.method === "POST") return send(response, 204);
  return send(response, 404, { message: `Unexpected local fake auth request: ${request.method} ${url.pathname}` });
});

server.listen(port, host);
