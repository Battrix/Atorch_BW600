import threading
import time
from atorch.service.sniff import monitor
from atorch.transports.simulated import SimulatedTransport


def test_reports_mode_change_and_ignores_noise():
    sim = SimulatedTransport(voltage_mv=3299, mode=1)
    lines = []
    th = threading.Thread(target=lambda: monitor(sim, seconds=1.2, interval=0.05, say=lines.append))
    th.start()
    time.sleep(0.4)
    sim.mode = 5                      # utilizatorul schimba modul pe aparat
    sim.voltage_mv = 3301             # zgomot: nu trebuie raportat
    th.join()
    assert any("initial" in l for l in lines)
    changes = [l for l in lines if "off 44: 01 -> 05" in l]
    assert changes and all("[03]" in l for l in changes)
    assert not any("[05]" in l and "off" in l for l in lines)       # V/A/W nu apar
