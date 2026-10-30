"""豆包登录态工具：本地读取与导出，按需应用到本机语音工作室。"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk
import urllib.request
from urllib.parse import urlsplit
import webbrowser

# 隔离模式下显式加载相邻模块；打包时由 PyInstaller 收集。
if getattr(sys, "frozen", False):
    import export_auth as exporter
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("export_auth", APP_DIR / "export_auth.py")
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)


def acquire(user_data: str, profile: str, base_path: str, request_url: str) -> dict:
    """工作线程只处理数据，绝不操作窗口或写配置。"""
    existing = exporter.load_config(Path(base_path)) if base_path.strip() else {}
    cookie, count = exporter.collect_cookies(Path(user_data), profile)
    try:
        config = exporter.make_config(existing, cookie, request_url=request_url.strip())
    except exporter.ExportError as error:
        return {"cookie": cookie, "count": count, "config": None, "warning": str(error)}
    return {"cookie": cookie, "count": count, "config": config, "warning": ""}


def studio_address(value: str) -> str:
    url = urlsplit(value.strip())
    if (url.scheme != 'http' or url.hostname not in {'localhost', '127.0.0.1', '::1'}
            or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment):
        raise exporter.ExportError('请填写本机工作室地址，例如 http://127.0.0.1:8000。')
    try:
        url.port
    except ValueError:
        raise exporter.ExportError('工作室端口无效。') from None
    return 'http://' + url.netloc


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def apply_to_studio(config: dict, address: str) -> None:
    address = studio_address(address)
    request = urllib.request.Request(address + '/api/auth/import',
        data=json.dumps({'config': config}).encode('utf-8'), method='POST',
        headers={'Content-Type': 'application/json', 'X-Doubao-Local': '1'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=25) as response:
            result = json.loads(response.read(65536))
        if result.get('auth_ok') is not True:
            raise ValueError()
    except Exception:
        raise exporter.ExportError('应用未确认完成，请打开工作室刷新状态；确认地址、服务连接与配置后重试。') from None


class AuthWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("豆包登录态工具 · Voice Studio")
        self.root.geometry("1040x760")
        self.root.minsize(920, 700)
        self.root.configure(background="#f6f7f2")
        self.events = queue.Queue()
        self.result = None
        self.busy = False
        self.closed = False
        self.timer = None
        self.status = tk.StringVar(value="准备就绪。先登录豆包，再完全退出客户端，即可获取。")
        self.result_label = tk.StringVar(value="等待获取")
        self.studio_url = tk.StringVar(value="http://127.0.0.1:8000")
        self.user_data = tk.StringVar(value=str(Path(os.environ.get("LOCALAPPDATA", "")) / "Doubao" / "User Data"))
        self.profile = tk.StringVar(value="Default")
        default_config = APP_DIR / "auth.json"
        # EXE 放在项目 dist 子目录时允许找到项目现有配置，但不把它打包进去。
        if not default_config.is_file() and APP_DIR.name == "dist":
            default_config = APP_DIR.parent / "auth.json"
        if not default_config.is_file() and APP_DIR.parent.name == 'dist':
            default_config = APP_DIR.parent.parent / 'auth.json'
        self.base_path = tk.StringVar(value=str(default_config) if default_config.is_file() else "")
        self.request_url = tk.StringVar()
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f6f7f2")
        style.configure("Card.TFrame", background="white")
        style.configure("TLabel", background="#f6f7f2", foreground="#27332f", font=("Microsoft YaHei UI", 10))
        style.configure("Card.TLabel", background="white")
        style.configure("Hint.TLabel", background="white", foreground="#64705e", font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 22, "bold"), foreground="#27332f")
        style.configure("Section.TLabel", background="white", font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(12, 9), background="#f3f5ef", borderwidth=0)
        style.map("TButton", background=[("active", "#e8ece3")])
        style.configure("TEntry", padding=8, fieldbackground="#fafbf8", bordercolor="#dde2d9")
        style.configure("Primary.TButton", background="#c94c27", foreground="white")
        style.map("Primary.TButton", background=[("active", "#a93c1c"), ("disabled", "#d9bcaf")])
        style.configure("Apply.TButton", background="#277968", foreground="white")
        style.map("Apply.TButton", background=[("active", "#1d5e50"), ("disabled", "#b5c9bd")])
        body = ttk.Frame(root, padding=24)
        body.pack(fill="both", expand=True)
        header = ttk.Frame(body)
        header.pack(fill="x", pady=(0, 22))
        tk.Label(header, text="豆", font=("Microsoft YaHei UI", 20, "bold"), background="#e5653d",
                 foreground="white", padx=12, pady=7).pack(side="left", padx=(0, 16))
        title = ttk.Frame(header)
        title.pack(side="left")
        ttk.Label(title, text="让连接，简单一点。", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title, text="豆包登录态工具  /  VOICE STUDIO", foreground="#64705e").pack(anchor="w", pady=(4, 0))
        content = ttk.Frame(body)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=4)
        content.columnconfigure(1, weight=6)
        content.rowconfigure(0, weight=1)
        settings = ttk.Frame(content, style="Card.TFrame", padding=20)
        settings.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        settings.columnconfigure(0, weight=1)
        ttk.Label(settings, text="01  读取来源", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self.inputs = []
        self.add_field(settings, 1, "豆包客户端目录", self.user_data, self.browse_directory)
        self.add_field(settings, 2, "沿用已有配置", self.base_path, self.browse_config)
        self.add_field(settings, 3, "客户端 Profile", self.profile)
        self.add_field(settings, 4, "语音请求 URL（首次配置时可选）", self.request_url)
        self.add_field(settings, 5, "本机工作室地址", self.studio_url)
        ttk.Label(settings, text="已有配置会保留设备参数与代理。获取时只读取当前 Windows 用户的数据。",
                  style="Hint.TLabel", wraplength=330).grid(row=12, column=0, columnspan=2, sticky="w", pady=(8, 16))
        self.get_button = ttk.Button(settings, text="获取登录态  →", command=self.start, style="Primary.TButton")
        self.get_button.grid(row=13, column=0, columnspan=2, sticky="ew")
        output = ttk.Frame(content, style="Card.TFrame", padding=20)
        output.grid(row=0, column=1, sticky="nsew")
        ttk.Label(output, text="02  登录态配置", style="Section.TLabel").pack(anchor="w")
        ttk.Label(output, textvariable=self.result_label, style="Hint.TLabel").pack(anchor="w", pady=(8, 16))
        display = ttk.Frame(output, style="Card.TFrame")
        display.pack(fill="both", expand=True)
        self.text = tk.Text(display, wrap="word", font=("Consolas", 10), background="#f6f8f3",
                            foreground="#27332f", relief="flat", padx=16, pady=16, state="disabled",
                            width=38, height=12, selectbackground="#d8eade", insertbackground="#277968")
        scroll = ttk.Scrollbar(display, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)
        actions = ttk.Frame(output, style="Card.TFrame")
        actions.pack(fill="x", pady=(16, 8))
        self.copy_button = ttk.Button(actions, text="复制完整配置", command=self.copy_config, state="disabled")
        self.copy_button.pack(side="left")
        self.cookie_button = ttk.Button(actions, text="复制 Cookie", command=self.copy_cookie, state="disabled")
        self.cookie_button.pack(side="left", padx=8)
        self.clear_button = ttk.Button(actions, text="清空", command=self.clear)
        self.clear_button.pack(side="right")
        export_actions = ttk.Frame(output, style="Card.TFrame")
        export_actions.pack(fill="x", pady=(0, 12))
        self.save_button = ttk.Button(export_actions, text="保存配置…", command=self.save, state="disabled")
        self.save_button.pack(side="left")
        self.apply_button = ttk.Button(export_actions, text="应用到工作室", style="Apply.TButton", command=self.apply, state="disabled")
        self.apply_button.pack(side="right")
        ttk.Button(output, text="打开本机工作室  ↗", command=self.open_studio).pack(fill="x")
        ttk.Label(body, textvariable=self.status, wraplength=960, foreground="#277968").pack(anchor="w", pady=(18, 8))
        ttk.Label(body, text="本地获取与复制不联网。选择“应用到工作室”后才验证会话，成功后生效；也可保存 JSON 用于其他部署。",
                  wraplength=960, foreground="#64705e", font=("Microsoft YaHei UI", 9)).pack(anchor="w")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.timer = self.root.after(100, self.poll)

    def add_field(self, parent, row, label, variable, browse=None):
        ttk.Label(parent, text=label, style="Hint.TLabel").grid(row=row * 2 - 1, column=0, columnspan=2, sticky="w", pady=(8, 4))
        entry = ttk.Entry(parent, textvariable=variable, show="•" if variable is self.request_url else "")
        entry.grid(row=row * 2, column=0, columnspan=1 if browse else 2, sticky="ew", pady=(0, 4))
        self.inputs.append(entry)
        if browse:
            button = ttk.Button(parent, text="选择", command=browse)
            button.grid(row=row * 2, column=1, padx=(8, 0), pady=(0, 4))
            self.inputs.append(button)

    def browse_directory(self):
        path = filedialog.askdirectory(title="选择豆包 User Data 目录", parent=self.root)
        if path:
            self.user_data.set(path)

    def browse_config(self):
        path = filedialog.askopenfilename(title="选择本人已有的 auth.json", parent=self.root,
                                         filetypes=[("JSON 配置", "*.json")])
        if path:
            self.base_path.set(path)

    def render(self, content):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.configure(state="disabled")

    def clear(self):
        self.result = None
        self.render("")
        self.copy_button.configure(state="disabled")
        self.cookie_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.apply_button.configure(state="disabled")
        self.result_label.set("等待获取 · 完整配置将显示在这里")
        self.status.set("已清空窗口内容。")

    def start(self):
        if self.busy:
            return
        self.clear()
        self.busy = True
        for widget in [self.get_button, self.clear_button, *self.inputs]:
            widget.configure(state="disabled")
        self.status.set("正在读取本机客户端，请稍候…")
        args = (self.user_data.get().strip(), self.profile.get().strip(),
                self.base_path.get().strip(), self.request_url.get().strip())
        threading.Thread(target=self.worker, args=args, daemon=True).start()

    def worker(self, *args):
        try:
            self.events.put(("result", acquire(*args)))
        except exporter.ExportError as error:
            self.events.put(("error", str(error)))
        except Exception:
            self.events.put(("error", "本地读取失败：客户端格式可能不受支持，请确认目录与配置；未修改任何文件。"))

    def save(self):
        if not self.result or self.result['config'] is None or self.busy:
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="保存登录态配置", defaultextension='.json',
                                           initialfile='auth.json', filetypes=[('JSON 配置', '*.json')])
        if path:
            try:
                exporter.save_config(Path(path), self.result['config'])
                self.status.set("配置已保存。可在工作室的“登录态管理”中导入。")
            except Exception:
                self.status.set("保存未完成，请检查文件权限与目标目录。")

    def apply(self):
        if not self.result or self.result['config'] is None or self.busy:
            return
        try:
            address = studio_address(self.studio_url.get())
        except exporter.ExportError as error:
            self.status.set(str(error))
            return
        self.busy = True
        for widget in [self.get_button, self.clear_button, self.apply_button, self.save_button, *self.inputs]:
            widget.configure(state='disabled')
        self.status.set("正在验证并应用到本机工作室…")
        threading.Thread(target=self.apply_worker, args=(self.result['config'], address), daemon=True).start()

    def apply_worker(self, config, address):
        try:
            apply_to_studio(config, address)
            self.events.put(('applied', None))
        except exporter.ExportError as error:
            self.events.put(('error', str(error)))
        except Exception:
            self.events.put(('error', '应用未完成，请打开工作室检查连接状态。'))

    def open_studio(self):
        try:
            webbrowser.open(studio_address(self.studio_url.get()) + '/#account')
        except (exporter.ExportError, webbrowser.Error):
            self.status.set('请检查本机工作室地址，并在浏览器中打开。')

    def poll(self):
        if self.closed:
            return
        try:
            kind, payload = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            for widget in [self.get_button, self.clear_button, *self.inputs]:
                widget.configure(state="normal")
            if self.result and self.result['config'] is not None:
                self.save_button.configure(state="normal")
                self.apply_button.configure(state="normal")
            if kind == "error":
                self.status.set("操作未完成：" + payload)
            elif kind == 'applied':
                self.status.set('登录态已验证并应用，无需重启工作室。')
            else:
                self.result = payload
                self.cookie_button.configure(state="normal")
                if payload["config"] is not None:
                    self.copy_button.configure(state="normal")
                    self.save_button.configure(state="normal")
                    self.apply_button.configure(state="normal")
                    self.render(json.dumps(payload["config"], ensure_ascii=False, indent=2))
                    self.result_label.set(f"已获取 {payload['count']} 个 Cookie · 可复制、保存或应用")
                    self.status.set('获取完成。选择复制、保存，或应用到本机工作室。')
                else:
                    self.result_label.set(f"已获取 {payload['count']} 个 Cookie · 待补充会话参数")
                    self.render(payload["cookie"])
                    self.status.set("Cookie 已获取；完整配置尚不可用。" + payload["warning"])
        self.timer = self.root.after(100, self.poll)

    def copy(self, value, label):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(value)
            self.status.set(label + "已复制，可粘贴到其他程序。")
        except tk.TclError:
            self.status.set("剪贴板暂时不可用，请在结果区选择并手动复制。")

    def copy_config(self):
        if self.result and self.result["config"] is not None:
            self.copy(json.dumps(self.result["config"], ensure_ascii=False, indent=2), "完整配置")

    def copy_cookie(self):
        if self.result:
            self.copy(self.result["cookie"], "Cookie")

    def close(self):
        self.closed = True
        if self.timer is not None:
            self.root.after_cancel(self.timer)
        self.result = None
        self.root.destroy()


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    AuthWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
