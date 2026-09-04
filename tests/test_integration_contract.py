from app.integration_contract import CONTRACT_VERSION, PROTOCOL, contract


def test_integration_contract_is_versioned_and_secret_free():
    data = contract()

    assert data["protocol"] == PROTOCOL == "xfi-ai"
    assert data["version"] == CONTRACT_VERSION == "1.0"
    assert data["gateway"]["health"] == "/health"
    assert data["gateway"]["models"] == "/v1/models"
    assert data["gateway"]["chat_completions"] == "/v1/chat/completions"
    assert data["integration"]["secrets"] == "never returned"
    assert "token" not in str(data).lower()


def test_contract_contains_shared_client_capabilities():
    capabilities = contract()["capabilities"]
    assert capabilities["ai"]
    assert capabilities["support"]
    assert capabilities["diagnostics"]
    assert capabilities["3x-ui"]
    assert capabilities["phobos"]
