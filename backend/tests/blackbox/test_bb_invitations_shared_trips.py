"""Company invitation validation and shared-trip publication and join lifecycle."""

from urllib.parse import parse_qs, urlparse
from uuid import UUID
import pytest

INVITATIONS = '/api/company/profiles/me/driver-invitations'


@pytest.mark.parametrize('body', [{}, {'email': 'x'}, {'email': 'not-an-email'}, {'email': 'driver@example.invalid', 'actor': 'forged'}])
def test_invitation_validation(api, headers, db, body):
    """OpenAPI InvitationCreate: email, length, additionalProperties=false; caja-negra.md S3 invalid input."""
    response = api.post(INVITATIONS, headers=headers('owner'), json=body)
    assert response.status_code == 422, response.text
    assert db.execute('SELECT count(*) FROM "DriverInvitation"').fetchone()[0] == 0


@pytest.mark.parametrize('actor', ['customer', 'driver'])
def test_invitation_company_owner_only(api, headers, actor):
    """OpenAPI company/profiles/me driver-invitations; caja-negra.md S3 wrong-role decision table."""
    assert api.get(INVITATIONS, headers=headers(actor)).status_code == 403


@pytest.mark.parametrize('body', [{'token': 'short'}, {'token': 'x' * 129}, {'token': '!' * 32}, {'token': 'x' * 32, 'actor': 'forged'}])
def test_invitation_accept_token_validation(api, headers, db, body):
    """OpenAPI InvitationAccept: URL-safe token 32..128 chars and no unknown fields."""
    before = db.execute('SELECT count(*) FROM "Conductor"').fetchone()[0]
    response = api.post('/api/driver-invitations/accept', headers=headers(), json=body)
    assert response.status_code == 422, response.text
    assert db.execute('SELECT count(*) FROM "Conductor"').fetchone()[0] == before


def test_invitation_lists_are_scoped(api, headers, seed, db):
    """caja-negra.md S3 owner/non-owner IDOR; OpenAPI InvitationList and revoke operation."""
    invitation_id = db.execute('INSERT INTO "DriverInvitation" (company_profile_id,target_email,token_hash,created_by_user_id,expires_at) VALUES (%s,\'invitee@blackbox.invalid\',\'blackbox-hash\',%s,now()+interval \'7 days\') RETURNING id', (seed['owner']['profile'], seed['owner']['id'])).fetchone()[0]
    owner = api.get(INVITATIONS, headers=headers('owner'))
    assert owner.status_code == 200
    assert str(invitation_id) in {item['id'] for item in owner.json()['invitations']}
    assert api.get(INVITATIONS, headers=headers('outsider')).json()['invitations'] == []
    assert api.delete(INVITATIONS + '/' + str(invitation_id), headers=headers('outsider')).status_code == 404
    assert api.delete(INVITATIONS + '/' + str(invitation_id), headers=headers('owner')).status_code == 200


@pytest.fixture
def shared_trip(api, headers, paid_service, seed):
    response = api.post(f"/api/provider/services/{paid_service['service']}/shared-trip", headers=headers('owner'), json={'vehicleId': seed['vehicle'], 'driverId': seed['driver']['driver']})
    assert response.status_code == 201, response.text
    return paid_service | {'trip': response.json()['tripId']}


def test_publish_and_close_shared_trip(api, headers, shared_trip, seed):
    """README.md#shared-trips: publish paid shareable route, provider-only trip id, close keeps linked services."""
    trip_id = shared_trip['trip']
    route = api.get('/api/shared-routes').json()['items']
    assert trip_id in {item['tripId'] for item in route}
    for actor, side, expected in [('owner', 'provider', trip_id), ('customer', 'customer', None)]:
        response = api.get(f"/api/{side}/services/{shared_trip['service']}", headers=headers(actor))
        assert response.status_code == 200
        assert response.json()['sharedTripId'] == expected
    provider_list = api.get('/api/provider/shared-trips', headers=headers('owner')).json()
    assert provider_list['items'][0]['joinedServices'] == 1
    assert api.get('/api/provider/shared-trips', headers=headers('outsider')).json()['items'] == []
    assert api.post(f'/api/provider/shared-trips/{trip_id}/close', headers=headers('outsider')).status_code == 404
    closed = api.post(f'/api/provider/shared-trips/{trip_id}/close', headers=headers('owner'))
    assert closed.status_code == 200 and closed.json()['acceptsRequests'] is False
    assert trip_id not in {item['tripId'] for item in api.get('/api/shared-routes').json()['items']}
    assert api.get(f"/api/provider/services/{shared_trip['service']}", headers=headers('owner')).json()['sharedTripId'] == trip_id


@pytest.mark.parametrize('accepts', [False, None])
def test_join_requires_explicit_sharing(api, headers, shared_trip, request_body, db, accepts):
    """README.md#shared-trips: requestedTripId requires acceptsSharing=true; omission also 422 with no writes."""
    before = db.execute('SELECT count(*) FROM "Formulario_servicio"').fetchone()[0]
    body = request_body | {'requestedTripId': shared_trip['trip']}
    if accepts is None:
        body.pop('acceptsSharing')
    else:
        body['acceptsSharing'] = accepts
    response = api.post('/api/service-requests', headers=headers('other'), json=body)
    assert response.status_code == 422, response.text
    assert ['body', 'acceptsSharing'] in [error['loc'] for error in response.json()['detail']]
    assert db.execute('SELECT count(*) FROM "Formulario_servicio"').fetchone()[0] == before


def test_join_trip_profile_and_closed_guards(api, headers, shared_trip, request_body, seed, db):
    """README.md#shared-trips: wrong requested profile=404, closed trip=409, no join written."""
    before = db.execute('SELECT count(*) FROM "Formulario_servicio"').fetchone()[0]
    body = request_body | {'requestedTripId': shared_trip['trip'], 'profileId': seed['outsider']['profile']}
    assert api.post('/api/service-requests', headers=headers('other'), json=body).status_code == 404
    assert api.post(f"/api/provider/shared-trips/{shared_trip['trip']}/close", headers=headers('owner')).status_code == 200
    body['profileId'] = seed['owner']['profile']
    assert api.post('/api/service-requests', headers=headers('other'), json=body).status_code == 409
    assert db.execute('SELECT count(*) FROM "Formulario_servicio"').fetchone()[0] == before


def test_second_customer_paid_join_keeps_chats_and_services_separate(api, headers, shared_trip, request_body, quote_body, db):
    """README.md#shared-trips; odd/tasks/viajes-compartidos.md S2: paid join links stops, separate customer chat/payment."""
    joined_request = api.post('/api/service-requests', headers=headers('other'), json=request_body | {'requestedTripId': shared_trip['trip']})
    assert joined_request.status_code == 201, joined_request.text
    request_id = joined_request.json()['requestId']
    accepted = api.post(f'/api/provider/requests/{request_id}/accept', headers=headers('owner'))
    assert accepted.status_code == 200
    chat_id = accepted.json()['chatId']
    assert chat_id != shared_trip['chat']
    quotation = api.post(f'/api/chats/{chat_id}/quotations', headers=headers('owner'), json=quote_body)
    assert quotation.status_code == 201
    checkout = api.post(f"/api/quotations/{quotation.json()['quotationId']}/payments", headers=headers('other'))
    assert checkout.status_code == 201
    payment = checkout.json()
    checkout_token = parse_qs(urlparse(payment['checkoutUrl']).query)['token'][0]
    # Closing after acceptance must not discard the accepted join.
    assert api.post(f"/api/provider/shared-trips/{shared_trip['trip']}/close", headers=headers('owner')).status_code == 200
    result = api.post(f"/api/payments/simulated/{payment['paymentId']}/complete", headers=headers('other'), json={'token': checkout_token, 'approve': True})
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'approved'
    second_service = result.json()['serviceId']
    assert second_service != shared_trip['service']
    assert api.get(f'/api/customer/services/{second_service}', headers=headers()).status_code == 404
    assert api.get(f'/api/chats/{chat_id}/messages', headers=headers()).status_code == 404
    assert api.get(f"/api/chats/{shared_trip['chat']}/messages", headers=headers('other')).status_code == 404
    assert api.get(f'/api/provider/services/{second_service}', headers=headers('owner')).json()['sharedTripId'] == shared_trip['trip']
    orders = db.execute('SELECT "Orden" FROM "Parada_Viaje" WHERE "ID_Viaje"=%s ORDER BY "Orden"', (shared_trip['trip'],)).fetchall()
    assert [row[0] for row in orders] == [1, 2, 3, 4]
    assert db.execute('SELECT count(*) FROM "Servicio"').fetchone()[0] == 2


def test_default_request_is_exclusive(api, headers, request_body, db):
    """odd/tasks/viajes-compartidos.md S1: sharing defaults to not accepted, stored exclusive."""
    body = request_body.copy()
    body.pop('acceptsSharing')
    response = api.post('/api/service-requests', headers=headers(), json=body)
    assert response.status_code == 201
    assert db.execute('SELECT es_exclusivo FROM "Formulario_servicio" WHERE "ID"=%s', (response.json()['requestId'],)).fetchone()[0] is True


def test_exclusive_service_cannot_publish_trip(api, headers, paid_service, seed, db):
    """README.md#shared-trips: exclusive service refuses publication with 409 and unchanged rows."""
    db.execute('UPDATE "Servicio" SET es_exclusivo=true WHERE "ID"=%s', (paid_service['service'],))
    before = db.execute('SELECT count(*) FROM "Viaje"').fetchone()[0]
    response = api.post(f"/api/provider/services/{paid_service['service']}/shared-trip", headers=headers('owner'), json={'vehicleId': seed['vehicle'], 'driverId': seed['driver']['driver']})
    assert response.status_code == 409, response.text
    assert db.execute('SELECT count(*) FROM "Viaje"').fetchone()[0] == before
    assert db.execute('SELECT "ID_Viaje" FROM "Servicio" WHERE "ID"=%s', (paid_service['service'],)).fetchone()[0] is None


def test_duplicate_publication_does_not_duplicate_trip(api, headers, shared_trip, seed, db):
    """README.md#shared-trips: service that already has a trip refuses a duplicate publication with 409."""
    before = db.execute('SELECT count(*) FROM "Viaje"').fetchone()[0]
    response = api.post(f"/api/provider/services/{shared_trip['service']}/shared-trip", headers=headers('owner'), json={'vehicleId': seed['vehicle'], 'driverId': seed['driver']['driver']})
    assert response.status_code == 409
    assert db.execute('SELECT count(*) FROM "Viaje"').fetchone()[0] == before
