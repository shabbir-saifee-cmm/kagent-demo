import json
import os
import textwrap
import threading
import urllib.error
import urllib.request
import uuid
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

VERDICTS = {"HEALTHY", "AT RISK", "DEGRADED", "INCONCLUSIVE"}
REQUIRED_PARAMS = ("namespace", "rollout", "blue", "green")
USER = "admin@kagent.dev"


def inconclusive(summary, action):
    return {"verdict": "INCONCLUSIVE", "confidence": 0, "summary": summary,
            "rootCause": "none", "evidence": [], "action": action}


def extract_report(text):
    try:
        raw = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except ValueError:
        return inconclusive(f"promotion-manager did not return a report: {text.strip()[:300]}", "none")
    verdict = str(raw.get("verdict", "")).upper().replace("_", " ")
    return {
        "verdict": verdict if verdict in VERDICTS else "INCONCLUSIVE",
        "confidence": int(raw.get("confidence") or 0),
        "summary": raw.get("summary") or "no summary",
        "rootCause": raw.get("rootCause") or "none",
        "evidence": list(raw.get("evidence") or []),
        "action": raw.get("action") or "none",
    }


def assessment(report):
    line = f"{report['verdict']} · {report['confidence']}% confidence: {report['summary']}"
    if report["verdict"] != "HEALTHY":
        line += f" Next step: {report['action']}"
    return line


class ReportCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._futures = {}

    def get(self, key, compute):
        with self._lock:
            future = self._futures.get(key)
            owner = future is None
            if owner:
                future = self._futures[key] = Future()
        if owner:
            try:
                future.set_result(compute())
            except Exception as e:
                with self._lock:
                    del self._futures[key]
                future.set_exception(e)
        return future.result()


def make_handler(cache, run_analysis):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/healthz":
                return self._reply(200, {"status": "ok"})
            if url.path != "/report":
                return self._reply(404, {"error": "not found"})
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            missing = [p for p in REQUIRED_PARAMS if not query.get(p)]
            if missing:
                return self._reply(400, {"error": f"missing params: {', '.join(missing)}"})
            params = {p: query[p] for p in REQUIRED_PARAMS}
            params["window"] = query.get("window") or "10m"
            key = (params["namespace"], params["rollout"], params["blue"], params["green"])
            try:
                report = cache.get(key, lambda: run_analysis(params))
            except Exception as e:
                return self._reply(502, {"error": str(e)})
            self._reply(200, {**report, "assessment": assessment(report)})

        def _reply(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):
            if not self.path.startswith("/healthz"):
                super().log_message(fmt, *args)

    return Handler


def tool_parts(api, session):
    with urllib.request.urlopen(f"{api}/sessions/{session}/tasks?user_id={USER}", timeout=60) as r:
        tasks = json.load(r)["data"] or []
    calls, results = [], {}
    for t in tasks:
        for m in t.get("history", []):
            for p in m.get("parts", []):
                d = p.get("data") if p.get("kind") == "data" else None
                if not isinstance(d, dict) or "name" not in d:
                    continue
                if "args" in d:
                    calls.append(d)
                elif "response" in d:
                    results[d.get("id")] = d["response"]
    return calls, results


def show(text, indent):
    print(textwrap.indent(str(text).strip(), " " * indent))


def print_trace(api, session):
    print("=" * 70)
    print(f"AGENT TRACE  (promotion-manager session {session})")
    print("=" * 70)
    calls, results = tool_parts(api, session)
    for i, c in enumerate(calls, 1):
        agent = c["name"].replace("kagent__NS__", "").replace("_", "-")
        res = results.get(c.get("id"), {})
        print(f"\n[{i}] promotion-manager -> {agent}")
        print("  request:")
        show(c["args"].get("request", c["args"]), 4)
        sub = res.get("subagent_session_id")
        if sub:
            sub_calls, sub_results = tool_parts(api, sub)
            print(f"  tools called ({len(sub_calls)}):")
            for sc in sub_calls:
                out = sub_results.get(sc.get("id"), {})
                print(f"    - {sc['name']} {json.dumps(sc['args'])}  -> {len(json.dumps(out))} chars")
            if not sub_calls:
                print("    (none, reasoned over its input)")
        print(f"  reply from {agent}:")
        show(res.get("result", "(no reply)"), 4)
    print("\n" + "=" * 70)


def run_analysis(agent_url, params, timeout, attempts):
    api = agent_url.split("/api/")[0] + "/api"
    ns, rollout, blue, green = params["namespace"], params["rollout"], params["blue"], params["green"]
    print(f"Promotion of {ns}/{rollout}: blue={blue} -> green={green}, window={params['window']}", flush=True)
    text = (f"Post-promotion report: {ns}/{rollout}. namespace={ns} rollout={rollout} "
            f"blueHash={blue} greenHash={green} window={params['window']}")
    body = {"jsonrpc": "2.0", "id": "1", "method": "message/send",
            "params": {"message": {"role": "user", "messageId": str(uuid.uuid4()),
                                   "parts": [{"kind": "text", "text": text}]}}}
    for attempt in range(1, attempts + 1):
        body["params"]["message"]["messageId"] = str(uuid.uuid4())
        req = urllib.request.Request(agent_url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.load(resp)
            break
        except (TimeoutError, urllib.error.URLError) as e:
            if not isinstance(getattr(e, "reason", e), TimeoutError):
                raise
            print(f"attempt {attempt}/{attempts}: promotion-manager did not answer within {timeout}s", flush=True)
    else:
        return inconclusive(f"The agents did not finish after {attempts} attempts of {timeout}s.",
                            "See the agent trace: kubectl -n kagent logs deploy/report-service")
    if "error" in result:
        raise RuntimeError(f"promotion-manager error: {result['error']}")
    task = result["result"]
    try:
        print_trace(api, task["contextId"])
    except Exception as e:
        print(f"Agent trace unavailable: {e}")
    reply = "\n".join(p.get("text", "") for a in task.get("artifacts", []) for p in a.get("parts", [])
                      if p.get("kind") == "text")
    report = extract_report(reply)
    print("FINAL REPORT\n" + json.dumps(report, indent=2), flush=True)
    return report


def main():
    agent_url = os.environ["AGENT_URL"]
    port = int(os.environ.get("PORT", "8080"))
    timeout = int(os.environ.get("AGENT_TIMEOUT_SECONDS", "120"))
    attempts = int(os.environ.get("AGENT_ATTEMPTS", "2"))
    handler = make_handler(ReportCache(), lambda params: run_analysis(agent_url, params, timeout, attempts))
    print(f"report-service listening on :{port}, agent {agent_url}", flush=True)
    ThreadingHTTPServer(("", port), handler).serve_forever()


if __name__ == "__main__":
    main()
