"""python -m redeem_bridge pair --server https://redeem.example --code ABCD-1234
   python -m redeem_bridge run [--no-ui]"""
import argparse
import signal
import sys

from . import client
from .platforms import current


def main(argv=None):
    ap = argparse.ArgumentParser(prog="redeem-bridge")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pair")
    p.add_argument("--server", required=True)
    p.add_argument("--code", required=True)
    p.add_argument("--name")
    r = sub.add_parser("run")
    r.add_argument("--no-ui", action="store_true")
    sub.add_parser("forget")
    a = ap.parse_args(argv)
    if a.cmd == "pair":
        cfg = client.pair(a.server, a.code, a.name, current())
        print(f"Paired as device {cfg['device_id']}. Start it with: python -m redeem_bridge run")
        return 0
    if a.cmd == "forget":
        client.CONFIG.unlink(missing_ok=True)
        print("Local credentials deleted.")
        return 0
    cfg = client.load()
    if not cfg:
        print("Not paired. Run: python -m redeem_bridge pair --server URL --code CODE", file=sys.stderr)
        return 2
    b = client.Bridge(cfg, current(), on_status=lambda s: print(f"[bridge] {s}", flush=True))
    signal.signal(signal.SIGINT, lambda *_: (b.local("stop"), b.quit.set()))
    if a.no_ui:
        b.run_forever()
    else:
        from .ui import run_with_ui
        run_with_ui(b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
