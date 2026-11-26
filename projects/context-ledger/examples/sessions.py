"""Synthetic long coding sessions with planted facts. Seeded, so every run sees the same text.

Phrasings are drawn from pools; some deliberately avoid the words and `key=value` shapes the
ledger's extractor looks for, so the benchmark can show where it fails.
"""

from __future__ import annotations

import random
import re
from typing import NamedTuple

from context_ledger import Event

SERVICES = ["billing", "search", "ingest", "auth", "export", "notify"]
DAYS = ["Friday", "Monday", "Thursday", "Sunday"]


class Probe(NamedTuple):
    id: str
    category: str
    question: str
    answer: str
    stale: str = ""  # an outdated value that must not be given


def _noise(rng: random.Random, i: int) -> Event:
    svc = rng.choice(SERVICES)
    lines = []
    for n in range(rng.randint(35, 55)):
        lines.append(
            rng.choice(
                [
                    f"2026-03-{rng.randint(10, 28)} INFO {svc}.worker processed batch {rng.randint(1000, 9999)}",
                    f"tests/{svc}/test_case_{n}.py::test_{n} PASSED",
                    f"{svc}_replica.timeout_ms={rng.randint(2000, 9000)}",
                    f"WARN {svc} retrying request id={rng.randint(10**5, 10**6)}",
                    f"  compiled src/{svc}/mod_{rng.randint(1, 40)}.py in {rng.randint(3, 90)}ms",
                ]
            )
        )
    if rng.random() < 0.25:
        lines.append(
            f"ERROR E{rng.randint(7000, 7999)}: transient cache miss in src/{svc}/cache.py"
        )
    lines.append(f"exit status 0 ({svc} step {i})")
    return Event(0, "tool", "\n".join(lines), f"run {svc} checks")


def _bury(rng: random.Random, line: str, name: str) -> Event:
    host = _noise(rng, 0)
    lines = host.text.splitlines()
    lines.insert(rng.randint(5, len(lines) - 5), line)
    return Event(0, "tool", "\n".join(lines), name)


def _unforeseen(rng: random.Random, segments) -> list[Probe]:
    """Questions about ordinary noise lines, chosen after the fact: nothing marks them out."""
    seen: dict[str, list[tuple[int, str]]] = {}
    for index, segment in enumerate(segments):
        for event in segment:
            for module, ms in re.findall(r"compiled (src/\w+/mod_\d+\.py) in (\d+)ms", event.text):
                seen.setdefault(module, []).append((index, ms))
    once = sorted(m for m, hits in seen.items() if len(hits) == 1 and hits[0][0] < 2)
    return [
        Probe(f"u{k + 1}", "unforeseen", f"How many milliseconds did compiling {module} take?", seen[module][0][1])
        for k, module in enumerate(rng.sample(once, 4))
    ]  # fmt: skip


def build(seed: int, rounds: int = 3) -> tuple[list[list[Event]], list[Probe]]:
    """`rounds` segments (compaction happens after each) and the questions asked at the end.

    The first two and the last segment carry the planted facts; extra middle segments are noise,
    so early facts have to survive more compactions.
    """
    rng = random.Random(seed)
    owned, own_dir = rng.sample(SERVICES, 2)
    day = rng.choice(DAYS)
    flag = f"{rng.choice(['nova', 'atlas', 'ember', 'quartz'])}_rollout_{rng.randint(2, 9)}"
    old_t, new_t = rng.sample(range(11, 90), 2)
    old_ttl, new_ttl = rng.sample(range(100, 900), 2)
    shards, clients = rng.sample(range(12, 99), 2)
    store, alt = rng.sample(["Redis Streams", "Kafka", "NATS", "RabbitMQ", "SQS"], 2)
    flaky = f"test_{rng.choice(['replay', 'lease', 'cursor', 'quota'])}_{rng.randint(10, 99)}"
    code = rng.randint(4000, 4999)
    bad = f"src/{rng.choice(SERVICES)}/tls_{rng.randint(1, 9)}.py"

    def u(text):
        return Event(0, "user", text)

    def a(text):
        return Event(0, "assistant", text)

    rule_dir = rng.choice(
        [
            f"Please leave everything under src/{owned}/ alone, another team owns it.",
            f"Hands off the src/{owned}/ folder. It isn't ours.",
        ]
    )
    rule_day = rng.choice([f"We never ship on {day}s.", f"Do not deploy on a {day}, ever."])
    rule_flag = f"Any new endpoint has to sit behind the {flag} feature flag."
    decision = rng.choice(
        [
            f"I'm going with {store} over {alt} for the job queue because ops already runs it.",
            f"{store} it is for the job queue; {alt} would need a new cluster.",
        ]
    )
    finding = rng.choice(
        [
            f"The flaky one is {flaky}; it depends on wall-clock time.",
            f"It turns out {flaky} is what fails intermittently.",
        ]
    )
    planted = [
        [
            u(f"Let's harden the {own_dir} service this week. {rule_dir}"),
            u(f"Use a request timeout of {old_t} seconds."),
            _bury(rng, f"{own_dir}.cache_ttl_s={old_ttl}", "cat service config"),
            a(decision),
            u(rule_day),
        ],
        [
            _bury(rng, f"{own_dir}.shard_count={shards}", "describe cluster"),
            _bury(
                rng,
                f"NOTE the connection pool saturates at {clients} concurrent clients",
                "load test",
            ),
            u(rule_flag),
            _bury(rng, f"ERROR E{code}: TLS handshake failed in {bad}", "integration tests"),
            a(finding),
        ],
        [
            u(f"Change of plan on the request timeout: make it {new_t} seconds."),
            _bury(rng, f"{own_dir}.cache_ttl_s={new_ttl}", "cat service config"),
            a("Config reloaded. Moving on to the remaining checks."),
        ],
    ]
    planted[2:2] = [[] for _ in range(rounds - 3)]
    segments, next_id = [], 1
    for i, items in enumerate(planted):
        body = list(items)
        for n in range(8):  # interleave noise, keeping planted order
            body.insert(rng.randint(0, len(body)), _noise(rng, i * 10 + n))
            if n % 3 == 0:
                body.insert(
                    rng.randint(0, len(body)),
                    a(f"Checked the {rng.choice(SERVICES)} step, nothing unusual there."),
                )
        if i == 0:  # the opening request really does come first
            body.remove(items[0])
            body.insert(0, items[0])
        numbered = [e._replace(id=next_id + j) for j, e in enumerate(body)]
        next_id += len(numbered)
        segments.append(numbered)

    probes = [
        Probe("q1", "user rule", "Which directory did the user say not to modify?", f"src/{owned}"),
        Probe("q2", "user rule", "On which weekday must we never deploy?", day),
        Probe("q3", "user rule", "Which feature flag must new endpoints be behind?", flag),
        Probe("q4", "updated value", "What request timeout (seconds) should be used now?", str(new_t), str(old_t)),
        Probe("q5", "updated value", f"What is the current {own_dir}.cache_ttl_s?", str(new_ttl), str(old_ttl)),
        Probe("q6", "tool output", f"What is {own_dir}.shard_count?", str(shards)),
        Probe("q7", "tool output", "At how many concurrent clients does the connection pool saturate?", str(clients)),
        Probe("q8", "error", "What error code did the TLS handshake failure report?", f"E{code}"),
        Probe("q9", "error", "Which file did the TLS handshake fail in?", bad),
        Probe("q10", "agent finding", "Which technology was chosen for the job queue?", store, alt),
        Probe("q11", "agent finding", "Which test is the flaky one?", flaky),
    ]  # fmt: skip
    return segments, probes + _unforeseen(rng, segments)
