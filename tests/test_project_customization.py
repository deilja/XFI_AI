from app.project_api import router


def test_customization_route_exists_and_is_post():
    routes = {(route.path, tuple(sorted(route.methods or set()))) for route in router.routes}
    assert ("/admin/projects/{project}/customize", ("POST",)) in routes
