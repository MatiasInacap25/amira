"""Public catalog partitions, documented bounds, and response privacy."""

from uuid import UUID
from datetime import datetime, timedelta, timezone
import pytest


@pytest.mark.parametrize('path', ['/api/services', '/api/shared-routes'])
@pytest.mark.parametrize('field,value,status', [
    ('limit', 0, 422), ('limit', 1, 200), ('limit', 50, 200), ('limit', 51, 422),
    ('offset', 0, 200), ('offset', 5000, 200), ('offset', 5001, 422),
])
def test_page_boundaries(api, seed, path, field, value, status):
    """README.md#public-browse-api; OpenAPI query bounds: pages 1..50, offsets 0..5000."""
    response = api.get(path, params={field: value})
    assert response.status_code == status, response.text
    if status == 200:
        page = response.json()
        assert {'items', 'total', 'limit', 'offset'} == page.keys()
        assert page[field] == value
        assert len(page['items']) <= page['limit']


@pytest.mark.parametrize('field,value,status', [
    ('q', 'x' * 120, 200), ('q', 'x' * 121, 422),
    ('regionCode', '13', 200), ('regionCode', '1', 422), ('regionCode', '131', 422), ('regionCode', 'ab', 422),
    ('communeCode', '13101', 200), ('communeCode', '1310', 422), ('communeCode', '131011', 422),
])
def test_service_filter_boundaries(api, seed, field, value, status):
    """README.md#public-browse-api; OpenAPI /api/services: q<=120, CUT digit lengths."""
    response = api.get('/api/services', params={field: value})
    assert response.status_code == status, response.text


@pytest.mark.parametrize('field', ['originCommuneCode', 'destinationCommuneCode'])
@pytest.mark.parametrize('value,status', [('13101', 200), ('1310', 422), ('131011', 422), ('abcde', 422)])
def test_route_commune_boundaries(api, seed, field, value, status):
    """README.md#public-browse-api; OpenAPI /api/shared-routes: five-digit CUT codes."""
    assert api.get('/api/shared-routes', params={field: value}).status_code == status


@pytest.mark.parametrize('field', ['departureFrom', 'departureTo'])
@pytest.mark.parametrize('value,status', [((datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), 200), ((datetime.now(timezone.utc) + timedelta(days=1)).replace(tzinfo=None).isoformat(), 422), ('not-a-date', 422)])
def test_route_datetime_partitions(api, seed, field, value, status):
    """README.md#public-browse-api: departure filters require timezone-aware ISO-8601."""
    assert api.get('/api/shared-routes', params={field: value}).status_code == status


def test_catalog_visibility_and_privacy(api, seed):
    """README.md#public-browse-api and #hidden-service-types: public DTOs omit private fields."""
    page = api.get('/api/services').json()
    assert seed['owner']['profile'] in {item['profileId'] for item in page['items']}
    for item in page['items']:
        assert item['logoUrl'] is None
        assert not {'email', 'phone', 'rut', 'taxId', 'userId', 'storageKey', 'drivers', 'vehicles'} & item.keys()
    assert 'blackbox.invalid' not in str(page)
    assert '76123456-0' not in str(page)
    hidden = api.get('/api/services', params={'serviceType': 'carga-compartida'})
    assert hidden.status_code == 200
    assert hidden.json()['items'] == []
    types = api.get('/api/service-types')
    assert types.status_code == 200
    assert 'carga-compartida' not in str(types.json())


@pytest.mark.parametrize('identifier,status', [('malformed', 422), (str(UUID(int=1)), 404)])
def test_provider_identifier_partitions(api, seed, identifier, status):
    """OpenAPI /api/providers/{profile_id}: UUID; odd/tasks/panel-proveedores.md S3: unpublished absent."""
    assert api.get(f'/api/providers/{identifier}').status_code == status


def test_locations_catalog(api):
    """README.md#public-browse-api; OpenAPI LocationCatalog: official CUT region/commune codes."""
    response = api.get('/api/locations')
    assert response.status_code == 200
    regions = response.json()['regions']
    assert any(c['code'] == '13101' for r in regions for c in r['communes'])
    assert all(len(r['code']) == 2 and r['code'].isdigit() for r in regions)
    assert all(len(c['code']) == 5 and c['code'].isdigit() for r in regions for c in r['communes'])
