from ggotaiorder.core.heartbeat import record_heartbeat


class _FakeRpc:
    def __init__(self, sink):
        self._sink = sink

    def execute(self):
        self._sink["executed"] = True
        return self


class _FakeClient:
    def __init__(self, sink):
        self._sink = sink

    def rpc(self, fn, params):
        self._sink["fn"] = fn
        self._sink["params"] = params
        return _FakeRpc(self._sink)


def test_record_heartbeat_calls_db_side_rpc():
    # DB 서버 시각(now())으로 기록하기 위해 RPC 를 호출한다(PC-서버 시계차 제거).
    sink = {}
    record_heartbeat(19, client=_FakeClient(sink))
    assert sink["fn"] == "record_engine_heartbeat"
    assert sink["params"] == {"p_shop_key": 19}
    assert sink["executed"] is True
