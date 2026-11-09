"""Assignment, start, GPS, completion and service visibility through real HTTP."""

from uuid import UUID
import pytest


@pytest.mark.parametrize('actor,status,manage', [('customer', 200, False), ('owner', 200, True), ('driver', 200, False), ('other', 404, None), ('outsider', 404, None)])
def test_service_visibility(api, headers, assigned_service, actor, status, manage):
    """README.md#contracted-services: owner/assigned driver/customer visibility, 404 for hidden service."""
    side = 'customer' if actor in ('customer', 'other') else 'provider'
    response = api.get(f"/api/{side}/services/{assigned_service['service']}", headers=headers(actor))
    assert response.status_code == status, response.text
    if status == 200:
        assert response.json()['canManage'] is manage
        assert 'blackbox.invalid' not in response.text
        assert '76123456-0' not in response.text
        assert not {'phone', 'email', 'rut'} & response.json().keys()


@pytest.mark.parametrize('body', [{}, {'assignments': []}, {'assignments': [{'driverId': 'bad', 'vehicleId': 'bad'}]}, {'assignments': [], 'actor': 'forged'}])
def test_assignment_body_validation(api, headers, paid_service, db, body):
    """OpenAPI ServiceAssignmentsUpdate/ServiceAssignmentPair: nonempty UUID pairs, no extra fields."""
    response = api.put(f"/api/provider/services/{paid_service['service']}/assignments", headers=headers('owner'), json=body)
    assert response.status_code == 422, response.text
    assert db.execute('SELECT count(*) FROM "Servicio_Asignacion"').fetchone()[0] == 0


@pytest.mark.parametrize('body', [None, {}, {'latitude': 91, 'longitude': 0}, {'latitude': 0, 'longitude': -181}, {'latitude': 0, 'longitude': 0, 'accuracy': -1}, {'latitude': 0, 'longitude': 0, 'accuracy': 100001}, {'latitude': 0, 'longitude': 0, 'actor': 'forged'}])
def test_start_requires_valid_location_without_transition(api, headers, assigned_service, db, body):
    """README.md#live-service-location-in-progress-services: invalid/missing position gives 422, stays confirmed."""
    response = api.post(f"/api/provider/services/{assigned_service['service']}/start", headers=headers('driver'), json=body)
    assert response.status_code == 422, response.text
    state = api.get(f"/api/customer/services/{assigned_service['service']}", headers=headers()).json()
    assert state['status'] == 'confirmed' and state['startedAt'] is None
    assert db.execute('SELECT count(*) FROM "Servicio_Ubicacion"').fetchone()[0] == 0


@pytest.mark.parametrize('position', [{'latitude': -90, 'longitude': -180, 'accuracy': 0}, {'latitude': 90, 'longitude': 180, 'accuracy': 100000}, {'latitude': 0, 'longitude': 0}])
def test_live_location_boundaries_and_authorization(api, headers, running_service, db, position):
    """README.md#live-service-location-in-progress-services: inclusive GPS bounds, driver-only writes, owner/customer reads."""
    base = f"/api/provider/services/{running_service['service']}"
    owner_write = api.put(base + '/location', headers=headers('owner'), json=position)
    assert owner_write.status_code == 403, owner_write.text
    assert api.get(base + '/location', headers=headers('outsider')).status_code == 404
    updated = api.put(base + '/location', headers=headers('driver'), json=position)
    assert updated.status_code == 200, updated.text
    for key, value in position.items():
        assert updated.json()[key] == value
    for side, actor in [('provider', 'owner'), ('provider', 'driver'), ('customer', 'customer')]:
        read = api.get(f"/api/{side}/services/{running_service['service']}/location", headers=headers(actor))
        assert read.status_code == 200
        assert read.json() == updated.json()
    assert db.execute('SELECT count(*) FROM "Servicio_Ubicacion"').fetchone()[0] == 1
    assert api.post(base + '/start', headers=headers('driver'), json=position).status_code == 409


def test_complete_before_start_is_refused(api, headers, assigned_service, photo, db):
    """caja-negra.md S3: completing before start is an invalid transition."""
    response = api.post(f"/api/provider/services/{assigned_service['service']}/complete", headers=headers('driver'), files={'photo': ('proof.png', photo, 'image/png')})
    assert response.status_code == 409, response.text
    assert db.execute('SELECT "Estado" FROM "Servicio" WHERE "ID"=%s', (assigned_service['service'],)).fetchone()[0] == 'confirmed'


@pytest.mark.parametrize('size,content,status', [(0, b'', 415), (4, b'text', 415), (8 * 1024 * 1024, b'\x89PNG\r\n\x1a\n', 200), (8 * 1024 * 1024 + 1, b'\x89PNG\r\n\x1a\n', 413)])
def test_delivery_file_boundaries(api, headers, running_service, size, content, status):
    """README.md#delivery-photos-private-supabase-storage-bucket: 8 MiB cap; PNG detected from bytes."""
    data = content + b'\0' * max(0, size - len(content))
    response = api.post(f"/api/provider/services/{running_service['service']}/complete", headers=headers('driver'), files={'photo': ('misleading.txt', data, 'text/plain')})
    assert response.status_code == status, response.text
    state = api.get(f"/api/customer/services/{running_service['service']}", headers=headers()).json()['status']
    assert state == ('completed' if status == 200 else 'in_progress')


def test_completion_deletes_live_position_and_exposes_private_photo(api, headers, completed_service, db):
    """README.md#live-service-location-in-progress-services and #delivery-photos-private-supabase-storage-bucket."""
    service_id = completed_service['service']
    assert db.execute('SELECT count(*) FROM "Servicio_Ubicacion"').fetchone()[0] == 0
    for side, actor in [('provider', 'owner'), ('customer', 'customer')]:
        base = f'/api/{side}/services/{service_id}'
        assert api.get(base + '/location', headers=headers(actor)).status_code == 404
        response = api.get(base + '/delivery-photo', headers=headers(actor))
        assert response.status_code == 200, response.text
        assert set(response.json()) == {'url', 'expiresAt'}
        assert response.json()['url'].startswith('http://127.0.0.1:')
    response = api.put(f'/api/provider/services/{service_id}/location', headers=headers('driver'), json={'latitude': 0, 'longitude': 0})
    assert response.status_code == 409
    assert api.get(f'/api/customer/services/{service_id}/delivery-photo', headers=headers('other')).status_code == 404
