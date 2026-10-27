import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

GOOD = dict(SEX=1, AGE=52, RACE="Black", BMI=31.0, WAIST=106, SYSBP=134, DIABP=84, GLUCOSE=104, HDL=38, TG=168, BPMEDS=0, DIABETES=0)


@pytest.fixture(scope="session")
def client():
    from app.main import app  # no DATABASE_URL in tests: prediction works, auth endpoints answer 503
    with TestClient(app, base_url="https://testserver") as c:
        yield c


@pytest.fixture
def good():
    return dict(GOOD)
