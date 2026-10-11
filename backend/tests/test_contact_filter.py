"""Heuristic contact-detail filter for chat messages. Evasion by spelling digits out is accepted as a known limit."""

import pytest

from amira_api.contact_filter import find_contact_detail


@pytest.mark.parametrize(
    ("content", "kind"),
    [
        ("escríbeme a pat@example.test", "email"),
        ("mi correo es casey.customer@mail.cl", "email"),
        ("mira www.transportes-norte.cl", "link"),
        ("cotiza en https://example.test/oferta", "link"),
        ("pagina transportes.cl", "link"),
        ("llámame al +56 9 1111 2222", "phone"),
        ("mi numero 912345678", "phone"),
        ("9.1234.5678 es el fono", "phone"),
        ("sígueme @transportes_norte", "social"),
        ("te escribo por instagram", "social"),
        ("hablemos por WhatsApp", "social"),
    ],
)
def test_contact_details_are_classified(content, kind):
    assert find_contact_detail(content) == kind


@pytest.mark.parametrize(
    "content",
    [
        "Llegamos a las 10:30 con 2 ayudantes",
        "Mudanza de 3 dormitorios, piso 4, depto 1234",
        "El día 2026-10-11 nos acomoda",
        "¿Tienen camión de 3 toneladas? Gracias",
        "Precio final: 120000 CLP",
        "Dirección de retiro: calle Los Olivos 123",
    ],
)
def test_ordinary_conversation_is_allowed(content):
    assert find_contact_detail(content) is None
