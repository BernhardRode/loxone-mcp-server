Kiro Steering Document – TDD Practices for Python Networking (Async/UVloop)
Philosophy

Test-Driven Development (TDD) is not an afterthought — it’s the foundation of building robust, scalable networking systems. Every feature, especially in asynchronous WebSocket and UDP services, is designed hand-in-hand with tests. The process ensures correctness, performance, and security at scale, while maintaining velocity.

Principles:

Red → Green → Refactor: Write a failing test, make it pass, then refine the implementation.

Async First: Tests run in an async event loop, using uvloop for maximum parity with production performance.

Fast Feedback: Keep test runs <2s for core unit tests.

Isolation: Unit tests isolate logic; integration tests simulate realistic network conditions.

Observability in Tests: All tests produce logs/metrics to aid debugging.

Tooling Stack

Test Runner: pytest
 with pytest-asyncio for async/await tests.

Property-Based Testing: hypothesis
 to explore edge cases (packet size, concurrency levels, malformed input).

Type Safety: mypy
 integrated in CI, ensuring static correctness alongside tests.

Event Loop: uvloop
 replaces asyncio default loop for all tests.

Mocking: pytest-mock and built-in unittest.mock for protocol boundaries.

Benchmarking/Profiling in CI: pytest-benchmark for detecting performance regressions.

Linting/Style: ruff, black, flake8, isort pre-commit hooks.

Coverage: pytest-cov (target: >95% coverage, with mandatory branch coverage).

Containers: testcontainers-python for ephemeral integration deps (Redis, Kafka, etc., if needed).

TDD Workflow

Define Behavior Before Code

Write test cases describing networking behavior (e.g., "UDP packets dropped after timeout", "WebSocket connection upgrade handshake").

Start with contract tests against protocol requirements (RFC compliance).

Unit Test Loop

Write failing unit test in pytest with @pytest.mark.asyncio.

Implement the minimal async function/class until test passes.

Refactor for clarity and performance.

import pytest
import asyncio

@pytest.mark.asyncio
async def test_udp_message_roundtrip(udp_client, udp_server):
    msg = b"hello"
    await udp_client.send(msg)
    data = await udp_server.receive()
    assert data == msg


Use uvloop in Tests

import asyncio
import uvloop
import pytest

@pytest.fixture(autouse=True, scope="session")
def use_uvloop():
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


Property Testing for Edge Cases

from hypothesis import given, strategies as st

@given(st.binary(min_size=1, max_size=4096))
def test_udp_handles_arbitrary_payload(payload, udp_client, udp_server):
    udp_client.send(payload)
    received = udp_server.receive()
    assert received == payload


Integration & Load Testing

Spin up real WebSocket/UDP servers inside pytest fixtures.

Simulate multiple concurrent clients using asyncio tasks.

Use pytest-benchmark to enforce latency/throughput SLAs.

@pytest.mark.asyncio
async def test_ws_can_handle_1000_clients(websocket_server):
    async def connect_and_ping():
        async with websockets.connect(websocket_server.url) as ws:
            await ws.send("ping")
            resp = await ws.recv()
            assert resp == "pong"

    tasks = [connect_and_ping() for _ in range(1000)]
    await asyncio.gather(*tasks)


Security/Resilience Testing

Fuzz malformed packets and check graceful degradation.

Assert that DoS attempts (e.g., large UDP floods) do not crash the service.

Validate rate-limiting and timeouts with async test harnesses.

Continuous Integration

Pre-commit hooks enforce formatting & linting.

GitHub Actions pipeline runs:

Unit + integration tests with uvloop.

Coverage enforcement (--cov-fail-under=95).

Property-based fuzz tests on nightly builds.

Benchmarks compared to baseline (alerts if >5% perf regression).

Deliverables in TDD Practice

Unit Test Suites for all modules (WebSocket, UDP).

Integration Harness with uvloop-based async fixtures.

Property-Based Tests exploring protocol edge cases.

Benchmark Reports for networking performance under load.

Security Regression Suite against common attacks.

CI/CD Integration ensuring test-first approach is enforced.

Success Criteria

No networking feature merged without corresponding test coverage.

CI pipeline guarantees regressions are caught before production.

Tests are fast, deterministic, and reliable across environments.

Team adopts async-first TDD as default development mode.

Culture shift: “If it isn’t tested, it doesn’t exist.”