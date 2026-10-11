"""Supabase Storage adapter for the EvidenceStorage port, over the Storage REST API through httpx.

The service-role key bypasses bucket policies, so this adapter runs on the server only. The bucket stays private: a
photo is reachable only through a short-lived signed URL, never through a public link.
"""

from urllib.parse import quote

import httpx

from amira_api.evidence_storage import EvidenceStorageError

REQUEST_TIMEOUT_SECONDS = 10.0


class SupabaseEvidenceStorage:
    def __init__(
        self,
        *,
        base_url: str,
        service_role_key: str,
        bucket: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._storage_root = f"{base_url.rstrip('/')}/storage/v1"
        self._bucket = bucket
        self._client = httpx.Client(
            base_url=self._storage_root,
            headers={"Authorization": f"Bearer {service_role_key}", "apikey": service_role_key},
            timeout=REQUEST_TIMEOUT_SECONDS,
            transport=transport,
        )

    def upload(self, key: str, content: bytes, content_type: str) -> None:
        try:
            response = self._client.post(
                f"/object/{self._bucket}/{quote(key, safe='/')}",
                content=content,
                headers={"Content-Type": content_type, "x-upsert": "false"},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise EvidenceStorageError("Supabase Storage rejected the upload.") from error

    def delete(self, key: str) -> None:
        # The bulk remove endpoint, the same call supabase-js makes for remove(): DELETE /object/{bucket} with prefixes.
        try:
            response = self._client.request("DELETE", f"/object/{self._bucket}", json={"prefixes": [key]})
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise EvidenceStorageError("Supabase Storage could not delete the object.") from error

    def create_signed_url(self, key: str, expires_in: int) -> str:
        try:
            response = self._client.post(
                f"/object/sign/{self._bucket}/{quote(key, safe='/')}",
                json={"expiresIn": expires_in},
            )
            response.raise_for_status()
            signed_path = response.json()["signedURL"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise EvidenceStorageError("Supabase Storage could not sign the URL.") from error
        # The API returns a path relative to the Storage root, which already carries /storage/v1.
        return f"{self._storage_root}{signed_path}"
