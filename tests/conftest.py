import asyncio
import uvloop
import pytest

@pytest.fixture(autouse=True, scope="session")
def use_uvloop():
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
