"""Shared fixtures."""

import pytest

from app import Deps
from services.supabase_client import SupabaseClient
from tests.helpers import FakeTransport


@pytest.fixture
def transport():
    return FakeTransport()


@pytest.fixture
def deps(transport):
    client = SupabaseClient("https://supabase.test", "pub", "svc", transport)
    return Deps(client, ["https://app.test"], "")
