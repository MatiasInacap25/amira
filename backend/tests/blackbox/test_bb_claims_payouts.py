"""Customer claims, satisfaction consent and real local payout job."""

import subprocess
import sys
from decimal import Decimal
import pytest


@pytest.mark.parametrize('reason,status', [('', 422), (' ', 422), ('x', 200), ('x' * 1000, 200), ('x' * 1001, 422)])
def test_claim_boundaries(api, headers, completed_service, db, reason, status):
    """README.md#claims-consent-and-payout-release: trimmed reason 1..1000, claim moves service to disputed."""
    response = api.post(f"/api/customer/services/{completed_service['service']}/claims", headers=headers(), json={'reason': reason})
    assert response.status_code == status, response.text
    state = api.get(f"/api/customer/services/{completed_service['service']}", headers=headers()).json()
    assert state['status'] == ('disputed' if status == 200 else 'completed')
    assert db.execute('SELECT count(*) FROM "Reclamo"').fetchone()[0] == (1 if status == 200 else 0)


def test_consent_and_claim_are_mutually_exclusive(api, headers, completed_service, db):
    """README.md#claims-consent-and-payout-release: consent records satisfaction; no claim after consent."""
    base = f"/api/customer/services/{completed_service['service']}"
    assert api.post(base + '/consent', headers=headers()).status_code == 200
    response = api.post(base + '/claims', headers=headers(), json={'reason': 'Damage found'})
    assert response.status_code == 409, response.text
    assert db.execute('SELECT count(*) FROM "Reclamo"').fetchone()[0] == 0
    assert api.get(base, headers=headers()).json()['customerConsentAt'] is not None


def test_open_claim_blocks_consent_and_duplicate_claim(api, headers, completed_service, db):
    """README.md#claims-consent-and-payout-release: one customer action, open claim blocks consent."""
    base = f"/api/customer/services/{completed_service['service']}"
    assert api.post(base + '/claims', headers=headers(), json={'reason': 'Damage found'}).status_code == 200
    assert api.post(base + '/claims', headers=headers(), json={'reason': 'Second claim'}).status_code == 409
    assert api.post(base + '/consent', headers=headers()).status_code == 409
    assert db.execute('SELECT count(*) FROM "Reclamo"').fetchone()[0] == 1


@pytest.mark.parametrize('action', ['claims', 'consent'])
def test_customer_actions_before_completion_and_idor(api, headers, paid_service, action, db):
    """README.md#claims-consent-and-payout-release: only owning customer may act on a completed service."""
    path = f"/api/customer/services/{paid_service['service']}/{action}"
    kwargs = {'json': {'reason': 'Damage'}} if action == 'claims' else {}
    assert api.post(path, headers=headers('other'), **kwargs).status_code == 404
    assert api.post(path, headers=headers(), **kwargs).status_code == 409
    assert db.execute('SELECT count(*) FROM "Reclamo"').fetchone()[0] == 0


def test_claim_window_closed(api, headers, completed_service, db):
    """README.md#claims-consent-and-payout-release: claim refused after configured 24-hour window."""
    service_id = completed_service['service']
    db.execute('UPDATE "Servicio" SET "Fecha_Finalizacion"=now()-interval \'25 hours\', "Fecha_Notificacion_Finalizacion"=now()-interval \'25 hours\', "Fecha_Limite_Liberacion"=now()-interval \'1 hour\' WHERE "ID"=%s', (service_id,))
    assert api.post(f'/api/customer/services/{service_id}/claims', headers=headers(), json={'reason': 'Late claim'}).status_code == 409
    assert db.execute('SELECT count(*) FROM "Reclamo"').fetchone()[0] == 0


@pytest.mark.parametrize('condition,expected_count', [('consented', 1), ('deadline', 1), ('open_claim', 0), ('no_consent', 0), ('missing_account', 0), ('missing_payment', 0)])
def test_payout_eligibility_and_idempotence(api, headers, completed_service, seed, db, server, condition, expected_count):
    """README.md#claims-consent-and-payout-release: due/consented, no open claim, approved payment, enabled account; 10% commission."""
    service_id = completed_service['service']
    base = f'/api/customer/services/{service_id}'
    if condition in ('consented', 'missing_account', 'missing_payment'):
        assert api.post(base + '/consent', headers=headers()).status_code == 200
    elif condition == 'deadline':
        db.execute('UPDATE "Servicio" SET "Fecha_Limite_Liberacion"=now()-interval \'1 hour\', "Fecha_Finalizacion"=now()-interval \'25 hours\' WHERE "ID"=%s', (service_id,))
    elif condition == 'open_claim':
        assert api.post(base + '/claims', headers=headers(), json={'reason': 'Damaged load'}).status_code == 200
    if condition != 'missing_account':
        db.execute('INSERT INTO "Cuenta_Desembolso" ("ID_Perfil", "Proveedor", "ID_Cuenta_Proveedor", "Estado_Registro", "Habilitada_Desembolsos") VALUES (%s,\'simulated\',\'blackbox-account\',\'enabled\',true)', (seed['owner']['profile'],))
    if condition == 'missing_payment':
        db.execute('UPDATE "Pago" SET "Estado"=\'rejected\' WHERE "ID"=%s', (completed_service['payment'],))
    for _ in range(2):
        run = subprocess.run([sys.executable, '-m', 'amira_api.release_payouts'], cwd='/tmp', env=server[3] | {'PAYOUT_COMMISSION_PERCENT': '10'}, capture_output=True, text=True, timeout=20)
        assert run.returncode == 0, run.stdout + run.stderr
        rows = db.execute('SELECT "Monto_Neto" FROM "Desembolso" WHERE "ID_Servicio"=%s', (service_id,)).fetchall()
        assert len(rows) == expected_count, run.stdout + run.stderr
        if rows:
            assert rows[0][0] == Decimal('9001')  # 10001 - ROUND_HALF_UP(1000.1).
