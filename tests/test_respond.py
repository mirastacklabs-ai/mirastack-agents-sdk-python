"""Tests for mirastack_sdk.respond helpers."""

import json
import unittest

from mirastack_sdk.respond import respond_map, respond_json, respond_error, respond_raw


class TestRespondMap(unittest.TestCase):
    def test_basic_types(self):
        resp = respond_map({"count": 42, "active": True, "name": "web"})
        data = json.loads(resp.output)
        self.assertEqual(data["count"], 42)
        self.assertEqual(data["active"], True)
        self.assertEqual(data["name"], "web")

    def test_empty_map(self):
        resp = respond_map({})
        self.assertEqual(json.loads(resp.output), {})

    def test_logs_default_empty(self):
        resp = respond_map({"ok": True})
        self.assertEqual(resp.logs, [])


class TestRespondJson(unittest.TestCase):
    def test_dict(self):
        resp = respond_json({"message": "ok", "score": 0.95})
        data = json.loads(resp.output)
        self.assertEqual(data["message"], "ok")
        self.assertAlmostEqual(data["score"], 0.95)

    def test_list(self):
        resp = respond_json(["a", "b", "c"])
        data = json.loads(resp.output)
        self.assertEqual(data, ["a", "b", "c"])


class TestRespondError(unittest.TestCase):
    def test_error_format(self):
        resp = respond_error("something went wrong")
        data = json.loads(resp.output)
        self.assertEqual(data["error"], "something went wrong")


class TestRespondRaw(unittest.TestCase):
    def test_passthrough(self):
        raw = b'{"already":"serialized","count":7}'
        resp = respond_raw(raw)
        self.assertEqual(resp.output, raw)


if __name__ == "__main__":
    unittest.main()
