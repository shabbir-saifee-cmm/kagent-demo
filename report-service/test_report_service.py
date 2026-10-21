import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from report_service import ReportCache, extract_report, make_handler

REPORT = {
    "verdict": "DEGRADED",
    "confidence": 91,
    "summary": "Green returns 5xx.",
    "rootCause": "PODINFO_RANDOM_ERROR enabled",
    "evidence": ["5xx 12% vs 0%"],
    "action": "kubectl argo rollouts undo demo-app -n demo",
}


class ExtractReportTest(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(extract_report(json.dumps(REPORT)), REPORT)

    def test_json_wrapped_in_prose_and_fences(self):
        text = "Here is the report:\n```json\n" + json.dumps(REPORT) + "\n```\nDone."
        self.assertEqual(extract_report(text), REPORT)

    def test_missing_fields_are_filled_so_every_metric_has_a_value(self):
        report = extract_report('{"verdict": "healthy"}')
        self.assertEqual(report["verdict"], "HEALTHY")
        self.assertEqual(report["confidence"], 0)
        self.assertEqual(report["rootCause"], "none")
        self.assertEqual(report["action"], "none")
        self.assertEqual(report["evidence"], [])
        self.assertTrue(report["summary"])

    def test_unknown_verdict_becomes_inconclusive(self):
        self.assertEqual(extract_report('{"verdict": "MAYBE"}')["verdict"], "INCONCLUSIVE")

    def test_unparseable_reply_is_inconclusive_with_reason(self):
        report = extract_report("the model rambled")
        self.assertEqual(report["verdict"], "INCONCLUSIVE")
        self.assertIn("the model rambled", report["summary"])


class ReportCacheTest(unittest.TestCase):
    def test_concurrent_requests_share_one_run(self):
        calls = []

        def compute():
            calls.append(1)
            time.sleep(0.2)
            return REPORT

        cache = ReportCache()
        results = []
        threads = [threading.Thread(target=lambda: results.append(cache.get("k", compute))) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(calls), 1)
        self.assertEqual(results, [REPORT] * 5)

    def test_completed_report_is_reused(self):
        calls = []
        cache = ReportCache()
        cache.get("k", lambda: calls.append(1) or REPORT)
        cache.get("k", lambda: calls.append(1) or REPORT)
        self.assertEqual(len(calls), 1)

    def test_failed_run_is_not_cached(self):
        calls = []

        def boom():
            calls.append(1)
            raise RuntimeError("agent down")

        cache = ReportCache()
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                cache.get("k", boom)
        self.assertEqual(len(calls), 2)


class HandlerTest(unittest.TestCase):
    def setUp(self):
        self.requests = []

        def run_analysis(params):
            self.requests.append(params)
            return REPORT

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(ReportCache(), run_analysis))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return r.status, json.load(r)

    def test_report_returns_agent_json(self):
        status, body = self.get("/report?namespace=demo&rollout=demo-app&blue=aaa&green=bbb&window=10m")
        self.assertEqual(status, 200)
        self.assertEqual(body["verdict"], "DEGRADED")
        self.assertEqual(body["assessment"], "DEGRADED · 91% confidence: Green returns 5xx. Next step: kubectl argo rollouts undo demo-app -n demo")
        self.assertEqual(self.requests, [{"namespace": "demo", "rollout": "demo-app", "blue": "aaa", "green": "bbb", "window": "10m"}])

    def test_window_defaults_to_10m(self):
        self.get("/report?namespace=demo&rollout=demo-app&blue=aaa&green=bbb")
        self.assertEqual(self.requests[0]["window"], "10m")

    def test_missing_param_is_400(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.get("/report?namespace=demo&rollout=demo-app&blue=aaa")
        self.assertEqual(e.exception.code, 400)

    def test_agent_failure_is_502(self):
        def broken(params):
            raise RuntimeError("agent down")

        self.server.RequestHandlerClass = make_handler(ReportCache(), broken)
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.get("/report?namespace=demo&rollout=demo-app&blue=aaa&green=bbb")
        self.assertEqual(e.exception.code, 502)

    def test_healthz(self):
        with urllib.request.urlopen(self.base + "/healthz", timeout=5) as r:
            self.assertEqual(r.status, 200)


if __name__ == "__main__":
    unittest.main()
