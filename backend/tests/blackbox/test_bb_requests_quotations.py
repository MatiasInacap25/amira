"""Request and quotation HTTP boundary and lifecycle checks."""

from uuid import UUID
import pytest


@pytest.mark.parametrize('field,value', [('origin', ''), ('destination', ''), ('origin', 'x' * 301),
    ('originCommuneCode', '1310'), ('destinationCommuneCode', '051011'), ('profileId', 'bad'),
    ('estimatedWeight', -1), ('estimatedVolume', -1), ('unknownActor', 'forged')])
def test_request_validation_has_no_writes(api, headers, request_body, db, field, value):
    """OpenAPI ServiceRequestCreate: required addresses, CUT, UUID, nonnegative cargo, strict fields."""
    before = db.execute('SELECT count(*) FROM "Formulario_servicio"').fetchone()[0]
    response = api.post('/api/service-requests', headers=headers(), json=request_body | {field: value})
    assert response.status_code == 422, response.text
    assert db.execute('SELECT count(*) FROM "Formulario_servicio"').fetchone()[0] == before
    assert db.execute('SELECT count(*) FROM "Chat"').fetchone()[0] == 0


@pytest.mark.parametrize('actor', ['owner', 'driver'])
def test_only_customer_creates_request(api, headers, request_body, db, actor):
    """odd/tasks/caja-negra.md S3: wrong-role authorization table; OpenAPI customer service request operation."""
    response = api.post('/api/service-requests', headers=headers(actor), json=request_body)
    assert response.status_code == 403, response.text
    assert db.execute('SELECT count(*) FROM "Formulario_servicio"').fetchone()[0] == 0


def test_request_acceptance_and_scoping(api, headers, create_request, seed, db):
    """odd/tasks/caja-negra.md S3 request→quotation lifecycle and owner/non-owner IDOR; OpenAPI request decisions."""
    request_id = create_request()
    assert db.execute('SELECT "ID_Usuario"::text FROM "Formulario_servicio" WHERE "ID"=%s', (request_id,)).fetchone()[0] == seed['customer']['id']
    assert db.execute('SELECT count(*) FROM "Chat"').fetchone()[0] == 0
    detail = api.get(f'/api/provider/requests/{request_id}', headers=headers('owner'))
    assert detail.status_code == 200
    assert 'blackbox.invalid' not in detail.text
    assert api.get(f'/api/provider/requests/{request_id}', headers=headers('outsider')).status_code == 404
    accepted = api.post(f'/api/provider/requests/{request_id}/accept', headers=headers('owner'))
    assert accepted.status_code == 200, accepted.text
    chat_id = accepted.json()['chatId']
    assert chat_id is not None
    assert db.execute('SELECT count(*) FROM "Chat_participantes" WHERE "ID_Chat"=%s', (chat_id,)).fetchone()[0] == 2
    assert db.execute('SELECT count(*) FROM "Chat"').fetchone()[0] == 1


def test_rejected_request_never_creates_chat(api, headers, create_request, db):
    """odd/tasks/caja-negra.md S3 state transitions; duplicate-request policy is unspecified; OpenAPI request reject operation."""
    request_id = create_request()
    assert api.post(f'/api/provider/requests/{request_id}/reject', headers=headers('owner')).status_code == 200
    assert 400 <= api.post(f'/api/provider/requests/{request_id}/accept', headers=headers('owner')).status_code < 500
    assert db.execute('SELECT count(*) FROM "Chat"').fetchone()[0] == 0


@pytest.mark.parametrize('field,value,status', [('amount', 0, 422), ('amount', 1, 201), ('amount', 1.5, 422),
    ('validityHours', 0, 422), ('validityHours', 1, 201), ('validityHours', 168, 201), ('validityHours', 169, 422),
    ('description', '', 422), ('description', 'x' * 1000, 201), ('description', 'x' * 1001, 422)])
def test_quotation_boundaries(api, headers, accepted_chat, quote_body, db, field, value, status):
    """OpenAPI QuotationCreate: positive integer CLP, validity 1..168, description 1..1000."""
    response = api.post(f"/api/chats/{accepted_chat['chat']}/quotations", headers=headers('owner'), json=quote_body | {field: value})
    assert response.status_code == status, response.text
    assert db.execute('SELECT count(*) FROM "Cotizacion"').fetchone()[0] == (1 if status == 201 else 0)


@pytest.mark.parametrize('actor,status', [('customer', 403), ('other', 404), ('outsider', 404)])
def test_quotation_actor_table(api, headers, accepted_chat, quote_body, db, actor, status):
    """odd/tasks/caja-negra.md S3 provider quotation/customer payment and participant IDOR decision table."""
    response = api.post(f"/api/chats/{accepted_chat['chat']}/quotations", headers=headers(actor), json=quote_body)
    assert response.status_code == status, response.text
    assert db.execute('SELECT count(*) FROM "Cotizacion"').fetchone()[0] == 0


def test_quotation_reject_then_pay_is_refused(api, headers, quotation, db):
    """odd/tasks/caja-negra.md S3: reject quotation then payment must be rejected, with no reservation."""
    path = f"/api/quotations/{quotation['quotation']}"
    assert api.post(path + '/reject', headers=headers()).status_code == 200
    assert api.post(path + '/payments', headers=headers()).status_code == 409
    assert db.execute('SELECT count(*) FROM "Pago"').fetchone()[0] == 0
    assert db.execute('SELECT count(*) FROM "Servicio"').fetchone()[0] == 0


@pytest.mark.parametrize('identifier,status', [('bad', 422), (str(UUID(int=1)), 404)])
def test_unknown_quotation(api, headers, identifier, status):
    """OpenAPI /api/quotations/{quotation_id}/reject UUID; odd/tasks/caja-negra.md S3 unknown-ID partition."""
    assert api.post(f'/api/quotations/{identifier}/reject', headers=headers()).status_code == status
