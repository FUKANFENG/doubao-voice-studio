"""导出当前 Windows 用户的豆包 PC 客户端登录态；不联网、不打印凭据。"""
from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
CHROMIUM_EPOCH = 11644473600
FIELDS = {"cookie", "web_id", "tea_uuid", "language", "region", "proxy", "access_key", "overrides"}
PARAMS = {
    "version_code", "language", "device_platform", "aid", "real_aid", "pkg_type",
    "runtime_version", "pc_version", "doubao_pc_version", "doubao_device_platform",
    "web_platform", "client_platform", "device_id", "fp", "region", "sys_region",
    "runtime", "samantha_web", "use-olympus-account",
}


class ExportError(Exception):
    """可直接显示给用户、不包含凭据的错误。"""


def unprotect(blob: bytes) -> bytes:
    """使用当前 Windows 用户的 DPAPI，不请求界面或管理员权限。"""
    if sys.platform != "win32":
        raise ExportError("本机提取仅支持 Windows；导出的配置可供其他系统使用。")
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob),
    ]
    crypt.CryptUnprotectData.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    source = DataBlob(len(blob), buf)
    result = DataBlob()
    if not crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None,
                                   1, ctypes.byref(result)):
        raise ExportError("DPAPI 解密失败。请以登录豆包的原 Windows 用户运行。")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel.LocalFree(result.pbData)


def load_key(user_data: Path) -> bytes:
    try:
        state = json.loads((user_data / "Local State").read_text(encoding="utf-8"))
        wrapped = base64.b64decode(state["os_crypt"]["encrypted_key"], validate=True)
    except (OSError, ValueError, KeyError, TypeError):
        raise ExportError("无法读取 Local State 中的加密密钥，请确认客户端用户数据目录。") from None
    if not wrapped.startswith(b"DPAPI"):
        raise ExportError("此客户端的密钥保护格式不受支持。")
    key = unprotect(wrapped[5:])
    if len(key) not in (16, 24, 32):
        raise ExportError("客户端加密密钥长度无效。")
    return key


def decrypt_value(blob: bytes, key: bytes, host: str, version: int) -> str:
    if blob.startswith(b"v20"):
        raise ExportError("检测到 v20 App-Bound 加密，本脚本不支持；请从本人已登录页面的请求手动配置。")
    if blob[:3] in (b"v10", b"v11"):
        if len(blob) < 31:
            raise ExportError("Cookie 加密数据不完整。")
        try:
            from Crypto.Cipher import AES
        except ImportError:
            raise ExportError("缺少 pycryptodome，请安装 requirements-auth.txt 中的依赖。") from None
        try:
            cipher = AES.new(key, AES.MODE_GCM, nonce=blob[3:15])
            plain = cipher.decrypt_and_verify(blob[15:-16], blob[-16:])
        except ValueError:
            raise ExportError("Cookie 解密或完整性校验失败。") from None
    else:
        plain = unprotect(blob)
    if version >= 24:
        digest = hashlib.sha256(host.encode("utf-8")).digest()
        if not hmac.compare_digest(plain[:32], digest):
            raise ExportError("Cookie 域名摘要校验失败，未导出不完整的登录态。")
        plain = plain[32:]
    try:
        return plain.decode("utf-8")
    except UnicodeDecodeError:
        raise ExportError("Cookie 内容编码无效，未导出。") from None


def collect_cookies(user_data: Path, profile: str, now: float | None = None) -> tuple[str, int]:
    if Path(profile).name != profile or profile in (".", "..") or "/" in profile or "\\" in profile:
        raise ExportError("profile 必须是用户数据目录中的单个目录名。")
    folder = user_data / profile
    database = folder / "Network" / "Cookies"
    if not database.is_file():
        database = folder / "Cookies"
    if not database.is_file():
        raise ExportError("找不到豆包 Cookies 数据库；请先登录客户端，或指定 --user-data-dir / --profile。")
    now = time.time() if now is None else now
    con = None
    try:
        # 同一只读事务读取版本及数据；让 SQLite 处理 WAL，不复制可能不一致的主库。
        con = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
        con.execute("BEGIN")
        record = con.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()
        if not record:
            raise ExportError("Cookies 数据库缺少版本信息。")
        version = int(record[0])
        rows = con.execute(
            "SELECT host_key, name, path, expires_utc, encrypted_value, value "
            "FROM cookies WHERE host_key IN (?, ?) ORDER BY name",
            (".doubao.com", "doubao.com"),
        ).fetchall()
    except (sqlite3.Error, ValueError, TypeError):
        raise ExportError("无法读取 Cookies 数据库。请完全退出豆包（包括托盘进程）后重试。") from None
    finally:
        if con is not None:
            con.close()
    key = None
    values: dict[str, str] = {}
    for host, name, path, expiry, encrypted, value in rows:
        # 仅使用两个语音端点均适用的共享域 Cookie，避免混入其他站点及路径。
        if host != ".doubao.com" or path != "/" or name.startswith(("LARK", "feishu")):
            continue
        if expiry and expiry / 1_000_000 - CHROMIUM_EPOCH <= now:
            continue
        if encrypted:
            if bytes(encrypted).startswith(b"v20"):
                raise ExportError("检测到 v20 App-Bound 加密，本脚本不支持。")
            if key is None and bytes(encrypted)[:3] in (b"v10", b"v11"):
                key = load_key(user_data)
            value = decrypt_value(bytes(encrypted), key or b"", host, version)
        if not value:
            continue
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) or any(
            ord(c) < 32 or ord(c) > 126 or c == ";" for c in value
        ):
            raise ExportError("Cookie 包含不适合请求头的字符，未导出。")
        if name in values and values[name] != value:
            raise ExportError("发现有冲突的同名 Cookie，未导出。")
        values[name] = value
    if not any(values.get(name) for name in ("sessionid", "sessionid_ss", "sid_tt")):
        raise ExportError("未找到非空的登录会话 Cookie，请先在豆包 PC 客户端登录。")
    return "; ".join(f"{name}={value}" for name, value in values.items()), len(values)


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise ExportError("现有配置无法解析，原文件未修改。") from None
    return validate_config(config)


def validate_config(config: dict) -> dict:
    """校验磁盘或导入配置，错误信息不包含输入内容。"""
    if not isinstance(config, dict) or set(config) - FIELDS:
        raise ExportError("现有配置的字段不符合 Auth 格式，原文件未修改。")
    if any(not isinstance(value, str) for key, value in config.items() if key != "overrides"):
        raise ExportError("现有配置字段必须为字符串，overrides 必须为对象。")
    if not isinstance(config.get("overrides", {}), dict):
        raise ExportError("现有配置的 overrides 必须为对象。")
    return config


def make_config(existing: dict, cookie: str, web_id: str = "", tea_uuid: str = "",
                request_url: str = "") -> dict:
    config = {"cookie": "", "web_id": "", "tea_uuid": "", "language": "zh",
              "region": "cn", "proxy": "", "access_key": "", "overrides": {}}
    config.update(existing)
    config["overrides"] = dict(config["overrides"])
    if request_url:
        url = urlsplit(request_url)
        if (url.scheme != "wss" or url.netloc != "ws-samantha.doubao.com" or
                url.path not in ("/samantha/audio/asr", "/samantha/audio/tts")):
            raise ExportError("--request-url 必须是实际的豆包 ASR/TTS WebSocket 地址。")
        params = parse_qs(url.query)
        if any(len(value) != 1 for value in params.values()):
            raise ExportError("请求 URL 含重复参数，无法确定实际值。")
        for field in ("web_id", "tea_uuid"):
            if params.get(field):
                config[field] = params[field][0]
        # 只采纳已知客户端参数；不保存 URL 中可能存在的其他令牌。
        config["overrides"].update({key: val[0] for key, val in params.items() if key in PARAMS})
    config["web_id"] = web_id or config["web_id"]
    config["tea_uuid"] = tea_uuid or config["tea_uuid"]
    if not all(isinstance(config[key], str) and config[key].strip() and
               not any(ord(c) < 32 for c in config[key]) for key in ("web_id", "tea_uuid")):
        raise ExportError("缺少 web_id / tea_uuid：请保留原 auth.json，或提供同一会话的 --request-url，"
                          "也可使用 --web-id 和 --tea-uuid。Cookie 数据库不能保证包含这些参数。")
    config["cookie"] = cookie
    return config


def save_config(path: Path, config: dict) -> None:
    if path.is_symlink():
        raise ExportError("输出路径是符号链接，请指定普通文件。")
    if not path.parent.is_dir():
        raise ExportError("输出目录不存在，请先创建目录。")
    name = None
    try:
        # 同目录临时文件 + replace；失败时保留原配置，不生成额外明文备份。
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".auth-export-", suffix=".tmp", delete=False) as out:
            name = out.name
            os.chmod(name, 0o600)
            json.dump(config, out, ensure_ascii=False, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    except OSError:
        raise ExportError("无法保存配置；请检查文件权限、只读挂载或占用情况。") from None
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


class RedactedArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "参数错误：请使用 --help 检查选项名称及必填值；输入内容已隐藏。\n")


def main(argv: list[str] | None = None) -> int:
    parser = RedactedArgumentParser(description=__doc__)
    parser.add_argument("--user-data-dir", type=Path, help="豆包 User Data 目录（不是 Default 子目录）")
    parser.add_argument("--profile", default="Default", help="客户端 profile 目录名，默认 Default")
    parser.add_argument("--output", type=Path, default=ROOT / "auth.json", help="输出路径，默认项目根 auth.json")
    parser.add_argument("--base-config", type=Path, help="沿用会话参数的配置，默认读取输出文件")
    parser.add_argument("--web-id", default="", help="本人实际语音请求的 web_id")
    parser.add_argument("--tea-uuid", default="", help="本人实际语音请求的 tea_uuid")
    parser.add_argument("--request-url", default="", help="本人实际语音 WS 请求 URL，用于取得配套参数")
    parser.add_argument("--check", action="store_true", help="只在内存中检查，不写文件、不联网")
    args = parser.parse_args(argv)
    try:
        if sys.platform != "win32":
            raise ExportError("本机提取仅支持 Windows；导出的配置可供其他系统使用。")
        user_data = args.user_data_dir
        if user_data is None:
            local = os.environ.get("LOCALAPPDATA")
            if not local:
                raise ExportError("找不到 LOCALAPPDATA，请使用 --user-data-dir。")
            user_data = Path(local) / "Doubao" / "User Data"
        existing = load_config(args.base_config or args.output)
        # 先检查设备参数，避免缺少配置时无意义地解密本地 Cookie。
        config = make_config(existing, "", args.web_id, args.tea_uuid, args.request_url)
        config["cookie"], count = collect_cookies(user_data, args.profile)
        if args.check:
            print(f"本地检查通过：读取 {count} 个共享域 Cookie，配置字段完整；未写入文件、未联网。")
        else:
            save_config(args.output, config)
            print(f"已保存 {count} 个共享域 Cookie 到：{args.output.absolute()}")
            print("会话参数已保留；凭据不在终端显示。重启服务后加载新配置。")
            print("这是本地提取结果，尚未验证服务器是否接受该会话。")
        return 0
    except ExportError as error:
        print(f"导出失败：{error}", file=sys.stderr)
        return 1
    except Exception:
        # 不回显包含密文、解密明文或配置内容的第三方异常。
        print("导出失败：遇到未支持的数据格式或本地读取错误，原配置未修改。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
