import json
import os
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except Exception:
    DND_AVAILABLE = False

APP_DIR = Path(__file__).resolve().parent
PRESETS_FILE = APP_DIR / "presets.json"


def load_presets():
    if not PRESETS_FILE.exists():
        raise FileNotFoundError(f"Не найден файл presets.json рядом со скриптом:\n{PRESETS_FILE}")
    with open(PRESETS_FILE, "r", encoding="utf-8") as f:
        presets = json.load(f)
    if not isinstance(presets, dict) or not presets:
        raise ValueError("presets.json пустой или имеет неверный формат")
    return presets


def detect_separator_and_encoding(file_path: Path):
    encodings = ["utf-8-sig", "utf-8", "cp1251"]
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc) as f:
                sample = f.read(4096)
            break
        except UnicodeDecodeError:
            continue
    else:
        enc = "utf-8-sig"
        with open(file_path, "r", encoding=enc, errors="ignore") as f:
            sample = f.read(4096)

    first_line = sample.splitlines()[0] if sample.splitlines() else ""
    candidates = [";", ",", "\t"]
    sep = max(candidates, key=lambda s: first_line.count(s))
    if first_line.count(sep) == 0:
        sep = ";"
    return sep, enc


def process_file(input_path, preset_name, presets):
    input_path = Path(input_path)
    sep, encoding = detect_separator_and_encoding(input_path)

    df = pd.read_csv(input_path, sep=sep, encoding=encoding, dtype=str, keep_default_na=False)

    preset = presets[preset_name]
    columns_to_delete = preset.get("delete_columns", [])
    if not isinstance(columns_to_delete, list):
        raise ValueError(f"В пресете {preset_name} delete_columns должен быть списком")

    existing_to_delete = [col for col in columns_to_delete if col in df.columns]
    missing_columns = [col for col in columns_to_delete if col not in df.columns]
    df_clean = df.drop(columns=existing_to_delete)

    output_csv = input_path.with_name(input_path.stem + f"_{preset_name}_clean.csv")
    output_xlsx = input_path.with_name(input_path.stem + f"_{preset_name}_clean.xlsx")

    df_clean.to_csv(output_csv, sep=sep, index=False, encoding="utf-8-sig")

    with pd.ExcelWriter(output_xlsx, engine="openpyxl") as writer:
        df_clean.to_excel(writer, index=False, sheet_name="Выгрузка")
        sheet = writer.sheets["Выгрузка"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions

        for column_cells in sheet.columns:
            column_letter = column_cells[0].column_letter
            max_length = 0
            for cell in column_cells:
                value = "" if cell.value is None else str(cell.value)
                max_length = max(max_length, len(value))
            sheet.column_dimensions[column_letter].width = min(max_length + 2, 70)

    return {
        "output_csv": output_csv,
        "output_xlsx": output_xlsx,
        "deleted": existing_to_delete,
        "missing": missing_columns,
        "rows_before": len(df),
        "cols_before": len(df.columns),
        "cols_after": len(df_clean.columns),
        "sep": sep,
        "encoding": encoding,
    }


class CsvCleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CSV Cleaner с пресетами")
        self.root.geometry("780x520")
        self.root.minsize(720, 480)

        self.presets = load_presets()
        self.file_path = None
        self.last_xlsx = None
        self.last_csv = None

        self.build_ui()

    def build_ui(self):
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(outer, text="CSV Cleaner", font=("Segoe UI", 16, "bold"))
        title.pack(anchor="w")

        self.drop_frame = tk.Frame(outer, bg="#f3f3f3", bd=1, relief="solid", height=95)
        self.drop_frame.pack(fill="x", pady=(10, 8))
        self.drop_frame.pack_propagate(False)

        drop_text = "Перетащи CSV-файл сюда" if DND_AVAILABLE else "Выбери CSV-файл кнопкой ниже"
        self.drop_label = tk.Label(
            self.drop_frame,
            text=drop_text,
            bg="#f3f3f3",
            fg="#333",
            font=("Segoe UI", 12),
        )
        self.drop_label.pack(expand=True)

        if DND_AVAILABLE:
            self.drop_frame.drop_target_register(DND_FILES)
            self.drop_frame.dnd_bind("<<Drop>>", self.on_drop)
            self.drop_label.drop_target_register(DND_FILES)
            self.drop_label.dnd_bind("<<Drop>>", self.on_drop)

        row_file = ttk.Frame(outer)
        row_file.pack(fill="x", pady=4)

        ttk.Button(row_file, text="Выбрать файл", command=self.choose_file).pack(side="left")
        self.file_label = ttk.Label(row_file, text="Файл не выбран")
        self.file_label.pack(side="left", padx=10, fill="x", expand=True)

        row_preset = ttk.Frame(outer)
        row_preset.pack(fill="x", pady=8)

        ttk.Label(row_preset, text="Пресет:").pack(side="left")
        self.preset_var = tk.StringVar()
        self.combo = ttk.Combobox(
            row_preset,
            textvariable=self.preset_var,
            values=list(self.presets.keys()),
            state="readonly",
            width=35,
        )
        self.combo.pack(side="left", padx=8)
        self.combo.bind("<<ComboboxSelected>>", lambda e: self.update_preset_info())
        self.combo.current(0)

        ttk.Button(row_preset, text="Обработать", command=self.run_processing).pack(side="left", padx=8)
        ttk.Button(row_preset, text="Открыть XLSX", command=self.open_last_xlsx).pack(side="left")

        self.preset_info = ttk.Label(outer, text="", foreground="#555")
        self.preset_info.pack(anchor="w", pady=(0, 6))
        self.update_preset_info()

        ttk.Label(outer, text="Лог:").pack(anchor="w")
        self.log = tk.Text(outer, height=14, wrap="word")
        self.log.pack(fill="both", expand=True)

        bottom = ttk.Label(
            outer,
            text="Пресеты редактируются в presets.json рядом со скриптом. Для drag&drop установи tkinterdnd2.",
            foreground="#666",
        )
        bottom.pack(anchor="w", pady=(8, 0))

    def update_preset_info(self):
        name = self.preset_var.get()
        preset = self.presets.get(name, {})
        desc = preset.get("description", "")
        cols = preset.get("delete_columns", [])
        self.preset_info.config(text=f"{desc} | удаляемых столбцов: {len(cols)}")

    def log_write(self, text):
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)

    def choose_file(self):
        path = filedialog.askopenfilename(
            title="Выберите CSV-файл",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.set_file(path)

    def on_drop(self, event):
        raw = event.data.strip()
        # tkinterdnd2 wraps paths with spaces in braces: {C:/path/file.csv}
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]
        # if several files dropped, take first
        if "} {" in event.data:
            raw = event.data.split("} {")[0].strip("{}")
        self.set_file(raw)

    def set_file(self, path):
        p = Path(path)
        if not p.exists():
            messagebox.showerror("Ошибка", f"Файл не найден:\n{path}")
            return
        self.file_path = str(p)
        self.file_label.config(text=str(p))
        self.drop_label.config(text=p.name)
        self.log_write(f"Выбран файл: {p}")

    def run_processing(self):
        if not self.file_path:
            messagebox.showwarning("Ошибка", "Сначала выберите CSV-файл")
            return
        preset_name = self.preset_var.get()
        if not preset_name:
            messagebox.showwarning("Ошибка", "Выберите пресет")
            return

        try:
            result = process_file(self.file_path, preset_name, self.presets)
            self.last_csv = result["output_csv"]
            self.last_xlsx = result["output_xlsx"]

            self.log_write("")
            self.log_write("Готово.")
            self.log_write(f"Кодировка: {result['encoding']} | разделитель: {repr(result['sep'])}")
            self.log_write(f"Строк: {result['rows_before']}")
            self.log_write(f"Столбцов было: {result['cols_before']} | стало: {result['cols_after']}")
            self.log_write(f"Удалено столбцов: {len(result['deleted'])}")
            if result["deleted"]:
                self.log_write("Удалены: " + ", ".join(result["deleted"]))
            if result["missing"]:
                self.log_write("Не найдены в CSV: " + ", ".join(result["missing"]))
            self.log_write(f"CSV: {result['output_csv']}")
            self.log_write(f"XLSX: {result['output_xlsx']}")
            messagebox.showinfo("Готово", "Файл обработан")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
            self.log_write("ОШИБКА: " + str(e))

    def open_last_xlsx(self):
        if not self.last_xlsx or not Path(self.last_xlsx).exists():
            messagebox.showwarning("Нет файла", "Сначала обработайте CSV")
            return
        try:
            os.startfile(self.last_xlsx)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))


def main():
    RootClass = TkinterDnD.Tk if DND_AVAILABLE else tk.Tk
    root = RootClass()
    try:
        app = CsvCleanerApp(root)
    except Exception as e:
        messagebox.showerror("Ошибка запуска", str(e))
        raise
    root.mainloop()


if __name__ == "__main__":
    main()
