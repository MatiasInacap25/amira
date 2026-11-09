"""Real HTTP harness; oracle: odd/tasks/caja-negra.md S1-S2.

No application modules are imported. SQL is arrangement and persistence evidence only.
"""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
import psycopg
import pytest
from sqlalchemy.engine import make_url

from postgres_support import destructive_test_skip_reason

ENV = "AMIRA_BLACKBOX_DATABASE_URL"


def pytest_collection_modifyitems(items):
    url = os.environ.get(ENV, "").strip()
    reason = destructive_test_skip_reason(url) if url else f"{ENV} is not set"
    if not reason:
        parsed = make_url(url)
        if parsed.host != "127.0.0.1" or parsed.port != 55432 or parsed.database != "postgres" or parsed.query:
            reason = "only the dedicated 127.0.0.1:55432/postgres database without query overrides is authorized"
    if reason:
        for item in items:
            if Path(__file__).parent in Path(str(item.path)).parents:
                item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture(scope="session")
def database_url():
    url = os.environ[ENV].strip()
    assert destructive_test_skip_reason(url) is None
    parsed = make_url(url)
    assert (parsed.host, parsed.port, parsed.database, dict(parsed.query)) == ("127.0.0.1", 55432, "postgres", {})
    return url


@pytest.fixture(scope="session")
def db(database_url):
    with psycopg.connect(database_url, autocommit=True, sslmode="require") as connection:
        yield connection


@pytest.fixture(scope="session")
def server(database_url):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="blackbox-local", alg="RS256", use="sig")

    class JWKSHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = json.dumps({"keys": [jwk]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    jwks = ThreadingHTTPServer(("127.0.0.1", 0), JWKSHandler)
    thread = threading.Thread(target=jwks.serve_forever, daemon=True)
    thread.start()
    issuer = f"http://127.0.0.1:{jwks.server_port}/auth/v1"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    # Do not inherit .env or ambient remote credentials/settings into the subprocess.
    env = {"PATH": os.environ["PATH"], "HOME": tempfile.gettempdir(),
           "APP_ENV": "test", "DATABASE_URL": database_url,
           "REALTIME_DATABASE_URL": database_url,
           "SUPABASE_JWT_ISSUER": issuer, "SUPABASE_JWT_AUDIENCE": "authenticated",
           "SUPABASE_JWKS_URL": issuer + "/.well-known/jwks.json",
           "SUPABASE_URL": f"http://127.0.0.1:{jwks.server_port}",
           "SUPABASE_SERVICE_ROLE_KEY": "", "DEV_SKIP_SMS_MFA": "false",
           "PAYMENT_SIMULATOR_SECRET": "blackbox-local-simulator-only",
           "PAYMENT_WEBHOOK_SECRET": "blackbox-local-webhook-only",
           "FRONTEND_BASE_URL": "http://127.0.0.1:3179",
           "REQUEST_IMAGES_BUCKET": "", "VEHICLE_IMAGES_BUCKET": "",
           "RESEND_API_KEY": "", "PYTHONUNBUFFERED": "1"}
    # An empty temporary cwd prevents pydantic dotenv loading the repository's .env.
    with tempfile.TemporaryDirectory(prefix="amira-bb-") as cwd, tempfile.TemporaryFile(mode="w+") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "amira_api.main:app", "--host", "127.0.0.1", "--port", str(port)], cwd=cwd, env=env, stdout=log, stderr=log)
        client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10, trust_env=False)
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.05)  # Bounded subprocess readiness polling only.
            else:
                pytest.fail("uvicorn readiness timed out")
            if process.poll() is not None:
                log.seek(0)
                pytest.fail("uvicorn failed: " + log.read())
            yield client, key, issuer, env
        finally:
            client.close()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            jwks.shutdown()
            jwks.server_close()
            thread.join(timeout=5)


@pytest.fixture
def api(server):
    return server[0]


@pytest.fixture
def seed(db):
    """Recreate actors only in the explicitly authorized disposable database."""
    db.execute('TRUNCATE "Usuario" CASCADE')
    actors = {}
    for name, role in [("customer", "client"), ("other", "client"), ("owner", "company_owner"), ("driver", "company_driver"), ("outsider", "company_owner")]:
        user_id, auth_id = uuid4(), uuid4()
        db.execute('INSERT INTO "Usuario" ("ID", "ID_Auth_Supabase", "Nombre", "Apellido", "Correo", "ID_Rol") SELECT %s,%s,%s,%s,%s,"ID" FROM "Rol_Usuario" WHERE code=%s', (user_id, auth_id, name, "PrivateSurname", f"{name}@blackbox.invalid", role))
        actors[name] = {"id": str(user_id), "sub": str(auth_id), "email": f"{name}@blackbox.invalid"}
    for name in ("owner", "outsider"):
        profile = uuid4()
        db.execute('INSERT INTO "Perfil" ("ID", "ID_user", "Nombre", "Descripcion", "Rol_Perfil", kind, "Rut_Empresa", public_activated_at, "Codigo_Comuna") SELECT %s,%s,%s,%s,"ID",\'company\',%s,now(),\'13101\' FROM "Rol_Perfil" WHERE code=\'company\'', (profile, actors[name]["id"], f"Blackbox {name}", "Transport services", "76123456-0" if name == "owner" else "76123457-9"))
        actors[name]["profile"] = str(profile)
    service_type = db.execute('SELECT "ID" FROM "Tipos_Servicio" WHERE "Slug"=\'mudanzas\'').fetchone()[0]
    actors["service_type"] = str(service_type)
    for name in ("owner", "outsider"):
        db.execute('INSERT INTO "Servicios_Disponibles" ("ID_Perfil", "ID_Tipo_Servicio") VALUES (%s,%s)', (actors[name]["profile"], service_type))
    driver_type = db.execute('INSERT INTO "Tipo_Conductor" ("Rol") VALUES (\'blackbox\') ON CONFLICT ("Rol") DO UPDATE SET "Rol"=EXCLUDED."Rol" RETURNING "ID"').fetchone()[0]
    driver = uuid4()
    db.execute('INSERT INTO "Conductor" ("ID", "ID_user", "ID_perfil", "Tipo_Conductor") VALUES (%s,%s,%s,%s)', (driver, actors["driver"]["id"], actors["owner"]["profile"], driver_type))
    actors["driver"]["driver"] = str(driver)
    vehicle = uuid4()
    db.execute('INSERT INTO "Vehiculo" ("ID", "ID_Perfil", "Patente", "Marca", "Modelo", "Imagen_Storage_Key") VALUES (%s,%s,\'BB1234\',\'Test\',\'Truck\',\'blackbox/private.jpg\')', (vehicle, actors["owner"]["profile"]))
    actors["vehicle"] = str(vehicle)
    return actors


@pytest.fixture
def token(server, seed):
    def mint(actor="customer", **overrides):
        now = int(time.time())
        identity = seed["customer" if actor == "anonymous" else actor]
        claims = {"iss": server[2], "aud": "authenticated", "exp": now + 600, "iat": now,
                  "sub": identity["sub"], "email": identity["email"], "aal": "aal2",
                  "amr": [{"method": "password", "timestamp": now}, {"method": "totp", "timestamp": now}],
                  "session_id": str(uuid4()), "role": "authenticated", "is_anonymous": actor == "anonymous"}
        claims.update(overrides)
        return jwt.encode(claims, server[1], algorithm="RS256", headers={"kid": "blackbox-local"})
    return mint


@pytest.fixture
def headers(token):
    return lambda actor="customer", **claims: {"Authorization": "Bearer " + token(actor, **claims)}


@pytest.fixture
def request_body(seed):
    from datetime import datetime, timedelta, timezone
    return {"profileId": seed['owner']['profile'], "serviceTypeId": seed['service_type'],
            "originCommuneCode": "13101", "destinationCommuneCode": "05101",
            "origin": "Pickup street 123", "destination": "Delivery street 456",
            "requestedAt": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "description": "Furniture transport", "acceptsSharing": True}


@pytest.fixture
def create_request(api, headers, request_body):
    def create(**changes):
        response = api.post('/api/service-requests', headers=headers(), json=request_body | changes)
        assert response.status_code == 201, response.text
        return response.json()['requestId']
    return create


@pytest.fixture
def accepted_chat(api, headers, create_request):
    request_id = create_request()
    response = api.post(f'/api/provider/requests/{request_id}/accept', headers=headers('owner'))
    assert response.status_code == 200, response.text
    return {'request': request_id, 'chat': response.json()['chatId']}


@pytest.fixture
def quote_body(request_body):
    return {'amount': 10001, 'serviceAt': request_body['requestedAt'], 'description': 'Transport quotation', 'validityHours': 48}


@pytest.fixture
def quotation(api, headers, accepted_chat, quote_body):
    response = api.post(f"/api/chats/{accepted_chat['chat']}/quotations", headers=headers('owner'), json=quote_body)
    assert response.status_code == 201, response.text
    return accepted_chat | {'quotation': response.json()['quotationId']}


@pytest.fixture
def checkout(api, headers, quotation):
    from urllib.parse import parse_qs, urlparse
    response = api.post(f"/api/quotations/{quotation['quotation']}/payments", headers=headers())
    assert response.status_code == 201, response.text
    body = response.json()
    assert urlparse(body['checkoutUrl']).netloc == '127.0.0.1:3179'
    return quotation | {'payment': body['paymentId'], 'checkout_token': parse_qs(urlparse(body['checkoutUrl']).query)['token'][0]}


@pytest.fixture
def paid_service(api, headers, checkout):
    response = api.post(f"/api/payments/simulated/{checkout['payment']}/complete", headers=headers(),
                        json={'token': checkout['checkout_token'], 'approve': True})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'approved'
    return checkout | {'service': response.json()['serviceId']}
