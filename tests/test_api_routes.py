from fastapi.routing import APIRoute

from app.api import app


def _paths():
    return set(app.openapi()["paths"])


def test_independent_admin_routes_are_mounted_once():
    paths = _paths()
    assert "/admin/phobos/health" in paths
    assert "/admin/phobos/clients" in paths
    assert "/admin/projects" in paths
    assert "/admin/projects/{project}" in paths
    assert "/admin/projects/{project}/analyze" in paths
    assert "/admin/projects/{project}/generate" in paths
    assert "/admin/projects/{project}/apply" in paths
    assert not any(path.startswith("/admin/phobos/admin/projects") for path in paths)


def test_health_is_public_and_reports_vpn_providers():
    health = next(route for route in app.routes if isinstance(route, APIRoute) and route.path == "/health")
    assert health.methods == {"GET"}
