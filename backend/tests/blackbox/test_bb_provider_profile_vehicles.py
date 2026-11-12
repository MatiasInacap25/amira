"""Provider publication and private vehicle ownership and upload partitions."""

from uuid import UUID
import pytest


@pytest.mark.parametrize('actor', ['customer', 'driver'])
def test_provider_owner_only_routes(api, headers, actor):
    """odd/tasks/panel-proveedores.md S3; README.md#provider-vehicles-private-supabase-storage-bucket: owner only."""
    for path in ['/api/provider/profile', '/api/provider/vehicles']:
        assert api.get(path, headers=headers(actor)).status_code == 403
    assert api.post('/api/provider/profile/publish', headers=headers(actor)).status_code == 403


def test_profile_draft_publish_and_unpublish(api, headers, seed):
    """odd/tasks/panel-proveedores.md S3: incomplete PUT auto-unpublishes; publish saves visibility only when complete."""
    body = {'description': None, 'commune_code': None, 'service_type_ids': [], 'name': 'Blackbox provider'}
    saved = api.put('/api/provider/profile', headers=headers('owner'), json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()['published'] is False
    assert saved.json()['missing'] == ['description', 'commune', 'service_types']
    assert api.post('/api/provider/profile/publish', headers=headers('owner')).status_code == 422
    assert seed['owner']['profile'] not in {item['profileId'] for item in api.get('/api/services').json()['items']}
    complete = body | {'description': 'Transport provider', 'commune_code': '13101', 'service_type_ids': [seed['service_type']]}
    assert api.put('/api/provider/profile', headers=headers('owner'), json=complete).status_code == 200
    assert api.post('/api/provider/profile/publish', headers=headers('owner')).json()['published'] is True
    assert seed['owner']['profile'] in {item['profileId'] for item in api.get('/api/services').json()['items']}
    assert api.post('/api/provider/profile/unpublish', headers=headers('owner')).json()['published'] is False
    assert api.get(f"/api/providers/{seed['owner']['profile']}").status_code == 404


@pytest.mark.parametrize('change', [{'description': 'x'}, {'description': 'x', 'commune_code': '99999', 'service_type_ids': []}, {'description': 'x', 'commune_code': '13101', 'service_type_ids': [str(UUID(int=1))]}, {'description': 'x', 'commune_code': '13101', 'service_type_ids': [], 'actor': 'forged'}])
def test_profile_invalid_save_has_no_write(api, headers, change):
    """odd/tasks/panel-proveedores.md S3: required keys, unknown communes/types and strict OpenAPI ProviderProfileUpdate."""
    before = api.get('/api/provider/profile', headers=headers('owner')).json()
    assert api.put('/api/provider/profile', headers=headers('owner'), json=change).status_code == 422
    assert api.get('/api/provider/profile', headers=headers('owner')).json() == before


@pytest.mark.parametrize('field,value,status', [('year', 1885, 422), ('year', 1886, 201), ('year', 2200, 201), ('year', 2201, 422), ('maximum_weight', 0, 422), ('maximum_weight', 1, 201)])
def test_vehicle_numeric_boundaries(api, headers, photo, db, field, value, status):
    """README.md#provider-vehicles-private-supabase-storage-bucket: year 1886..2200, weight above zero."""
    before = db.execute('SELECT count(*) FROM "Vehiculo"').fetchone()[0]
    response = api.post('/api/provider/vehicles', headers=headers('owner'), data={'plate': 'NEW123', 'brand': 'Test', 'model': 'Truck', field: str(value)}, files={'photo': ('truck.png', photo, 'image/png')})
    assert response.status_code == status, response.text
    assert db.execute('SELECT count(*) FROM "Vehiculo"').fetchone()[0] == before + (status == 201)


@pytest.mark.parametrize('size,prefix,status', [(4, b'text', 415), (5 * 1024 * 1024, b'\x89PNG\r\n\x1a\n', 201), (5 * 1024 * 1024 + 1, b'\x89PNG\r\n\x1a\n', 413)])
def test_vehicle_file_boundaries(api, headers, size, prefix, status):
    """README.md#provider-vehicles-private-supabase-storage-bucket: byte-detected photo, chat 5 MiB size cap."""
    response = api.post('/api/provider/vehicles', headers=headers('owner'), data={'plate': 'NEW123', 'brand': 'Test', 'model': 'Truck'}, files={'photo': ('trick.txt', prefix + b'\0' * max(0, size - len(prefix)), 'text/plain')})
    assert response.status_code == status, response.text


def test_vehicle_duplicate_and_idor_delete(api, headers, seed, photo, db):
    """README.md#provider-vehicles-private-supabase-storage-bucket: normalized plate unique, foreign vehicle same 404."""
    response = api.post('/api/provider/vehicles', headers=headers('owner'), data={'plate': ' bb1234 ', 'brand': 'Test', 'model': 'Truck'}, files={'photo': ('truck.png', photo, 'image/png')})
    assert response.status_code == 409, response.text
    path = f"/api/provider/vehicles/{seed['vehicle']}"
    foreign = api.delete(path, headers=headers('outsider'))
    missing = api.delete('/api/provider/vehicles/' + str(UUID(int=1)), headers=headers('outsider'))
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert api.get('/api/provider/vehicles', headers=headers('outsider')).json()['items'] == []
    assert api.delete(path, headers=headers('owner')).status_code == 204
    assert db.execute('SELECT count(*) FROM "Vehiculo"').fetchone()[0] == 0


def test_assigned_vehicle_cannot_be_deleted(api, headers, assigned_service, seed, db):
    """README.md#provider-vehicles-private-supabase-storage-bucket: referenced vehicle deletion returns 409."""
    response = api.delete(f"/api/provider/vehicles/{seed['vehicle']}", headers=headers('owner'))
    assert response.status_code == 409, response.text
    assert db.execute('SELECT count(*) FROM "Vehiculo"').fetchone()[0] == 1


@pytest.mark.parametrize('size,prefix,status', [(4, b'text', 415), (5 * 1024 * 1024, b'\x89PNG\r\n\x1a\n', 201), (5 * 1024 * 1024 + 1, b'\x89PNG\r\n\x1a\n', 413)])
def test_request_image_file_boundaries(api, headers, create_request, db, size, prefix, status):
    """README.md#request-images-private-supabase-storage-bucket; OpenAPI POST images (201): MIME bytes, 5 MiB, owner-only image upload."""
    request_id = create_request()
    response = api.post(f'/api/requests/{request_id}/images', headers=headers(), files={'photo': ('trick.txt', prefix + b'\0' * max(0, size - len(prefix)), 'text/plain')})
    assert response.status_code == status, response.text
    assert db.execute('SELECT count(*) FROM "Imagenes_Formulario"').fetchone()[0] == (1 if status == 201 else 0)


def test_request_image_count_and_visibility(api, headers, create_request, photo, db):
    """README.md#request-images-private-supabase-storage-bucket: max five, sixth 409, read owner/provider only."""
    request_id = create_request()
    base = f'/api/requests/{request_id}/images'
    for _ in range(5):
        response = api.post(base, headers=headers(), files={'photo': ('cargo.png', photo, 'image/png')})
        assert response.status_code == 201, response.text
        assert set(response.json()) == {'imageId'}
    assert api.post(base, headers=headers(), files={'photo': ('sixth.png', photo, 'image/png')}).status_code == 409
    assert db.execute('SELECT count(*) FROM "Imagenes_Formulario"').fetchone()[0] == 5
    assert api.get(base, headers=headers()).status_code == 200
    assert api.get(base, headers=headers('owner')).status_code == 200
    assert api.get(base, headers=headers('other')).status_code == api.get(f'/api/provider/requests/{request_id}', headers=headers('other')).status_code == 403
    assert api.post(base, headers=headers('other'), files={'photo': ('foreign.png', photo, 'image/png')}).status_code == 404


@pytest.mark.parametrize('prefix,content_type', [(b'\xff\xd8\xff\xe0', 'image/jpeg'), (b'\x89PNG\r\n\x1a\n', 'image/png'), (b'RIFF\x00\x00\x00\x00WEBP', 'image/webp')])
def test_documented_image_type_partitions(api, headers, create_request, prefix, content_type):
    """README.md#request-images-private-supabase-storage-bucket: JPEG/PNG/WebP determined by bytes, not MIME."""
    request_id = create_request()
    response = api.post(f'/api/requests/{request_id}/images', headers=headers(), files={'photo': ('untrusted.bin', prefix + b'\0' * 32, 'application/octet-stream')})
    assert response.status_code == 201, response.text
