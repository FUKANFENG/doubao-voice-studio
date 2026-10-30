"""桌面工具合成数据测试，不读取真实登录态。"""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    import tkinter
except ImportError:
    raise unittest.SkipTest("当前环境未安装可选的 Tkinter 桌面组件")

SPEC = importlib.util.spec_from_file_location("auth_gui", Path(__file__).resolve().parents[1] / "auth_gui.py")
gui = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gui)


class AcquireTests(unittest.TestCase):
    def test_studio_address_rejects_external_hosts_credentials_and_paths(self):
        for address in ('https://example.com', 'http://127.0.0.1.evil.example',
                        'http://user@localhost:8000', 'http://localhost:8000/other',
                        'http://localhost:8000/?secret=value'):
            with self.subTest(address=address), self.assertRaises(gui.exporter.ExportError):
                gui.studio_address(address)
        self.assertEqual(gui.studio_address('http://127.0.0.1:18088/'), 'http://127.0.0.1:18088')

    def test_apply_sends_config_only_to_direct_local_service(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"auth_ok": true}'
        opener = MagicMock()
        opener.open.return_value = response
        with patch.object(gui.urllib.request, 'build_opener', return_value=opener):
            gui.apply_to_studio({'cookie': 'synthetic'}, 'http://127.0.0.1:18088')
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'http://127.0.0.1:18088/api/auth/import')
        self.assertEqual(json.loads(request.data), {'config': {'cookie': 'synthetic'}})
        self.assertEqual(request.get_header('X-doubao-local'), '1')

    def test_complete_config_and_partial_cookie_without_disk_write(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "auth.json"
            target.write_text(json.dumps({"web_id": "synthetic-web", "tea_uuid": "synthetic-tea"}), encoding="utf-8")
            before = target.read_bytes()
            with patch.object(gui.exporter, "collect_cookies", return_value=("sessionid=synthetic", 1)):
                result = gui.acquire(directory, "Default", str(target), "")
                self.assertEqual(result["config"]["cookie"], "sessionid=synthetic")
                self.assertEqual(target.read_bytes(), before)
                partial = gui.acquire(directory, "Default", "", "")
                self.assertIsNone(partial["config"])
                self.assertEqual(partial["cookie"], "sessionid=synthetic")
                self.assertIn("缺少", partial["warning"])

    def test_worker_error_never_echoes_unexpected_secret(self):
        window = object.__new__(gui.AuthWindow)
        window.events = gui.queue.Queue()
        with patch.object(gui, "acquire", side_effect=RuntimeError("synthetic-secret")):
            window.worker("", "", "", "")
        kind, message = window.events.get_nowait()
        self.assertEqual(kind, "error")
        self.assertNotIn("synthetic-secret", message)


@unittest.skipUnless(os.environ.get('DOUBAO_TEST_GUI') == '1', '窗口测试需显式启用 DOUBAO_TEST_GUI=1')
class WindowTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = gui.tk.Tk()
        except gui.tk.TclError:
            self.skipTest("没有桌面显示环境")
        self.root.withdraw()
        self.window = gui.AuthWindow(self.root)
        self.addCleanup(self.window.close)

    def deliver(self, payload):
        self.window.events.put(("result", payload))
        self.window.poll()

    def test_display_copy_and_clear_with_synthetic_data(self):
        payload = {"cookie": "sessionid=synthetic", "count": 1,
                   "config": {"cookie": "sessionid=synthetic", "web_id": "demo", "tea_uuid": "demo"}, "warning": ""}
        self.deliver(payload)
        self.assertEqual(json.loads(self.window.text.get("1.0", "end")), payload["config"])
        # 验证复制动作，不覆盖用户当前剪贴板。
        with patch.object(self.root, "clipboard_clear") as clear, patch.object(self.root, "clipboard_append") as append:
            self.window.copy_config()
            clear.assert_called_once()
            self.assertEqual(json.loads(append.call_args.args[0]), payload["config"])
            self.window.copy_cookie()
            self.assertEqual(append.call_args.args[0], payload["cookie"])
        self.window.clear()
        self.assertIsNone(self.window.result)
        self.assertEqual(self.window.text.get("1.0", "end").strip(), "")
        self.assertIn("disabled", self.window.copy_button.state())

    def test_partial_config_disables_full_copy(self):
        self.deliver({"cookie": "sessionid=synthetic", "count": 1, "config": None, "warning": "缺少设备参数"})
        self.assertIn("disabled", self.window.copy_button.state())
        self.assertNotIn("disabled", self.window.cookie_button.state())
        self.assertIn("缺少设备参数", self.window.status.get())


if __name__ == "__main__":
    unittest.main()
