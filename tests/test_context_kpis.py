"""Tests for EngineContext KPI callback helpers."""

import unittest

from mirastack_sdk.context import EngineContext
from mirastack_sdk.gen import plugin_pb2


class _FakeStub:
    def __init__(self) -> None:
        self.last_list_req = None
        self.last_get_req = None

    def ListKPIs(self, req):
        self.last_list_req = req
        return plugin_pb2.ListKPIsResponse(
            kpis=[
                plugin_pb2.KPIView(
                    id="kpi-1",
                    tenant_id=req.tenant_id,
                    name="Error Rate",
                    kind=req.kind,
                    layer=req.layer,
                )
            ]
        )

    def GetKPI(self, req):
        self.last_get_req = req
        return plugin_pb2.GetKPIResponse(
            kpi=plugin_pb2.KPIView(
                id=req.kpi_id,
                tenant_id=req.tenant_id,
                name="Latency",
                kind="technical",
                layer="silver",
            )
        )


class TestEngineContextKPICallbacks(unittest.IsolatedAsyncioTestCase):
    async def test_list_kpis_auto_stamps_tenant(self):
        ctx = EngineContext("localhost:65535", "test-plugin", "tenant-123")
        stub = _FakeStub()
        ctx._stub = stub

        rows = await ctx.list_kpis(kind="business", layer="gold")

        self.assertEqual(stub.last_list_req.tenant_id, "tenant-123")
        self.assertEqual(stub.last_list_req.kind, "business")
        self.assertEqual(stub.last_list_req.layer, "gold")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "kpi-1")
        self.assertEqual(rows[0]["tenant_id"], "tenant-123")

        await ctx.close()

    async def test_get_kpi_auto_stamps_tenant(self):
        ctx = EngineContext("localhost:65535", "test-plugin", "tenant-abc")
        stub = _FakeStub()
        ctx._stub = stub

        row = await ctx.get_kpi("kpi-9")

        self.assertEqual(stub.last_get_req.tenant_id, "tenant-abc")
        self.assertEqual(stub.last_get_req.kpi_id, "kpi-9")
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], "kpi-9")
        self.assertEqual(row["tenant_id"], "tenant-abc")

        await ctx.close()

    async def test_kpi_fallback_generic_unary(self):
        ctx = EngineContext("localhost:65535", "test-plugin", "tenant-z")
        ctx._stub = None

        calls = []

        def _fake_call_unary(method, request):
            calls.append((method, request))
            if method.endswith("/ListKPIs"):
                return {"kpis": [{"id": "kpi-fallback", "tenant_id": request["tenant_id"]}]}
            return {"kpi": {"id": "kpi-one", "tenant_id": request["tenant_id"]}}

        ctx._call_unary = _fake_call_unary  # type: ignore[method-assign]

        rows = await ctx.list_kpis(kind="business")
        row = await ctx.get_kpi("kpi-one")

        self.assertEqual(rows[0]["id"], "kpi-fallback")
        self.assertEqual(rows[0]["tenant_id"], "tenant-z")
        self.assertEqual(row["id"], "kpi-one")
        self.assertEqual(row["tenant_id"], "tenant-z")
        self.assertEqual(calls[0][1]["tenant_id"], "tenant-z")
        self.assertEqual(calls[1][1]["tenant_id"], "tenant-z")

        await ctx.close()


if __name__ == "__main__":
    unittest.main()
