import sys, types, importlib, json
from datetime import datetime
from pathlib import Path
cc = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[1] / "custom_components")
aio = types.ModuleType("aiohttp"); aio.ClientSession = object; aio.ClientError = Exception
aio.ClientTimeout = lambda **k: None; sys.modules["aiohttp"] = aio
pkg = types.ModuleType("grainit"); pkg.__path__ = [cc + "/grainit"]; sys.modules["grainit"] = pkg
api = importlib.import_module("grainit.api"); summ = importlib.import_module("grainit.summary")
n = api._num
assert n("28.540") == 28540 and n("1.234.567") == 1234567 and n("12.345,6") == 12345.6
assert n("540") == 540 and n("1.5") == 1.5 and n("-28.540") == -28540 and n("") is None
d = api._decode
assert d("Rågylle Kvæg".encode()) == "Rågylle Kvæg" and d("Kvæg".encode("latin-1")) == "Kvæg"
html = """<table><thead><tr><th>Dato</th></tr></thead><tbody>
<tr onclick="printRegistration(123)"><td>06-11-2026 14:05</td><td>Rågylle Kvæg</td><td>Tank 1</td><td>Mark 7</td><td>Ole</td><td>123</td><td>-28.540</td><td>28.540</td><td>kg</td><td></td></tr>
<tr onclick="printRegistration(124)"><td>07-11-2026 08:10</td><td>Afgasset gylle</td><td>Biogas</td><td>Tank 1</td><td>Ole</td><td>123</td><td>+30.120</td><td>30.120</td><td>kg</td><td></td></tr>
<tr><td colspan="10">Ingen registeringer fundet</td></tr></tbody></table>"""
loads = api.parse_loads(d(html.encode("latin-1")))
assert [(l.reg_id, l.direction, l.kg, l.product) for l in loads] == [(123,"ud",28540,"Rågylle Kvæg"),(124,"ind",30120,"Afgasset gylle")], loads
s = summ.summarize(loads, datetime(2026,11,7,12,0))
assert s.streams["raagylle_kvaeg_ud"].week_t == 28.54 and s.streams["afgasset_gylle_ind"].today_t == 30.12
assert s.today_count == 1 and s.month_count == 2 and s.last_load.reg_id == 124
assert summ.fertilizer_year_start(datetime(2026,7,1).date()).year == 2025
print("v0.2.1 tests passed")
