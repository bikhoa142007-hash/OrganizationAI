from src.backend.api.auth_rate_limit import AuthAttemptLimiter


def test_login_identifier_limit_is_shared_across_client_ips():
    limiter = AuthAttemptLimiter(login_per_ip=10, login_per_identifier=2)

    assert limiter.record_login("192.0.2.1", "maker@example.com") is None
    assert limiter.record_login("198.51.100.2", "MAKER@example.com") is None
    assert limiter.record_login("203.0.113.3", "maker@example.com") is not None


def test_registration_has_a_service_wide_cap_in_addition_to_the_ip_cap():
    limiter = AuthAttemptLimiter(register_per_ip=5, register_per_service=2)

    assert limiter.record_registration("192.0.2.1") is None
    assert limiter.record_registration("198.51.100.2") is None
    assert limiter.record_registration("203.0.113.3") is not None
