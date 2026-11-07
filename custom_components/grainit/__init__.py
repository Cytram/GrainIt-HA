"""The Grainit integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import GrainitAuthError, GrainitClient, GrainitConnectionError, Load
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_NEW_LOAD,
    HISTORY_INTERVAL_HOURS,
    HISTORY_START,
)
from .statistics import import_history
from .summary import Stream, Summary, fertilizer_year_start, stream_key, summarize

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]


class GrainitCoordinator(DataUpdateCoordinator[Summary]):
    def __init__(self, hass: HomeAssistant, client: GrainitClient, minutes: int) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=timedelta(minutes=minutes)
        )
        self.client = client
        # Every product/direction ever seen, so sensors exist (as 0) even
        # when a product has had no loads this fertilizer year.
        self.known_streams: dict[str, tuple[str, str]] = {}
        self._last_history: datetime | None = None
        self._seen_ids: set[int] | None = None

    async def _maybe_import_history(self, now: datetime) -> None:
        if self._last_history and now - self._last_history < timedelta(hours=HISTORY_INTERVAL_HOURS):
            return
        start = datetime.strptime(HISTORY_START, "%d-%m-%Y").date()
        try:
            loads = await self.client.get_loads(start, now.date())
        except GrainitConnectionError as err:
            _LOGGER.warning("Could not fetch Grainit history: %s", err)
            return
        for l in loads:
            self.known_streams[stream_key(l.product, l.direction)] = (l.product, l.direction)
        import_history(self.hass, loads)
        self._last_history = now
        _LOGGER.debug("Imported %d Grainit loads into statistics", len(loads))

    def _fire_new_loads(self, loads: list[Load]) -> None:
        ids = {l.reg_id for l in loads if l.reg_id is not None}
        if self._seen_ids is None:  # first run: remember, don't fire
            self._seen_ids = ids
            return
        for load in loads:
            if load.reg_id is not None and load.reg_id not in self._seen_ids:
                self.hass.bus.async_fire(
                    EVENT_NEW_LOAD,
                    {
                        "registration_id": load.reg_id,
                        "time": load.time.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        ).isoformat(),
                        "product": load.product,
                        "direction": load.direction,
                        "kg": load.kg,
                        "tonnes": round(load.tonnes, 2),
                        "from": load.source,
                        "to": load.destination,
                        "driver": load.driver,
                    },
                )
        self._seen_ids |= ids

    async def _async_update_data(self) -> Summary:
        now = dt_util.now().replace(tzinfo=None)  # portal times are local, naive
        try:
            await self._maybe_import_history(now)
            loads = await self.client.get_loads(fertilizer_year_start(now.date()), now.date())
        except GrainitAuthError as err:
            raise ConfigEntryAuthFailed from err
        except GrainitConnectionError as err:
            raise UpdateFailed(str(err)) from err

        for l in loads:
            self.known_streams[stream_key(l.product, l.direction)] = (l.product, l.direction)
        self._fire_new_loads(loads)

        summary = summarize(loads, now)
        for key, (product, direction) in self.known_streams.items():
            summary.streams.setdefault(key, Stream(product, direction))
        return summary


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar())
    client = GrainitClient(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = GrainitCoordinator(hass, client, minutes)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return ok
