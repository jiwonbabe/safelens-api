"""Age band from a date of birth. k-ID's server API when KID_API_KEY is set, a local date check otherwise. Never raises past resolve_age."""
import datetime
import os

import requests
from dotenv import load_dotenv

load_dotenv()

KID_BANDS = {"digital-minor": "kid", "digital_minor": "kid", "digital-youth": "teen", "digital_youth": "teen", "adult": "adult", "legal_adult": "adult"}
MEMO = {}  # ponytail: in-memory memo, lost on restart


def band_from_dob(dob, today=None):
    born = datetime.date.fromisoformat(dob)
    today = today or datetime.date.today()
    if born > today:
        raise ValueError("dob is in the future")
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    if age < 13:
        return "kid"
    if age < 18:
        return "teen"
    return "adult"


def band_from_kid(dob, jurisdiction):
    key = os.environ.get("KID_API_KEY", "")
    if not key:
        return None
    base = os.environ.get("KID_BASE_URL") or "https://game-api.test.k-id.com/api/v1"
    try:
        r = requests.post(base + "/age-gate/check-age-category", json={"jurisdiction": jurisdiction, "dateOfBirth": dob},
                          headers={"Authorization": "Bearer " + key}, timeout=3)
        r.raise_for_status()
        d = r.json()
        return KID_BANDS.get(str(d.get("ageCategory") or d.get("ageStatus") or "").lower())
    except Exception:
        return None


def resolve_age(dob, jurisdiction):
    """(band, source). source is "k-id" when k-ID answered, else "fallback". Raises ValueError on a bad or future date."""
    local = band_from_dob(dob)  # validate first so a bad date never hits the network or the memo
    if (dob, jurisdiction) not in MEMO:
        band = band_from_kid(dob, jurisdiction)
        MEMO[(dob, jurisdiction)] = (band, "k-id") if band else (local, "fallback")
    return MEMO[(dob, jurisdiction)]
