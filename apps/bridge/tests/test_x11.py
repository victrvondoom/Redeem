"""The same executor on a real X server (Xvfb) with a real Chromium window."""
import base64
import http.server
import os
import shutil
import subprocess
import sys
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux" or not shutil.which("Xvfb"), reason="needs Linux with Xvfb")
PAGE = b'<title>T</title><input aria-label=n style="position:absolute;left:100px;top:100px;width:400px;font-size:24px"><p id=o></p><script>document.querySelector("input").oninput=e=>o.textContent="typed:"+e.target.value</script>'


@pytest.fixture
def desktop(tmp_path):
    n = 260 + os.getpid() % 30
    x = subprocess.Popen(["Xvfb", f":{n}", "-screen", "0", "1024x700x24", "-nolisten", "tcp"])
    time.sleep(0.8)
    os.environ["DISPLAY"], os.environ["REDEEM_BRIDGE_PROFILE"] = f":{n}", str(tmp_path / "prof")

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    from redeem_bridge.executor import Executor
    from redeem_bridge.platforms.x11 import X11Platform
    p = X11Platform()
    yield Executor(p), f"http://127.0.0.1:{srv.server_port}/"
    p.close()
    srv.shutdown()
    x.terminate()


def test_open_click_type_observe_and_local_controls(desktop):
    ex, url = desktop
    assert ex.run("open_url", {"url": url})["ok"]
    time.sleep(4)
    obs = ex.run("observe_screen", {})["observation"]
    assert obs["width"] == 1024 and any("chrom" in (w["app"] or "").lower() for w in obs["windows"])
    r = ex.run("click_coordinates", {"x": 300, "y": 300})  # anywhere in the page body; the input is focused by Tab below
    ex.run("press_key", {"key": "tab"})
    r = ex.run("type_text", {"text": "Priya Sharma 42!"})
    assert r["ok"] and r["typed"] == 16 and r["observation"]["cursor"] == {"x": 300, "y": 300}
    assert base64.b64decode(r["observation"]["png_b64"])[:4] == b"\x89PNG"
    ex.takeover.set()
    assert ex.run("type_text", {"text": "x"})["error"] == "user_has_control"
    assert ex.run("type_text", {"text": "x"}, actor="user")["ok"]  # the person may drive while they have control
    ex.stopped.set()
    assert ex.run("click_coordinates", {"x": 1, "y": 1}, actor="user")["error"] == "stopped"
    assert ex.run("key_combination", {"combo": "ctrl+alt+delete"})["error"] == "invalid_action"
