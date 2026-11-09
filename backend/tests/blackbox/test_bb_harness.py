"""Harness smoke checks independent of implementation internals."""

def test_real_http_health_and_schema(api):
    """README.md#setup; odd/tasks/caja-negra.md S2: real uvicorn serves health and OpenAPI."""
    assert api.get('/health').status_code == 200
    schema = api.get('/openapi.json')
    assert schema.status_code == 200
    assert '/api/services' in schema.json()['paths']


def test_local_signed_actor(api, headers):
    """odd/tasks/caja-negra.md S2: locally signed Supabase-shaped actors reach the real API."""
    response = api.get('/api/account/me', headers=headers())
    assert response.status_code == 200, response.text
