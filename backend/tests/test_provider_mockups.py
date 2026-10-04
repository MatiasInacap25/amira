from pathlib import Path


MOCKUPS = Path(__file__).parents[2] / "docs" / "mockups"
PROFILE_PAGES = (
    MOCKUPS / "public-provider-independent.html",
    MOCKUPS / "public-provider-company.html",
)


def test_provider_mockups_share_public_sections_and_work_without_network_assets():
    pages = [path.read_text(encoding="utf-8") for path in PROFILE_PAGES]

    for page in pages:
        assert '<html lang="es">' in page
        assert 'href="#servicios"' in page
        assert 'href="#conductores"' in page
        assert 'href="#vehiculos"' in page
        assert 'id="servicios"' in page
        assert 'id="conductores"' in page
        assert 'id="vehiculos"' in page
        assert "Solicitar cotización" in page
        assert "Valoración de muestra" in page
        assert "Mockup, no verificada" in page
        assert "https://" not in page
        assert "<script" not in page
        assert "@example" not in page
        assert "RUT" not in page

    assert "Conductor independiente" in pages[0]
    assert "Empresa" in pages[1]
    assert "único conductor" in pages[0]
    assert "[DEMO] Mateo Silva" in pages[1]
    assert "[DEMO] Lucía Rojas" in pages[1]
