"""Grainit sensors.

Per product and direction (e.g. "Rågylle Kvæg ud"):
  sensor.grainit_<key>_i_dag          tonnes today
  sensor.grainit_<key>_denne_uge      tonnes this week (Mon-Sun)
  sensor.grainit_<key>_denne_maaned   tonnes this month
  sensor.grainit_<key>_goedningsaar   tonnes this fertilizer year (from 1 Aug)
  sensor.grainit_<key>_laes_i_dag     number of loads today
  sensor.grainit_<key>_seneste        time of the latest load

Overall:
  sensor.grainit_seneste_laes         time of the latest load (+ details and
                                      the last 20 loads in attribute "laes")
  sensor.grainit_laes_i_dag           number of loads today
  sensor.grainit_laes_denne_maaned    number of loads this month
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .statistics import statistic_id
from .summary import Stream, Summary

DIRECTION_LABEL = {"ind": "ind", "ud": "ud"}


def _aware(value):
    if value is None:
        return None
    return value.replace(tzinfo=dt_util.get_default_time_zone())


@dataclass(frozen=True)
class StreamField:
    suffix: str
    label: str
    unit: str | None
    icon: str
    value: Callable[[Stream], object]
    timestamp: bool = False


STREAM_FIELDS = [
    StreamField("i_dag", "i dag", "t", "mdi:truck", lambda s: round(s.today_t, 2)),
    StreamField("denne_uge", "denne uge", "t", "mdi:calendar-week", lambda s: round(s.week_t, 2)),
    StreamField("denne_maaned", "denne måned", "t", "mdi:calendar-month", lambda s: round(s.month_t, 2)),
    StreamField("goedningsaar", "gødningsår", "t", "mdi:calendar-range", lambda s: round(s.year_t, 1)),
    StreamField("laes_i_dag", "læs i dag", "læs", "mdi:counter", lambda s: s.today_count),
    StreamField("seneste", "seneste læs", None, "mdi:clock-outline", lambda s: _aware(s.last_time), True),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            GrainitLastLoadSensor(coordinator, entry),
            GrainitCountSensor(coordinator, entry, "laes_i_dag", "Læs i dag", lambda s: s.today_count),
            GrainitCountSensor(
                coordinator, entry, "laes_denne_maaned", "Læs denne måned", lambda s: s.month_count
            ),
        ]
    )

    known: set[str] = set()

    @callback
    def _add_streams() -> None:
        summary: Summary | None = coordinator.data
        if not summary:
            return
        new = []
        for key in summary.streams:
            if key in known:
                continue
            known.add(key)
            new += [GrainitStreamSensor(coordinator, entry, key, f) for f in STREAM_FIELDS]
        if new:
            async_add_entities(new)

    _add_streams()
    entry.async_on_unload(coordinator.async_add_listener(_add_streams))


class _Base(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, object_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{object_id}"
        self.entity_id = f"sensor.grainit_{object_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Grainit",
            manufacturer="Grainit",
            configuration_url="https://portal.grainit.net",
        )

    @property
    def summary(self) -> Summary:
        return self.coordinator.data


class GrainitStreamSensor(_Base):
    def __init__(self, coordinator, entry, key: str, field: StreamField) -> None:
        super().__init__(coordinator, entry, f"{key}_{field.suffix}")
        self._key = key
        self._field = field
        stream = coordinator.data.streams[key]
        self._attr_name = f"{stream.product} {DIRECTION_LABEL[stream.direction]} {field.label}"
        self._attr_icon = field.icon
        self._attr_native_unit_of_measurement = field.unit
        if field.timestamp:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        stream = self.summary.streams.get(self._key)
        return self._field.value(stream) if stream else None

    @property
    def extra_state_attributes(self):
        if self._field.suffix != "goedningsaar":
            return None
        stream = self.summary.streams.get(self._key)
        return {
            "produkt": stream.product if stream else None,
            "retning": stream.direction if stream else None,
            "antal_laes": stream.year_count if stream else 0,
            "statistik_id": statistic_id(self._key),
        }


class GrainitCountSensor(_Base):
    _attr_icon = "mdi:counter"
    _attr_native_unit_of_measurement = "læs"

    def __init__(self, coordinator, entry, object_id: str, name: str, value) -> None:
        super().__init__(coordinator, entry, object_id)
        self._attr_name = name
        self._value = value

    @property
    def native_value(self):
        return self._value(self.summary)


class GrainitLastLoadSensor(_Base):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:truck-check"
    # The load list changes every update; keep it out of the recorder.
    _unrecorded_attributes = frozenset({"laes"})

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "seneste_laes")
        self._attr_name = "Seneste læs"

    @property
    def native_value(self):
        last = self.summary.last_load
        return _aware(last.time) if last else None

    @property
    def extra_state_attributes(self):
        last = self.summary.last_load
        attrs = {
            "laes": [
                {
                    "tid": _aware(l.time).isoformat(),
                    "produkt": l.product,
                    "retning": l.direction,
                    "ton": round(l.tonnes, 2),
                    "fra": l.source,
                    "til": l.destination,
                    "chauffoer": l.driver,
                }
                for l in self.summary.recent
            ]
        }
        if last:
            attrs.update(
                {
                    "produkt": last.product,
                    "retning": last.direction,
                    "ton": round(last.tonnes, 2),
                    "fra": last.source,
                    "til": last.destination,
                    "chauffoer": last.driver,
                    "registrering": last.reg_id,
                }
            )
        return attrs
