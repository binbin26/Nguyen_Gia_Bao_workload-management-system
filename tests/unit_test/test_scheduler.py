import asyncio

from app import main as main_module


def test_lifespan_starts_and_stops_scheduler(monkeypatch):
    started = False
    shutdown = False
    added_jobs = []

    class DummyScheduler:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def add_job(self, *args, **kwargs):
            added_jobs.append((args, kwargs))

        def start(self):
            nonlocal started
            started = True

        def shutdown(self, wait=False):
            nonlocal shutdown
            shutdown = True

    async def _noop_async():
        return None

    monkeypatch.setattr(main_module, "connect_to_mongo", _noop_async)
    monkeypatch.setattr(main_module, "close_mongo_connection", _noop_async)
    monkeypatch.setattr(main_module, "AsyncIOScheduler", DummyScheduler)

    app = main_module.create_app()

    async def run_lifespan():
        async with app.router.lifespan_context(app):
            return None

    asyncio.run(run_lifespan())

    assert started is True
    assert shutdown is True
    assert len(added_jobs) == 1
    assert getattr(app.state, "scheduler", None) is not None
    job_args, job_kwargs = added_jobs[0]
    assert job_kwargs["trigger"] == "cron"
    assert job_kwargs["hour"] == 0
    assert job_kwargs["minute"] == 0
    assert str(job_kwargs["timezone"]) == "Asia/Ho_Chi_Minh"
