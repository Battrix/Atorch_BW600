import sys
from atorch.service.logfile import start_log


def test_tee_writes_console_and_file(tmp_path, capsys):
    old_out, old_err = sys.stdout, sys.stderr
    try:
        p = start_log("t", root=tmp_path)
        print("salut")
        sys.stdout.flush()
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    txt = p.read_text(encoding="utf-8")
    assert "salut" in txt and p.parent.name == "logs"
