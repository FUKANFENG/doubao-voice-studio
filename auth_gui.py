"""豆包登录态桌面工具：本地获取、显示和复制，不请求上游。"""
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


class AuthWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("豆包登录态工具")
        self.root.geometry("900x730")
        self.root.minsize(700, 590)
        self.root.configure(background="#f3f5f8")
        self.events = queue.Queue()
        self.result = None
        self.busy = False
        self.closed = False
        self.timer = None
        self.status = tk.StringVar(value="准备就绪 · 点击获取，只读取本机豆包客户端。")
        self.user_data = tk.StringVar(value=str(Path(os.environ.get("LOCALAPPDATA", "")) / "Doubao" / "User Data"))
        self.profile = tk.StringVar(value="Default")
        default_config = APP_DIR / "auth.json"
        # EXE 放在项目 dist 子目录时允许找到项目现有配置，但不把它打包进去。
        if not default_config.is_file() and APP_DIR.name == "dist":
            default_config = APP_DIR.parent / "auth.json"
        self.base_path = tk.StringVar(value=str(default_config) if default_config.is_file() else "")
        self.request_url = tk.StringVar()
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f3f5f8")
        style.configure("TLabel", background="#f3f5f8", font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 21, "bold"), foreground="#17243b")
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(12, 8))
        style.configure("Primary.TButton", background="#2563eb", foreground="white")
        style.map("Primary.TButton", background=[("active", "#1d4ed8"), ("disabled", "#b6c5df")])
        body = ttk.Frame(root, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="豆包登录态工具", style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, text="获取本机登录态 → 复制配置 → 粘贴到其他程序", foreground="#59677d").pack(anchor="w", pady=(6, 18))
        settings = ttk.LabelFrame(body, text="读取来源", padding=12)
        settings.pack(fill="x")
        settings.columnconfigure(1, weight=1)
        self.inputs = []
        self.add_field(settings, 0, "客户端目录", self.user_data, self.browse_directory)
        self.add_field(settings, 1, "已有配置（可选）", self.base_path, self.browse_config)
        self.add_field(settings, 2, "Profile", self.profile)
        self.add_field(settings, 3, "语音请求 URL（可选）", self.request_url)
        ttk.Label(body, text="已有配置用于沿用 web_id / tea_uuid 等参数。首次缺少参数时，可粘贴本人实际语音请求 URL。",
                  wraplength=790, foreground="#59677d").pack(anchor="w", pady=(8, 12))
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(0, 10))
        self.get_button = ttk.Button(actions, text="获取登录态", command=self.start, style="Primary.TButton")
        self.get_button.pack(side="left")
        self.copy_button = ttk.Button(actions, text="复制完整配置", command=self.copy_config, state="disabled")
        self.copy_button.pack(side="left", padx=8)
        self.cookie_button = ttk.Button(actions, text="仅复制 Cookie", command=self.copy_cookie, state="disabled")
        self.cookie_button.pack(side="left")
        self.clear_button = ttk.Button(actions, text="清空显示", command=self.clear)
        self.clear_button.pack(side="right")
        ttk.Label(body, textvariable=self.status, wraplength=800, foreground="#2457a6").pack(anchor="w", pady=(0, 10))
        display = ttk.Frame(body)
        display.pack(fill="both", expand=True)
        self.text = tk.Text(display, wrap="word", font=("Consolas", 11), background="white",
                            foreground="#17243b", relief="flat", padx=14, pady=14, state="disabled")
        scroll = ttk.Scrollbar(display, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)
        ttk.Label(body, text="结果会显示明文，复制后可用于你的其他部署。工具不联网、不自动保存；若提示文件占用，请完全退出豆包后重试。",
                  wraplength=800, foreground="#59677d").pack(anchor="w", pady=(12, 0))
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.timer = self.root.after(100, self.poll)

    def add_field(self, parent, row, label, variable, browse=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=4)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        self.inputs.append(entry)
        if browse:
            button = ttk.Button(parent, text="选择…", command=browse)
            button.grid(row=row, column=2, padx=(8, 0), pady=4)
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
            if kind == "error":
                self.status.set("获取失败：" + payload)
            else:
                self.result = payload
                self.cookie_button.configure(state="normal")
                if payload["config"] is not None:
                    self.copy_button.configure(state="normal")
                    self.render(json.dumps(payload["config"], ensure_ascii=False, indent=2))
                    self.status.set(f"已获取 {payload['count']} 个 Cookie，配置可复制；尚未验证服务器端会话。")
                else:
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
