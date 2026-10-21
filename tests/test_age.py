import datetime

import pytest
import requests

from pipeline import age

TODAY = datetime.date(2026, 10, 21)


def test_band_boundaries_with_fixed_today():
    assert age.band_from_dob("2013-10-22", TODAY) == "kid"   # 12y 364d
    assert age.band_from_dob("2013-10-21", TODAY) == "teen"  # 13 today
    assert age.band_from_dob("2009-10-21", TODAY) == "teen"  # 17
    assert age.band_from_dob("2008-10-21", TODAY) == "adult"  # 18 today


def test_bad_or_future_date_raises():
    with pytest.raises(ValueError):
        age.band_from_dob("bad", TODAY)
    with pytest.raises(ValueError):
        age.band_from_dob("2027-01-01", TODAY)


def test_band_from_kid_is_none_without_key(monkeypatch):
    monkeypatch.delenv("KID_API_KEY", raising=False)
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("must not call k-ID without a key"))
    assert age.band_from_kid("2015-04-15", "US-CA") is None


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self.body = status, body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self.body


def test_band_from_kid_maps_a_200(monkeypatch):
    monkeypatch.setenv("KID_API_KEY", "x")
    monkeypatch.delenv("KID_BASE_URL", raising=False)
    seen = {}

    def fake_post(url, json, headers, timeout):
        seen.update(url=url, json=json, auth=headers["Authorization"], timeout=timeout)
        return FakeResponse(200, {"ageCategory": "DIGITAL_YOUTH"})

    monkeypatch.setattr(requests, "post", fake_post)
    assert age.band_from_kid("2011-01-01", "US-CA") == "teen"
    assert seen["url"] == "https://game-api.test.k-id.com/api/v1/age-gate/check-age-category"
    assert seen["json"] == {"jurisdiction": "US-CA", "dateOfBirth": "2011-01-01"} and seen["auth"] == "Bearer x" and seen["timeout"] == 3
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(200, {"ageStatus": "digital-minor"}))
    assert age.band_from_kid("2015-04-15", "US-CA") == "kid"
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(200, {"ageCategory": "LEGAL_ADULT"}))
    assert age.band_from_kid("2000-01-01", "US-CA") == "adult"
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(200, {"ageCategory": "weird"}))
    assert age.band_from_kid("2000-01-01", "US-CA") is None


def test_band_from_kid_is_none_on_403_or_timeout(monkeypatch):
    monkeypatch.setenv("KID_API_KEY", "x")
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(403, {}))
    assert age.band_from_kid("2015-04-15", "US-CA") is None

    def boom(*a, **k):
        raise requests.Timeout()

    monkeypatch.setattr(requests, "post", boom)
    assert age.band_from_kid("2015-04-15", "US-CA") is None


def test_resolve_age_memoizes(monkeypatch):
    monkeypatch.setattr(age, "MEMO", {})
    monkeypatch.setenv("KID_API_KEY", "x")
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        return FakeResponse(200, {"ageCategory": "digital-minor"})

    monkeypatch.setattr(requests, "post", fake_post)
    assert age.resolve_age("2015-04-15", "US-CA") == ("kid", "k-id")
    assert age.resolve_age("2015-04-15", "US-CA") == ("kid", "k-id")
    assert len(calls) == 1
    monkeypatch.delenv("KID_API_KEY")
    assert age.resolve_age("2005-04-15", "US-CA") == ("adult", "fallback")
    with pytest.raises(ValueError):
        age.resolve_age("bad", "US-CA")
