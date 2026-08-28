"""The demo scheduler exists to keep numen.team's demo org looking fresh.

Every self-hosted deployment was starting it too, so an internal install woke a
task every 60 seconds forever to look for demo orgs it will never have.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.workers.demo_scheduler import DemoScheduler


@pytest.mark.asyncio
async def test_does_not_run_when_demo_mode_is_off():
    """The default for anyone who is not us."""
    scheduler = DemoScheduler()

    with (
        patch("src.workers.demo_scheduler.settings") as mock_settings,
        patch.object(scheduler, "_apply_variance", new=AsyncMock()) as variance,
        patch("asyncio.sleep", new=AsyncMock(side_effect=AssertionError("polled anyway"))),
    ):
        mock_settings.demo_mode = False
        await scheduler.run()

    variance.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_returns_immediately_rather_than_looping():
    """It must exit, not spin - a task that never yields blocks shutdown."""
    scheduler = DemoScheduler()

    with patch("src.workers.demo_scheduler.settings") as mock_settings:
        mock_settings.demo_mode = False
        await scheduler.run()

    assert scheduler._running is False


@pytest.mark.asyncio
async def test_demo_mode_on_starts_the_poll_loop():
    scheduler = DemoScheduler()

    async def stop_after_first_sleep(_seconds):
        scheduler.stop()

    with (
        patch("src.workers.demo_scheduler.settings") as mock_settings,
        patch("src.workers.demo_scheduler.asyncio.sleep", new=stop_after_first_sleep),
    ):
        mock_settings.demo_mode = True
        await scheduler.run()

    # Reaching the sleep at all means the loop body ran.
    assert scheduler._running is False


def test_demo_mode_defaults_to_off():
    from src.config import Settings

    assert Settings.model_fields["demo_mode"].default is False
