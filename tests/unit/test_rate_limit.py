from app.core.rate_limit import InMemoryRateLimiter


def test_allows_up_to_limit_then_blocks_with_retry_after() -> None:
    limiter = InMemoryRateLimiter(max_attempts=2, window_seconds=60)
    assert limiter.hit("k", now=0.0) is None
    assert limiter.hit("k", now=1.0) is None
    assert limiter.hit("k", now=2.0) == 58


def test_window_slides() -> None:
    limiter = InMemoryRateLimiter(max_attempts=1, window_seconds=10)
    assert limiter.hit("k", now=0.0) is None
    assert limiter.hit("k", now=5.0) is not None
    assert limiter.hit("k", now=10.5) is None


def test_keys_are_independent_and_reset_clears() -> None:
    limiter = InMemoryRateLimiter(max_attempts=1, window_seconds=10)
    assert limiter.hit("a", now=0.0) is None
    assert limiter.hit("b", now=0.0) is None
    assert limiter.hit("a", now=1.0) is not None
    limiter.reset()
    assert limiter.hit("a", now=1.0) is None
