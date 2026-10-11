export type StatusResponse = {
  status: number;
};

// Sends with the current access token and retries once with a refreshed token on 401.
// A second 401 is returned to the caller; no further retries happen.
export async function sendWithTokenRetry<T extends StatusResponse>(
  send: (accessToken: string) => Promise<T>,
  readAccessToken: () => Promise<string>,
  refreshAccessToken: () => Promise<string>,
): Promise<T> {
  const first = await send(await readAccessToken());
  if (first.status !== 401) return first;
  return send(await refreshAccessToken());
}
