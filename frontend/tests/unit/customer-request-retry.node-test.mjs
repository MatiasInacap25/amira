import assert from "node:assert/strict";
import { test } from "node:test";
import { sendWithTokenRetry } from "../../src/lib/customer-request-retry.ts";

function harness(statuses) {
  const sent = [];
  let refreshes = 0;
  const send = async (accessToken) => {
    sent.push(accessToken);
    return { status: statuses[sent.length - 1] };
  };
  const readAccessToken = async () => "token-a";
  const refreshAccessToken = async () => {
    refreshes += 1;
    return `token-b-${refreshes}`;
  };
  return { send, readAccessToken, refreshAccessToken, sent, refreshCount: () => refreshes };
}

test("sends once with the current token when the response is not 401", async () => {
  const h = harness([200]);
  const response = await sendWithTokenRetry(h.send, h.readAccessToken, h.refreshAccessToken);
  assert.equal(response.status, 200);
  assert.deepEqual(h.sent, ["token-a"]);
  assert.equal(h.refreshCount(), 0);
});

test("refreshes once and retries with the new token after a 401", async () => {
  const h = harness([401, 201]);
  const response = await sendWithTokenRetry(h.send, h.readAccessToken, h.refreshAccessToken);
  assert.equal(response.status, 201);
  assert.deepEqual(h.sent, ["token-a", "token-b-1"]);
  assert.equal(h.refreshCount(), 1);
});

test("does not retry a second time when the refreshed request is still 401", async () => {
  const h = harness([401, 401]);
  const response = await sendWithTokenRetry(h.send, h.readAccessToken, h.refreshAccessToken);
  assert.equal(response.status, 401);
  assert.equal(h.sent.length, 2);
  assert.equal(h.refreshCount(), 1);
});

test("does not refresh for other error statuses", async () => {
  const h = harness([500]);
  const response = await sendWithTokenRetry(h.send, h.readAccessToken, h.refreshAccessToken);
  assert.equal(response.status, 500);
  assert.equal(h.sent.length, 1);
  assert.equal(h.refreshCount(), 0);
});
