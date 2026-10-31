import assert from "node:assert/strict";
import { test } from "node:test";
import { postLoginPath, safeNextPath } from "../../src/lib/post-login-path.ts";

const FALLBACK = "/servicios";

test("safeNextPath rejects protocol-relative and absolute external URLs", () => {
  assert.equal(safeNextPath("//evil.example"), FALLBACK);
  assert.equal(safeNextPath("https://evil.example"), FALLBACK);
  assert.equal(safeNextPath("/\\evil.example"), FALLBACK);
  assert.equal(safeNextPath(null), FALLBACK);
});

test("safeNextPath keeps same-origin absolute paths with search and hash", () => {
  assert.equal(safeNextPath("/cuenta/perfil"), "/cuenta/perfil");
  assert.equal(safeNextPath("/servicios?q=grua#resultados"), "/servicios?q=grua#resultados");
});

test("sends independent drivers to /panel when there is no explicit next", () => {
  assert.equal(postLoginPath({ role: "independent_driver", explicitNext: null, fallback: FALLBACK }), "/panel");
});

test("sends company owners to /panel when there is no explicit next", () => {
  assert.equal(postLoginPath({ role: "company_owner", explicitNext: null, fallback: FALLBACK }), "/panel");
});

test("sends company drivers to /panel when there is no explicit next", () => {
  assert.equal(postLoginPath({ role: "company_driver", explicitNext: null, fallback: FALLBACK }), "/panel");
});

test("keeps the fallback destination for clients", () => {
  assert.equal(postLoginPath({ role: "client", explicitNext: null, fallback: FALLBACK }), FALLBACK);
});

test("an explicit safe next wins over /panel for providers", () => {
  assert.equal(
    postLoginPath({ role: "independent_driver", explicitNext: "/cuenta/servicios?tab=activos", fallback: FALLBACK }),
    "/cuenta/servicios?tab=activos",
  );
});

test("an explicit safe next wins over the fallback for clients", () => {
  assert.equal(postLoginPath({ role: "client", explicitNext: "/mensajes", fallback: FALLBACK }), "/mensajes");
});

test("ignores unsafe explicit next values and uses the role rule instead", () => {
  assert.equal(postLoginPath({ role: "company_owner", explicitNext: "//evil.example", fallback: FALLBACK }), "/panel");
  assert.equal(postLoginPath({ role: "company_driver", explicitNext: "https://evil.example", fallback: FALLBACK }), "/panel");
  assert.equal(postLoginPath({ role: "client", explicitNext: "/\\evil.example", fallback: FALLBACK }), FALLBACK);
});

test("unknown, empty or missing roles use the fallback", () => {
  assert.equal(postLoginPath({ role: null, explicitNext: null, fallback: FALLBACK }), FALLBACK);
  assert.equal(postLoginPath({ role: undefined, explicitNext: null, fallback: FALLBACK }), FALLBACK);
  assert.equal(postLoginPath({ role: "", explicitNext: null, fallback: FALLBACK }), FALLBACK);
  assert.equal(postLoginPath({ role: "superadmin", explicitNext: null, fallback: FALLBACK }), FALLBACK);
});
