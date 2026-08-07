"""Repeatable load test comparing 5 operation types against a running
weather-app instance:

  1. uncached current-weather API   (unique coordinates every request)
  2. cached current-weather API     (same location_id, warmed first)
  3. UI page-shell load             (GET /ui/ - see note below on why this
                                      isn't a full interactive round trip)
  4. agent request                  (POST /v1/agent/query - needs a working
                                      LiteLLM Proxy; reports as failures if not)
  5. daily collection               (single run, not a percentile series -
                                      reported as one wall-clock duration)

This is a real HTTP load test against a live process, not a pytest suite -
run it manually:

    uv run uvicorn app.main:app &
    uv run python tests/load/load_test.py --requests 50 --concurrency 10

Or against Docker Compose:

    docker compose up --build -d
    uv run python tests/load/load_test.py --base-url http://localhost:8000
"""
from __future__ import annotations

import argparse
import asyncio
import random
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class OperationResult:
    name: str
    latencies_s: list[float] = field(default_factory=list)
    errors: int = 0

    @property
    def total(self) -> int:
        return len(self.latencies_s) + self.errors

    def percentile(self, p: float) -> float | None:
        if not self.latencies_s:
            return None
        data = sorted(self.latencies_s)
        k = (len(data) - 1) * p
        f, c = int(k), min(int(k) + 1, len(data) - 1)
        if f == c:
            return data[f]
        return data[f] + (data[c] - data[f]) * (k - f)

    def summary(self, duration_s: float) -> dict:
        return {
            "operation": self.name,
            "requests": self.total,
            "errors": self.errors,
            "error_rate_pct": round(100 * self.errors / self.total, 2) if self.total else None,
            "throughput_rps": round(self.total / duration_s, 2) if duration_s > 0 else None,
            "p50_ms": _ms(self.percentile(0.50)),
            "p95_ms": _ms(self.percentile(0.95)),
            "p99_ms": _ms(self.percentile(0.99)),
        }


def _ms(seconds: float | None) -> float | None:
    return round(seconds * 1000, 1) if seconds is not None else None


async def _timed(coro) -> tuple[bool, float]:
    started = time.perf_counter()
    try:
        await coro
        return True, time.perf_counter() - started
    except Exception:
        return False, time.perf_counter() - started


async def run_operation(name: str, make_request, n: int, concurrency: int) -> OperationResult:
    result = OperationResult(name=name)
    semaphore = asyncio.Semaphore(concurrency)

    async def _one(i: int) -> None:
        async with semaphore:
            ok, elapsed = await _timed(make_request(i))
            if ok:
                result.latencies_s.append(elapsed)
            else:
                result.errors += 1

    await asyncio.gather(*(_one(i) for i in range(n)))
    return result


SEED_LOCATION_IDS = [
    "hyderabad", "mumbai", "delhi", "bengaluru", "chennai",
    "new-york-city", "los-angeles", "chicago", "austin", "seattle",
    "zurich", "geneva", "bern", "lugano", "vaduz",
]


async def main(base_url: str, n: int, concurrency: int) -> None:
    results: list[dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Uncached current-weather - unique coordinates every call.
        async def uncached_request(i: int):
            lat = 10 + (i % 50) * 0.7 + random.random() * 0.01
            lon = 10 + (i % 50) * 0.7 + random.random() * 0.01
            resp = await client.get(
                f"{base_url}/v1/weather/current",
                params={"latitude": lat, "longitude": lon, "timezone": "UTC"},
            )
            resp.raise_for_status()

        started = time.perf_counter()
        r1 = await run_operation("uncached_weather_api", uncached_request, n, concurrency)
        results.append(r1.summary(time.perf_counter() - started))

        # 2. Cached current-weather - warm once (best-effort; if the
        # provider is unreachable this run will simply show up as errors
        # in the cached-operation stats below, which is honest reporting).
        try:
            warm = await client.get(f"{base_url}/v1/weather/current", params={"location_id": "hyderabad"})
            warm.raise_for_status()
        except httpx.HTTPError:
            pass

        async def cached_request(i: int):
            resp = await client.get(f"{base_url}/v1/weather/current", params={"location_id": "hyderabad"})
            resp.raise_for_status()

        started = time.perf_counter()
        r2 = await run_operation("cached_weather_api", cached_request, n, concurrency)
        results.append(r2.summary(time.perf_counter() - started))

        # 3. UI page-shell load - NiceGUI's actual interactive round trip
        #    runs over a stateful Socket.IO session per browser client, which
        #    isn't practically replayable from a stateless load-test script
        #    the way Gradio's REST-ish queue/join was. This measures the
        #    honest HTTP-observable proxy instead: time to serve the page
        #    shell (`GET /ui/`) - NOT a full button-click round trip. The
        #    business-logic latency a click would trigger is already covered
        #    by the cached/uncached weather operations above, since
        #    `app/ui/callbacks.py` calls the exact same `WeatherService`.
        async def ui_page_load(i: int):
            resp = await client.get(f"{base_url}/ui/")
            resp.raise_for_status()

        started = time.perf_counter()
        r3 = await run_operation("ui_page_load", ui_page_load, min(n, 20), min(concurrency, 5))
        results.append(r3.summary(time.perf_counter() - started))

        # 4. Agent request - needs a working LiteLLM Proxy; failures here are
        #    expected/reported honestly if one isn't configured.
        async def agent_request(i: int):
            resp = await client.post(
                f"{base_url}/v1/agent/query",
                json={"message": "What's the weather in Hyderabad?"},
                timeout=30.0,
            )
            resp.raise_for_status()

        started = time.perf_counter()
        r4 = await run_operation("agent_query", agent_request, min(n, 10), min(concurrency, 3))
        results.append(r4.summary(time.perf_counter() - started))

        # 5. Daily collection - a single run, reported as one duration, not
        #    a percentile series (it's one job, not N independent requests).
        started = time.perf_counter()
        try:
            resp = await client.post(
                f"{base_url}/internal/jobs/daily-weather",
                headers={"X-Internal-Token": "change-me-internal-token"},
                timeout=120.0,
            )
            resp.raise_for_status()
            batch_ok = True
            batch_body = resp.json()
        except Exception as exc:  # noqa: BLE001
            batch_ok = False
            batch_body = {"error": str(exc)}
        batch_duration = time.perf_counter() - started
        results.append(
            {
                "operation": "daily_collection (single run)",
                "requests": 1,
                "errors": 0 if batch_ok else 1,
                "error_rate_pct": 0.0 if batch_ok else 100.0,
                "throughput_rps": None,
                "p50_ms": _ms(batch_duration),
                "p95_ms": _ms(batch_duration),
                "p99_ms": _ms(batch_duration),
                "detail": batch_body,
            }
        )

    def _fmt(v, suffix: str = "") -> str:
        return f"{v:.1f}{suffix}" if v is not None else "-"

    print(f"\n{'Operation':<28} {'Reqs':>6} {'Err%':>7} {'RPS':>8} {'p50 ms':>9} {'p95 ms':>9} {'p99 ms':>9}")
    print("-" * 82)
    for r in results:
        print(
            f"{r['operation']:<28} {r['requests']:>6} "
            f"{_fmt(r['error_rate_pct'], '%'):>7} "
            f"{_fmt(r['throughput_rps']):>8} "
            f"{_fmt(r['p50_ms']):>9} "
            f"{_fmt(r['p95_ms']):>9} "
            f"{_fmt(r['p99_ms']):>9}"
        )
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=50, help="requests per operation")
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    asyncio.run(main(args.base_url, args.requests, args.concurrency))
