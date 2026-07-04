from ggotaiorder.mall.credentials_repo import (
    MallCredentialRepository,
    SupabaseMallCredentialRepository,
)
from ggotaiorder.mall.order_repo import (
    MallOrderRepository,
    SupabaseMallOrderRepository,
)


def test_credential_repo_conforms_to_protocol():
    repo = SupabaseMallCredentialRepository()
    assert isinstance(repo, MallCredentialRepository)
    for name in ("list_credentials", "update_cursor"):
        assert callable(getattr(repo, name))


def test_order_repo_conforms_to_protocol():
    repo = SupabaseMallOrderRepository()
    assert isinstance(repo, MallOrderRepository)
    for name in (
        "order_exists", "insert_call_history", "insert_order_details",
        "list_confirmable", "mark_ack", "increment_ack_attempts",
    ):
        assert callable(getattr(repo, name))
