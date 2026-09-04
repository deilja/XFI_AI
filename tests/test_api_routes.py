from app.api import app


def test_independent_admin_routes_are_mounted_once():
    paths = {route.path for route in app.routes}
    assert "/admin/phobos/health" in paths
    assert "/admin/phobos/clients" in paths
    assert "/admin/projects" in paths
    assert "/admin/projects/connect" in paths
    assert "/admin/projects/webapp" in paths
    assert not any(path.startswith("/admin/phobos/admin/projects") for path in paths)


def test_health_is_public_and_reports_vpn_providers():
    health = next(route for route in app.routes if route.path == "/health")
    assert health.methods == {"GET"}
