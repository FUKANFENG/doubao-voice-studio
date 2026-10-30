"""登录态导出测试：仅使用合成 Cookie、临时 SQLite 和模拟 DPAPI，不访问真实账号。"""
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("export_auth", Path(__file__).resolve().parents[1] / "export_auth.py")
export = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(export)


class ExportAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.key = b"k" * 32

    def encrypted(self, plain):
        from Crypto.Cipher import AES
        cipher = AES.new(self.key, AES.MODE_GCM, nonce=b"n" * 12)
        ciphertext, tag = cipher.encrypt_and_digest(plain)
        return b"v10" + b"n" * 12 + ciphertext + tag

    def database(self, rows, version=23):
        folder = self.root / "Default" / "Network"
        folder.mkdir(parents=True)
        with contextlib.closing(sqlite3.connect(folder / "Cookies")) as con, con:
            con.execute("CREATE TABLE meta (key TEXT, value TEXT)")
            con.execute("INSERT INTO meta VALUES ('version', ?)", (str(version),))
            con.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, path TEXT, expires_utc INTEGER, encrypted_value BLOB, value TEXT)")
            con.executemany("INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?)", rows)

    def test_authenticated_gcm_and_domain_digest(self):
        plain = hashlib.sha256(b".doubao.com").digest() + b"synthetic-session"
        blob = self.encrypted(plain)
        self.assertEqual(export.decrypt_value(blob, self.key, ".doubao.com", 24), "synthetic-session")
        with self.assertRaises(export.ExportError):
            export.decrypt_value(blob, self.key, ".other.example", 24)
        broken = blob[:-1] + bytes([blob[-1] ^ 1])
        with self.assertRaises(export.ExportError):
            export.decrypt_value(broken, self.key, ".doubao.com", 24)
        # 旧数据库不应按启发式删除合法值的前 32 字节。
        old = b"a" * 70
        self.assertEqual(export.decrypt_value(self.encrypted(old), self.key, ".doubao.com", 23), old.decode())

    def test_v20_fails_without_bypassing_protection(self):
        with self.assertRaisesRegex(export.ExportError, "v20"):
            export.decrypt_value(b"v20unsupported", self.key, ".doubao.com", 24)

    def test_master_key_uses_current_user_dpapi(self):
        (self.root / "Local State").write_text(json.dumps({"os_crypt": {
            "encrypted_key": base64.b64encode(b"DPAPIwrapped-key").decode()
        }}), encoding="utf-8")
        with patch.object(export, "unprotect", return_value=self.key) as unprotect:
            self.assertEqual(export.load_key(self.root), self.key)
            unprotect.assert_called_once_with(b"wrapped-key")

    def test_scope_expiry_and_login_requirement(self):
        expiry = int((export.CHROMIUM_EPOCH + 900) * 1_000_000)
        self.database([
            (".doubao.com", "sessionid", "/", 0, b"", "synthetic-session"),
            (".doubao.com", "expired", "/", expiry, b"", "old"),
            (".doubao.com", "private_path", "/chat", 0, b"", "hidden"),
            (".doubao.com.evil.example", "unrelated", "/", 0, b"", "hidden"),
            ("doubao.com", "host_only", "/", 0, b"", "hidden"),
            (".doubao.com", "LARK_OTHER", "/", 0, b"", "hidden"),
        ])
        with patch.object(export, "load_key", side_effect=AssertionError("不应读取密钥")):
            cookie, count = export.collect_cookies(self.root, "Default", now=1000)
        self.assertEqual(cookie, "sessionid=synthetic-session")
        self.assertEqual(count, 1)
        with contextlib.closing(sqlite3.connect(self.root / "Default/Network/Cookies")) as con, con:
            con.execute("DELETE FROM cookies WHERE name='sessionid'")
        with self.assertRaisesRegex(export.ExportError, "登录会话"):
            export.collect_cookies(self.root, "Default", now=1000)

    def test_encrypted_database_and_failure_do_not_export_placeholders(self):
        blob = self.encrypted(hashlib.sha256(b".doubao.com").digest() + b"synthetic-session")
        self.database([(".doubao.com", "sessionid", "/", 0, blob, "")], version=24)
        with patch.object(export, "load_key", return_value=self.key):
            self.assertEqual(export.collect_cookies(self.root, "Default")[0], "sessionid=synthetic-session")
        with patch.object(export, "load_key", return_value=b"x" * 32):
            with self.assertRaises(export.ExportError):
                export.collect_cookies(self.root, "Default")

    def test_read_only_connection_sees_committed_wal(self):
        self.database([])
        with contextlib.closing(sqlite3.connect(self.root / "Default/Network/Cookies")) as writer, writer:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?)",
                           (".doubao.com", "sessionid", "/", 0, b"", "wal-session"))
            writer.commit()
            self.assertEqual(export.collect_cookies(self.root, "Default")[0], "sessionid=wal-session")

    def test_config_preserves_settings_without_guessing_device_ids(self):
        existing = {"web_id": "actual-web", "tea_uuid": "actual-tea", "proxy": "http://localhost:1234",
                    "access_key": "synthetic-key", "overrides": {"device_id": "actual-device"}}
        config = export.make_config(existing, "sessionid=new")
        self.assertEqual(config["proxy"], existing["proxy"])
        self.assertEqual(config["access_key"], existing["access_key"])
        self.assertEqual(config["overrides"], existing["overrides"])
        self.assertIsNot(config["overrides"], existing["overrides"])
        with self.assertRaisesRegex(export.ExportError, "缺少"):
            export.make_config({}, "sessionid=new")
        url = "wss://ws-samantha.doubao.com/samantha/audio/tts?web_id=actual-web&tea_uuid=actual-tea&pc_version=1.2.3&unknown_secret=hidden"
        config = export.make_config({}, "sessionid=new", request_url=url)
        self.assertEqual(config["overrides"], {"pc_version": "1.2.3"})
        self.assertNotIn("hidden", json.dumps(config))
        with self.assertRaises(export.ExportError):
            export.make_config({}, "", request_url=url.replace("ws-samantha.doubao.com", "evil.example"))
        with self.assertRaises(export.ExportError):
            export.make_config({}, "", request_url=url + "&web_id=duplicate")

    def test_invalid_config_does_not_overwrite_original(self):
        target = self.root / "auth.json"
        target.write_text('{"cookie": "synthetic-secret",', encoding="utf-8")
        before = target.read_bytes()
        with self.assertRaises(export.ExportError):
            export.load_config(target)
        self.assertEqual(target.read_bytes(), before)
        with patch.object(export.os, "replace", side_effect=PermissionError):
            with self.assertRaises(export.ExportError):
                export.save_config(target, {"cookie": "new-secret"})
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(list(self.root.glob(".auth-export-*")), [])

    def test_cli_check_is_offline_does_not_write_or_print_credentials(self):
        target = self.root / "auth.json"
        target.write_text(json.dumps({"web_id": "actual-web", "tea_uuid": "actual-tea"}), encoding="utf-8")
        before = target.read_bytes()
        out, err = io.StringIO(), io.StringIO()
        with patch.object(export.sys, "platform", "win32"), \
                patch.dict(export.os.environ, {}, clear=True), \
                patch.object(export, "collect_cookies", return_value=("sessionid=synthetic-secret", 1)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            args = ["--user-data-dir", str(self.root), "--output", str(target)]
            self.assertEqual(export.main([*args, "--check"]), 0)
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(export.main(args), 0)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["cookie"], "sessionid=synthetic-secret")
        self.assertNotIn("synthetic-secret", out.getvalue() + err.getvalue())
        self.assertEqual(list(self.root.glob(".auth-export-*")), [])

    def test_invalid_cli_arguments_do_not_echo_secrets(self):
        for args in (["--request_url", "wss://example.invalid/?token=synthetic-secret"],
                     ["--unknown=synthetic-secret"], ["--output"]):
            out, err = io.StringIO(), io.StringIO()
            with patch.object(export, "collect_cookies") as collect, \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as caught:
                    export.main(args)
            self.assertEqual(caught.exception.code, 2)
            self.assertNotIn("synthetic-secret", out.getvalue() + err.getvalue())
            collect.assert_not_called()

    def test_cli_unexpected_error_is_redacted_and_retains_config(self):
        target = self.root / "auth.json"
        target.write_text(json.dumps({"web_id": "actual-web", "tea_uuid": "actual-tea"}), encoding="utf-8")
        before = target.read_bytes()
        out, err = io.StringIO(), io.StringIO()
        with patch.object(export.sys, "platform", "win32"), \
                patch.dict(export.os.environ, {}, clear=True), \
                patch.object(export, "collect_cookies", side_effect=ValueError("synthetic-secret")) as collect, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(export.main(["--user-data-dir", str(self.root), "--output", str(target)]), 1)
        collect.assert_called_once_with(self.root, "Default")
        self.assertNotIn("synthetic-secret", out.getvalue() + err.getvalue())
        self.assertEqual(target.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
