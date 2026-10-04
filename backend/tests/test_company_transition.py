from amira_api.account_routes import router


def test_direct_company_transition_endpoint_is_removed():
    assert "/company/transition" not in {route.path for route in router.routes}
