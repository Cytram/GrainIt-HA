"""Small client for the Grainit web portal.

Grainit has no public API. This logs in the same way the website does
(form POST, session cookie) and reads the movement list ("Lagerbevægelser")
from /ajax/dashboard_status.php?action=get_movements_status_details_v2.
That endpoint answers JSON {"success": 1, "html": "<table>..."} with one
row per load: date, product, from, to, driver, signed amount, amount, unit.
"""

from __future__ import annotations

import asyncio
import codecs
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser

import aiohttp

from .const import BASE_URL, LOGIN_URL, MOVEMENTS_URL

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=90)
_REG_ID = re.compile(r"printRegistration\((\d+)")
# Danish thousands without decimals, e.g. "28.540" = 28540.
_THOUSANDS = re.compile(r"-?\d{1,3}(\.\d{3})+")

# The portal mixes UTF-8 with Latin-1 bytes (e.g. a raw 0xE6 for "æ"), so bytes
# that are not valid UTF-8 are read as Windows-1252 one stretch at a time.
codecs.register_error(
    "grainit_cp1252",
    lambda err: (err.object[err.start:err.end].decode("cp1252", "replace"), err.end),
)


def _decode(body: bytes) -> str:
    return body.decode("utf-8", "grainit_cp1252")


class GrainitAuthError(Exception):
    """Wrong e-mail or password."""


class GrainitConnectionError(Exception):
    """Portal could not be reached or answered unexpectedly."""


@dataclass(frozen=True)
class Load:
    """One registered load (one row in the movement list)."""

    reg_id: int | None
    time: datetime  # naive, portal local time (Europe/Copenhagen)
    product: str
    source: str
    destination: str
    driver: str
    direction: str  # "ind" or "ud"
    kg: float

    @property
    def tonnes(self) -> float:
        return self.kg / 1000.0


def _to_kg(amount: float, unit: str) -> float:
    unit = unit.strip().lower()
    if unit in ("t", "ton", "tons", "1000 kg"):
        return amount * 1000
    if unit == "100 kg":
        return amount * 100
    return amount  # kg (all rows seen so far)


def _num(text: str) -> float | None:
    text = text.replace("\xa0", "").replace(" ", "").strip()
    if not text:
        return None
    if "," in text:  # Danish format 12.345,6
        text = text.replace(".", "").replace(",", ".")
    elif _THOUSANDS.fullmatch(text):  # 28.540
        text = text.replace(".", "")
    try:
        return float(text)
    except ValueError:
        return None


class _RowParser(HTMLParser):
    """Collect (row_html_attrs, [cell texts]) for every <tr> in <tbody>."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple[int | None, list[str]]] = []
        self._in_body = False
        self._row: list[str] | None = None
        self._reg: int | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tbody":
            self._in_body = True
        elif tag == "tr" and self._in_body:
            self._row, self._reg = [], None
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        if self._row is not None and self._reg is None:
            for _, value in attrs:
                if value and (m := _REG_ID.search(value)):
                    self._reg = int(m.group(1))
                    break

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append((self._reg, self._row))
            self._row = None
        elif tag == "tbody":
            self._in_body = False

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def parse_loads(html: str) -> list[Load]:
    """Parse the movement table. Columns:
    Dato | Produkter | Fra | Til | Bruger | CVR | ±Mængde | Mængde | Enhed | Ref
    """
    parser = _RowParser()
    parser.feed(html)
    loads: list[Load] = []
    for reg_id, cells in parser.rows:
        if len(cells) < 9:
            continue
        try:
            when = datetime.strptime(cells[0], "%d-%m-%Y %H:%M")
        except ValueError:
            continue  # "Ingen registeringer fundet" and other non-data rows
        signed = cells[6].strip()
        amount = _num(cells[7])
        if amount is None:
            amount = abs(_num(re.sub(r"[^\d,.\-]", "", signed)) or 0.0)
        direction = "ud" if signed.startswith("-") else "ind"
        loads.append(
            Load(
                reg_id=reg_id,
                time=when,
                product=cells[1],
                source=cells[2],
                destination=cells[3],
                driver=cells[4],
                direction=direction,
                kg=_to_kg(abs(amount), cells[8] or "kg"),
            )
        )
    loads.sort(key=lambda l: (l.time, l.reg_id or 0))
    return loads


class GrainitClient:
    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._logged_in = False

    async def login(self) -> None:
        data = {
            "offset": "60",
            "email": self._email,
            "password": self._password,
            "remember_login": "1",
        }
        try:
            async with self._session.post(
                LOGIN_URL, data=data, allow_redirects=True, timeout=_TIMEOUT
            ) as resp:
                text = _decode(await resp.read())
                final_url = str(resp.url)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise GrainitConnectionError(f"Login request failed: {err}") from err

        if "action=logout" not in text and "homepage" not in final_url:
            raise GrainitAuthError("Login failed")
        self._logged_in = True

    async def _fetch(self, start: date, end: date) -> list[Load] | None:
        """Return loads, or None when the session is no longer valid."""
        params = {
            "action": "get_movements_status_details_v2",
            "start_date": start.strftime("%d-%m-%Y"),
            "end_date": end.strftime("%d-%m-%Y"),
            "category_id": "",
            "product_id": "",
            "location_from_id": "",
            "location_to_id": "",
            "reg_type": "",
            "group_by_product": "0",
            "group_by_from_location": "0",
            "group_by_location": "0",
            "show_grouped_count": "0",
            "group_by_period": "",
            "secondary_products": "0",
            "weight_dried": "0",
        }
        try:
            async with self._session.get(
                MOVEMENTS_URL,
                params=params,
                allow_redirects=False,
                headers={
                    "Referer": f"{BASE_URL}/?action=dashboard_movements_status_details_v2",
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status in (301, 302, 401, 403):
                    return None
                resp.raise_for_status()
                text = _decode(await resp.read())
        except (aiohttp.ClientError, TimeoutError) as err:
            raise GrainitConnectionError(f"Fetching loads failed: {err}") from err

        # The portal returns JSON with a text/html content type, and plain
        # text such as "Ingen adgang" when the session has expired.
        try:
            payload = json.loads(text)
        except ValueError:
            return None
        if not isinstance(payload, dict) or payload.get("success") != 1:
            return None
        # Full history is ~2 MB of HTML; parse it off the event loop.
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, parse_loads, payload.get("html") or "")

    async def get_loads(self, start: date, end: date) -> list[Load]:
        if not self._logged_in:
            await self.login()
        loads = await self._fetch(start, end)
        if loads is None:
            _LOGGER.debug("Grainit session not valid, logging in again")
            await self.login()
            loads = await self._fetch(start, end)
            if loads is None:
                raise GrainitConnectionError("Grainit answered without data (Ingen adgang?)")
        return loads
