import ctypes
import json
import os
import subprocess
import sys
import time
import tkinter as tk
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk


APP_NAME = "IndieShelf"
POLL_INTERVAL_MS = 3000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def data_file():
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "IndieShelf" / "games.json"


def legacy_data_file():
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "SimpleGameLibrary" / "games.json"


def load_games(path=None):
    file_path = path or data_file()
    if path is None and not file_path.exists() and legacy_data_file().exists():
        games = load_games(legacy_data_file())
        save_games(games, file_path)
        return games
    if not file_path.exists():
        return []
    with file_path.open("r", encoding="utf-8") as stream:
        games = json.load(stream)
    if not isinstance(games, list):
        raise ValueError("The saved library data is not a list.")
    return games


def save_games(games, path=None):
    file_path = path or data_file()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = file_path.with_suffix(".tmp")
    with temporary_path.open("w", encoding="utf-8") as stream:
        persisted_games = [
            {key: value for key, value in game.items() if not key.startswith("_")}
            for game in games
        ]
        json.dump(persisted_games, stream, indent=2)
    temporary_path.replace(file_path)


def running_executable_paths():
    if sys.platform != "win32":
        return set()

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    snapshot = kernel32.CreateToolhelp32Snapshot
    snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    snapshot.restype = wintypes.HANDLE
    first = kernel32.Process32FirstW
    first.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    first.restype = wintypes.BOOL
    next_process = kernel32.Process32NextW
    next_process.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    next_process.restype = wintypes.BOOL
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    query_path = kernel32.QueryFullProcessImageNameW
    query_path.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    query_path.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    handle = snapshot(TH32CS_SNAPPROCESS, 0)
    if handle == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())

    paths = set()
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        found = first(handle, ctypes.byref(entry))
        while found:
            process = open_process(
                PROCESS_QUERY_LIMITED_INFORMATION, False, entry.th32ProcessID
            )
            if process:
                try:
                    buffer = ctypes.create_unicode_buffer(32768)
                    length = wintypes.DWORD(len(buffer))
                    if query_path(process, 0, buffer, ctypes.byref(length)):
                        paths.add(os.path.normcase(os.path.abspath(buffer.value)))
                finally:
                    close_handle(process)
            found = next_process(handle, ctypes.byref(entry))
    finally:
        close_handle(handle)
    return paths


def format_playtime(seconds):
    total_minutes = int(seconds // 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes:02d}m"


class GameLibrary:
    def __init__(self, root, games):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("820x500")
        self.root.minsize(640, 380)
        self.root.configure(bg="#111318")
        self.games = games
        for game in self.games:
            game["_was_running"] = False
        self.last_poll = time.monotonic()
        self.running_paths = set()
        self.resize_after_id = None

        self._configure_style()
        self._build_ui()
        self.root.bind("<Configure>", self.on_resize)
        self.refresh_processes()
        self.refresh_table()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(POLL_INTERVAL_MS, self.poll)

    def _configure_style(self):
        style = ttk.Style()
        self.style = style
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background="#191c23",
            foreground="#e7e9ee",
            fieldbackground="#191c23",
            rowheight=34,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background="#20242d",
            foreground="#b8c0ce",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", "#303d59")],
            foreground=[("selected", "#ffffff")],
        )

    def _build_ui(self):
        header = tk.Frame(self.root, bg="#111318")
        header.pack(fill="x", padx=22, pady=(20, 14))
        title_group = tk.Frame(header, bg="#111318")
        title_group.pack(side="left", anchor="w")
        self.title_label = tk.Label(
            title_group,
            text="Your indie games",
            bg="#111318",
            fg="#f3f4f6",
            font=("Segoe UI", 20, "bold"),
        )
        self.title_label.pack(anchor="w")
        self.subtitle_label = tk.Label(
            title_group,
            text="A simple library that tracks time while your games are running.",
            bg="#111318",
            fg="#9ba3b4",
            font=("Segoe UI", 10),
        )
        self.subtitle_label.pack(anchor="w", pady=(3, 0))
        self.add_button = tk.Button(
            header,
            text="+ Add game",
            command=self.add_game,
            bg="#5879cf",
            fg="white",
            activebackground="#6889df",
            activeforeground="white",
            relief="flat",
            padx=14,
            pady=9,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        self.add_button.pack(side="right", padx=(12, 0), pady=(2, 0))

        table_frame = tk.Frame(self.root, bg="#111318")
        self.table_frame = table_frame
        table_frame.pack(fill="both", expand=True, padx=22)
        columns = ("game", "status", "playtime", "last_played", "running")
        self.table = ttk.Treeview(
            table_frame, columns=columns, show="headings", selectmode="browse"
        )
        headings = {
            "game": ("Game", 220),
            "status": ("Status", 110),
            "playtime": ("Play time", 105),
            "last_played": ("Last played", 155),
            "running": ("Activity", 105),
        }
        self.column_names = tuple(headings)
        for column, (title, width) in headings.items():
            self.table.heading(column, text=title)
            self.table.column(column, width=width, minwidth=70, anchor="w")
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        scrollbar.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.bind("<Double-1>", self.launch_double_clicked)
        self.table.bind("<Return>", lambda _event: self.launch_game())

        footer = tk.Frame(self.root, bg="#111318")
        self.footer = footer
        footer.pack(fill="x", padx=22, pady=16)
        self.notice = tk.Label(
            footer,
            text="Double-click a game to launch it.",
            bg="#111318",
            fg="#9ba3b4",
            font=("Segoe UI", 9),
        )
        self.notice.pack(side="left", pady=8)
        self.action_buttons = []
        for label, command in (
            ("▶ Launch selected", self.launch_game),
            ("Set status", self.toggle_status),
            ("Remove", self.remove_game),
        ):
            button = tk.Button(
                footer,
                text=label,
                command=command,
                bg="#5879cf" if label.startswith("▶") else "#252a34",
                fg="white",
                activebackground="#6889df" if label.startswith("▶") else "#384153",
                activeforeground="white",
                relief="flat",
                padx=12,
                pady=8,
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
            )
            button.pack(side="right", padx=(7, 0))
            self.action_buttons.append(button)

    def on_resize(self, event):
        if event.widget is not self.root:
            return
        if self.resize_after_id is not None:
            self.root.after_cancel(self.resize_after_id)
        self.resize_after_id = self.root.after(90, self.apply_responsive_layout)

    def apply_responsive_layout(self):
        self.resize_after_id = None
        width = max(1, self.root.winfo_width())
        height = max(1, self.root.winfo_height())
        scale = min(1.2, max(0.85, min(width / 820, height / 500)))
        outer_padding = round(22 * scale)
        self.header.pack_configure(
            padx=outer_padding, pady=(round(20 * scale), round(14 * scale))
        )
        self.table_frame.pack_configure(padx=outer_padding)
        self.footer.pack_configure(padx=outer_padding, pady=round(16 * scale))
        self.title_label.configure(font=("Segoe UI", round(20 * scale), "bold"))
        self.subtitle_label.configure(font=("Segoe UI", max(8, round(10 * scale))))
        self.subtitle_label.pack_configure(pady=(round(3 * scale), 0))
        self.notice.configure(font=("Segoe UI", max(8, round(9 * scale))))
        self.notice.pack_configure(pady=round(8 * scale))
        self.add_button.configure(
            font=("Segoe UI", max(8, round(10 * scale)), "bold"),
            padx=round(14 * scale),
            pady=round(9 * scale),
        )
        self.add_button.pack_configure(
            padx=(round(12 * scale), 0), pady=(round(2 * scale), 0)
        )
        for button in self.action_buttons:
            button.configure(
                font=("Segoe UI", max(8, round(9 * scale)), "bold"),
                padx=round(12 * scale),
                pady=round(8 * scale),
            )
            button.pack_configure(padx=(round(7 * scale), 0))
        self.style.configure(
            "Treeview",
            rowheight=round(34 * scale),
            font=("Segoe UI", max(8, round(10 * scale))),
        )
        self.style.configure(
            "Treeview.Heading",
            font=("Segoe UI", max(8, round(9 * scale)), "bold"),
        )

        available_width = max(1, width - outer_padding * 2 - 18)
        ratios = (0.38, 0.15, 0.15, 0.20, 0.12)
        minimums = (150, 75, 80, 120, 75)
        scaled_minimums = tuple(round(minimum * scale) for minimum in minimums)
        extra_width = max(0, available_width - sum(scaled_minimums))
        for column, ratio, minimum in zip(
            self.column_names, ratios, scaled_minimums
        ):
            self.table.column(
                column,
                width=minimum + round(extra_width * ratio),
                minwidth=minimum,
            )

    def launch_double_clicked(self, event):
        row = self.table.identify_row(event.y)
        if row:
            self.table.selection_set(row)
            self.table.focus(row)
            self.launch_game()

    def refresh_table(self):
        selected = self.table.selection()
        selected_game = selected[0] if selected else None
        self.table.delete(*self.table.get_children())
        for game in self.games:
            path = os.path.normcase(os.path.abspath(game["path"]))
            is_running = path in self.running_paths
            last_played = game.get("last_played") or "Never"
            if last_played != "Never":
                try:
                    last_played = datetime.fromisoformat(last_played).strftime(
                        "%Y-%m-%d %H:%M"
                    )
                except ValueError:
                    pass
            self.table.insert(
                "",
                "end",
                iid=game["id"],
                values=(
                    game["name"],
                    game.get("status", "Playing"),
                    format_playtime(game.get("play_seconds", 0)),
                    last_played,
                    "Running" if is_running else "",
                ),
            )
        if selected_game in self.table.get_children():
            self.table.selection_set(selected_game)

    def refresh_processes(self):
        try:
            self.running_paths = running_executable_paths()
        except OSError as error:
            self.notice.configure(text=f"Could not check running games: {error}")
            self.running_paths = set()

    def poll(self):
        now = time.monotonic()
        elapsed = max(0, now - self.last_poll)
        self.last_poll = now
        self.refresh_processes()
        changed = False
        timestamp = datetime.now().isoformat(timespec="seconds")
        for game in self.games:
            path = os.path.normcase(os.path.abspath(game["path"]))
            if path in self.running_paths:
                game["play_seconds"] = game.get("play_seconds", 0) + elapsed
                if not game.get("_was_running"):
                    game["last_played"] = timestamp
                game["_was_running"] = True
                changed = True
            else:
                game["_was_running"] = False
        if changed:
            self._save()
        self.refresh_table()
        self.root.after(POLL_INTERVAL_MS, self.poll)

    def _save(self):
        try:
            save_games(self.games)
        except OSError as error:
            self.notice.configure(text=f"Could not save your library: {error}")

    def _selected_game(self):
        selection = self.table.selection()
        if not selection:
            messagebox.showinfo(APP_NAME, "Select a game first.", parent=self.root)
            return None
        game_id = selection[0]
        return next((game for game in self.games if game["id"] == game_id), None)

    def add_game(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Choose a game executable",
            filetypes=[("Windows applications", "*.exe"), ("All files", "*.*")],
        )
        if not path:
            return
        normalized_path = os.path.normcase(os.path.abspath(path))
        existing = next(
            (
                game
                for game in self.games
                if os.path.normcase(os.path.abspath(game["path"])) == normalized_path
            ),
            None,
        )
        if existing:
            messagebox.showinfo(APP_NAME, "That game is already in your library.")
            return
        default_name = Path(path).stem
        name = simpledialog.askstring(
            "Game name",
            "Name shown in your library:",
            initialvalue=default_name,
            parent=self.root,
        )
        if name is None:
            return
        game = {
            "id": f"game-{time.time_ns()}",
            "name": name.strip() or default_name,
            "path": os.path.abspath(path),
            "status": "Playing",
            "play_seconds": 0,
            "last_played": None,
            "_was_running": False,
        }
        self.games.append(game)
        self._save()
        self.refresh_table()

    def launch_game(self):
        game = self._selected_game()
        if not game:
            return
        if not Path(game["path"]).is_file():
            messagebox.showerror(
                APP_NAME,
                "The game executable could not be found.",
                parent=self.root,
            )
            return
        try:
            subprocess.Popen([game["path"]], cwd=str(Path(game["path"]).parent))
        except OSError as error:
            messagebox.showerror(
                APP_NAME,
                f"Could not launch the game:\n{error}",
                parent=self.root,
            )

    def toggle_status(self):
        game = self._selected_game()
        if not game:
            return
        game["status"] = "Finished" if game.get("status") == "Playing" else "Playing"
        self._save()
        self.refresh_table()

    def remove_game(self):
        game = self._selected_game()
        if not game:
            return
        if not messagebox.askyesno(
            APP_NAME, f"Remove {game['name']} from your library?", parent=self.root
        ):
            return
        self.games.remove(game)
        self._save()
        self.refresh_table()

    def close(self):
        self._save()
        self.root.destroy()


def main():
    if sys.platform != "win32":
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, "Game Library currently requires Windows.")
        root.destroy()
        return
    try:
        games = load_games()
    except (OSError, json.JSONDecodeError, ValueError) as error:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            APP_NAME,
            f"Could not load the saved game library:\n{error}\n\n"
            "You can repair or remove the data file at:\n"
            f"{data_file()}",
        )
        root.destroy()
        return

    root = tk.Tk()
    app = GameLibrary(root, games)
    root.mainloop()


if __name__ == "__main__":
    main()
