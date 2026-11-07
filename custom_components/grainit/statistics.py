"""Import the full load history into Home Assistant long-term statistics.

Creates one external statistic per product/direction, e.g.
`grainit:raagylle_kvaeg_ud`, holding cumulative tonnes per hour. A
statistics-graph card with `stat_types: [change]` then shows tonnes per
day, week or month for the whole history, also from before installation.
Re-importing is idempotent: existing hours are overwritten.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .api import Load
from .const import DOMAIN
from .summary import hourly_cumulative, stream_key

_LOGGER = logging.getLogger(__name__)


def statistic_id(key: str) -> str:
    return f"{DOMAIN}:{key}"


def _metadata(key: str, name: str) -> dict:
    from homeassistant.components.recorder.models import StatisticMetaData

    meta = {
        "has_sum": True,
        "name": name,
        "source": DOMAIN,
        "statistic_id": statistic_id(key),
        "unit_of_measurement": "t",
    }
    fields = getattr(StatisticMetaData, "__annotations__", {})
    if "mean_type" in fields:  # HA 2025.x and newer
        from homeassistant.components.recorder.models import StatisticMeanType

        meta["mean_type"] = StatisticMeanType.NONE
    if "has_mean" in fields:
        meta["has_mean"] = False
    if "unit_class" in fields:
        meta["unit_class"] = None
    return meta


def import_history(hass: HomeAssistant, loads: list[Load]) -> None:
    try:
        from homeassistant.components.recorder.statistics import (
            async_add_external_statistics,
        )
    except ImportError:
        _LOGGER.warning("Recorder not available, skipping Grainit statistics import")
        return

    tz = dt_util.get_default_time_zone()
    names = {
        stream_key(l.product, l.direction): f"Grainit {l.product} {l.direction}" for l in loads
    }
    for key, rows in hourly_cumulative(loads).items():
        stats = [
            {"start": hour.replace(tzinfo=tz), "sum": total, "state": total}
            for hour, total in rows
        ]
        try:
            async_add_external_statistics(hass, _metadata(key, names[key]), stats)
        except Exception:  # noqa: BLE001 - statistics are a bonus, never break setup
            _LOGGER.exception("Could not import Grainit statistics for %s", key)
