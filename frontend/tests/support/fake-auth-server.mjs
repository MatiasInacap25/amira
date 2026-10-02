import { createServer } from "node:http";
import { generateKeyPairSync, sign } from "node:crypto";

const host = "127.0.0.1";
const port = 54329;
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

const server = createServer((request, response) => {
  const url = new URL(request.url ?? "/", issuer);
  if (request.method === "OPTIONS") return send(response, 204);
  if (url.pathname === "/__health" && request.method === "GET") return send(response, 200, { ok: true });
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
