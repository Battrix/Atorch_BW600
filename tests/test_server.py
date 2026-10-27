import json
import threading
import time
import urllib.error
import urllib.request

import pytest
from atorch.server.app import create_server
from atorch.service.device import DeviceService
from atorch.transports.simulated import SimulatedTransport


@pytest.fixture()
def app():
    sim = SimulatedTransport(voltage_mv=3299, mode=1, setpoint=5.0, cutoff=3.0)
    svc = DeviceService(lambda: sim, poll_interval=0.02, settings_interval=0.05,
                        reconnect_delay=0.05, write_pause=0.0)
    svc.start()
    srv = create_server(svc, "127.0.0.1", 0, link="simulat")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    for _ in range(100):
        if svc.snapshot().settings:
            break
        time.sleep(0.02)
    yield base, sim
    srv.shutdown()
    svc.shutdown()


def get(base, path):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return r.status, r.read()


def post(base, path, body, headers=None):
    req = urllib.request.Request(base + path, json.dumps(body).encode(),
                                 {"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_state_and_static(app):
    base, _ = app
    st, body = get(base, "/api/state")
    d = json.loads(body)
    assert st == 200 and d["state"]["connected"] and d["device"]["profile"] == "bw600"
    assert d["limits"]["cc"] == [0.01, 50]
    assert get(base, "/")[0] == 200
    assert get(base, "/api/history")[0] == 200
    with pytest.raises(urllib.error.HTTPError) as e:
        get(base, "/../server/app.py")
    assert e.value.code == 404


def test_commands_flow(app):
    base, sim = app
    assert post(base, "/api/mode", {"mode": 0})[1]["ok"]
    assert post(base, "/api/value", {"name": "setpoint", "value": 0.5})[1]["ok"]
    assert post(base, "/api/value", {"name": "cutoff", "value": 3.1})[1]["ok"]
    assert post(base, "/api/power", {"on": True})[1]["message"] == "pornit"
    st, r = post(base, "/api/value", {"name": "cutoff", "value": 3.0})
    assert st == 409 and not r["ok"]                    # blocat cat ruleaza
    assert post(base, "/api/power", {"on": False})[1]["message"] == "oprit"
    assert not sim.running


def test_validation_errors(app):
    base, _ = app
    assert post(base, "/api/value", {"name": "ocp", "value": 999})[0] == 409
    assert post(base, "/api/value", {"name": "ocp"})[0] == 400
    assert post(base, "/api/nimic", {})[0] == 404


def test_cdc_api_and_interlock(app):
    base, sim = app
    assert get(base, '/cdc.html')[0] == 200
    assert json.loads(get(base, '/api/cdc/status')[1])['state'] == 'idle'
    for _ in range(100):
        if json.loads(get(base, '/api/state')[1])['state']['updated']:
            break
        time.sleep(.02)
    params = dict(current=1, empty_v=3, full_v=4.1, end_current=.1, double_start=True)
    assert post(base, '/api/cdc/start', dict(params, end_current=float('nan')))[0] == 409
    assert post(base, '/api/cdc/start', params)[0] == 200
    assert post(base, '/api/mode', {'mode': 0})[0] == 409
    assert post(base, '/api/cdc/start', params)[0] == 409
    assert post(base, '/api/cdc/stop', {})[0] == 200
    for _ in range(150):
        st = json.loads(get(base, '/api/cdc/status')[1])
        if st['state'] not in ('preparing', 'running', 'stopping'):
            break
        time.sleep(.02)
    assert st['stop_confirmed']
    assert not sim.running


def test_origin_check(app):
    base, _ = app
    st, r = post(base, "/api/power", {"on": False}, {"Origin": "http://evil.example"})
    assert st == 403
    host = base.removeprefix("http://")
    assert post(base, "/api/power", {"on": False}, {"Origin": f"http://{host}"})[0] == 200


def test_charger_api(app):
    base, _ = app
    assert not json.loads(get(base, '/api/charger/status')[1])['connected']
    assert json.loads(get(base, '/api/charger/ports')[1])[0]['port'] == 'SIMULATOR'
    assert post(base, '/api/charger/connect', {'port': 'SIMULATOR'})[0] == 200
    r = post(base, '/api/charger/configure', {'voltage': 4.1, 'current': 1})[1]['charger']
    assert r['set_voltage'] == 4.1 and not r['output']
    assert post(base, '/api/charger/output', {'on': True})[1]['charger']['output']
    assert post(base, '/api/charger/output', {'on': False})[0] == 200
    assert post(base, '/api/charger/disconnect', {})[0] == 200


def test_sse_stream(app):
    base, _ = app
    with urllib.request.urlopen(base + "/api/stream", timeout=5) as r:
        got = b""
        while b"event: sample" not in got:
            got += r.readline()
    assert b"event: sample" in got
