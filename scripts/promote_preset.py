#!/usr/bin/env python3
"""ユーザー投稿プリセットを公式プリセットに昇格させる GUI ツール。

使い方:
    python scripts/promote_preset.py
"""

import json
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent
_PRESETS_PATH = _BASE_DIR / "data" / "presets.json"
_USER_PRESETS_PATH = _BASE_DIR / "data" / "user_presets.json"


def load_presets() -> dict:
    with open(_PRESETS_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_presets(presets: dict) -> None:
    with open(_PRESETS_PATH, "w", encoding="utf-8") as f:
        json.dump(presets, f, ensure_ascii=False, indent=2)


def load_user_presets() -> dict:
    if not _USER_PRESETS_PATH.exists():
        return {}
    with open(_USER_PRESETS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("presets", {})


def save_user_presets(presets: dict) -> None:
    with open(_USER_PRESETS_PATH, "w", encoding="utf-8") as f:
        json.dump({"presets": presets}, f, ensure_ascii=False, indent=2)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("プリセット管理")
        self.geometry("750x500")
        self.configure(padx=12, pady=12)

        # --- 上部: 一覧 ---
        list_frame = ttk.LabelFrame(self, text="ユーザー投稿プリセット")
        list_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("name", "costumes", "approved", "submitted")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=10)
        self.tree.heading("name", text="生徒名")
        self.tree.heading("costumes", text="衣装")
        self.tree.heading("approved", text="状態")
        self.tree.heading("submitted", text="投稿日時")
        self.tree.column("name", width=100)
        self.tree.column("costumes", width=280)
        self.tree.column("approved", width=70, anchor=tk.CENTER)
        self.tree.column("submitted", width=170)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # --- 下部: 操作 ---
        action_frame = ttk.Frame(self)
        action_frame.pack(fill=tk.X, pady=(12, 0))

        ttk.Label(action_frame, text="登録名:").pack(side=tk.LEFT)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(action_frame, textvariable=self.name_var, width=20)
        self.name_entry.pack(side=tk.LEFT, padx=(4, 12))

        self.promote_btn = ttk.Button(
            action_frame, text="公式に昇格", command=self._promote
        )
        self.promote_btn.pack(side=tk.LEFT, padx=4)

        self.approve_btn = ttk.Button(
            action_frame, text="承認", command=self._approve
        )
        self.approve_btn.pack(side=tk.LEFT, padx=4)

        self.delete_btn = ttk.Button(
            action_frame, text="削除", command=self._delete
        )
        self.delete_btn.pack(side=tk.LEFT, padx=4)

        ttk.Button(action_frame, text="更新", command=self._refresh).pack(
            side=tk.RIGHT, padx=4
        )

        self._set_buttons_state(False)
        self._refresh()

    def _refresh(self):
        self.user_presets = load_user_presets()
        self.tree.delete(*self.tree.get_children())
        for key, entry in self.user_presets.items():
            name = entry["character_name"]
            costumes = ", ".join(c["costume_name"] for c in entry["costumes"])
            status = "承認済" if entry.get("approved") else "未承認"
            submitted = entry.get("submitted_at", "")
            self.tree.insert("", tk.END, iid=key, values=(name, costumes, status, submitted))
        self._set_buttons_state(False)

    def _on_select(self, _event):
        sel = self.tree.selection()
        if sel:
            key = sel[0]
            entry = self.user_presets.get(key, {})
            self.name_var.set(entry.get("character_name", ""))
            self._set_buttons_state(True)
        else:
            self._set_buttons_state(False)

    def _set_buttons_state(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.promote_btn.configure(state=state)
        self.approve_btn.configure(state=state)
        self.delete_btn.configure(state=state)

    def _selected_key(self) -> str | None:
        sel = self.tree.selection()
        return sel[0] if sel else None

    def _promote(self):
        key = self._selected_key()
        if not key:
            return
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("エラー", "登録名を入力してください。")
            return
        presets = load_presets()
        if name in presets:
            if not messagebox.askyesno("確認", f"「{name}」は既に存在します。上書きしますか？"):
                return
        entry = self.user_presets[key]
        presets[name] = entry["costumes"]
        save_presets(presets)
        del self.user_presets[key]
        save_user_presets(self.user_presets)
        messagebox.showinfo("完了", f"「{name}」を公式プリセットに登録しました。")
        self._refresh()

    def _approve(self):
        key = self._selected_key()
        if not key:
            return
        self.user_presets[key]["approved"] = True
        save_user_presets(self.user_presets)
        self._refresh()

    def _delete(self):
        key = self._selected_key()
        if not key:
            return
        name = self.user_presets[key]["character_name"]
        if not messagebox.askyesno("確認", f"「{name}」を削除しますか？"):
            return
        del self.user_presets[key]
        save_user_presets(self.user_presets)
        self._refresh()


if __name__ == "__main__":
    App().mainloop()
