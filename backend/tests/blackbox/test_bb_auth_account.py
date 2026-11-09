"""Authentication decision table, account roles, and strict input boundaries."""

import time
import pytest


@pytest.mark.parametrize('case', ['none', 'malformed', 'expired', 'issuer', 'audience', 'aal1', 'anonymous', 'role', 'email'])
def test_authentication_decision_table(api, headers, case):
    """README.md#development-only-sms-mfa-bypass: signature/issuer/audience/expiry/role/email/anonymous checks."""
    changes = {
        'expired': {'exp': int(time.time()) - 120}, 'issuer': {'iss': 'http://127.0.0.1/other'},
        'audience': {'aud': 'wrong'}, 'aal1': {'aal': 'aal1', 'amr': [{'method': 'password'}]},
        'anonymous': {'is_anonymous': True}, 'role': {'role': 'anon'}, 'email': {'email': ''},
    }
    auth = {} if case == 'none' else {'Authorization': 'Bearer malformed'} if case == 'malformed' else headers(**changes[case])
    response = api.get('/api/account/me', headers=auth)
    assert response.status_code in (401, 403), response.text
    assert 'PrivateSurname' not in response.text


@pytest.mark.parametrize('actor,role', [('customer', 'client'), ('other', 'client'), ('owner', 'company_owner'), ('driver', 'company_driver')])
def test_verified_actor_identity(api, headers, seed, actor, role):
    """OpenAPI AccountResponse: account identity and role come from verified JWT, not caller JSON."""
    response = api.get('/api/account/me', headers=headers(actor))
    assert response.status_code == 200, response.text
    assert response.json()['user_id'] == seed[actor]['id']
    assert response.json()['role'] == role
    assert not {'email', 'phone', 'national_id', 'birth_date'} & response.json().keys()


@pytest.mark.parametrize('body', [{}, {'code': '12345'}, {'code': '1234567'}, {'code': 'abcdef'}, {'code': '123456', 'actor': 'other'}])
def test_email_fallback_validation(api, headers, db, body):
    """OpenAPI EmailCodeRequest: six digits, additionalProperties=false; no malformed proof writes."""
    before = db.execute('SELECT count(*) FROM "EmailFallbackChallenge"').fetchone()[0]
    response = api.post('/api/account/email-fallback/verify', headers=headers(), json=body)
    assert response.status_code == 422, response.text
    assert db.execute('SELECT count(*) FROM "EmailFallbackChallenge"').fetchone()[0] == before
