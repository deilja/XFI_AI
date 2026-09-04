from fastapi.routing import APIRoute

from app.api import app


def _paths(routes=None):
    routes = app.routes if routes is None else routes
    paths = set()
    for route in routes:
        if isinstance(route, APIRoute):
            paths.add(route.path)
        nested = getattr(route, "routes", None)
        if nested:
            paths.update(_paths(nested))
    return paths


def test_independent_admin_routes_are_mounted_once():
    paths = _paths()
    assert "/admin/phobos/health" in paths
    assert "/admin/phobos/clients" in paths
    assert "/admin/projects" in paths
    assert "/admin/projects/connect" in paths
    assert "/admin/projects/webapp" in paths
    assert not any(path.startswith("/admin/phobos/admin/projects") for path in paths)


def test_health_is_public_and_reports_vpn_providers():
    health = next(route for route in app.routes if isinstance(route, APIRoute) and route.path == "/health")
    assert health.methods == {"GET"}
