# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from PIL import Image, ImageOps
except ImportError:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Не найден Pillow", "Установите библиотеку:\n\npip install pillow")
    raise SystemExit

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_AVAILABLE = True
except Exception:
    TkinterDnD = None
    DND_FILES = None
    DND_AVAILABLE = False

MM_TO_PT = 72.0 / 25.4


def human_size(n):
    x = float(n)
    for u in ("Б", "КБ", "МБ", "ГБ"):
        if x < 1024 or u == "ГБ":
            return f"{int(x)} {u}" if u == "Б" else f"{x:.1f} {u}"
        x /= 1024


def jpeg_direct_ok(path):
    with Image.open(path) as im:
        orientation = im.getexif().get(274, 1)
        return (
            (im.format or "").upper() == "JPEG"
            and im.mode in ("RGB", "L")
            and orientation in (None, 1)
        )


def normalize_to_jpeg(src_path):
    im = Image.open(src_path)
    im = ImageOps.exif_transpose(im)

    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, "white")
        bg.paste(rgba, mask=rgba.getchannel("A"))
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")

    fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    im.save(tmp_path, "JPEG", quality=90, optimize=True, subsampling="4:2:0")
    im.close()
    return tmp_path


def write_jpeg_pdf(jpeg_path, pdf_path, page_w_mm, page_h_mm):
    with Image.open(jpeg_path) as im:
        w_px, h_px = im.size
        if im.mode == "RGB":
            colorspace = "/DeviceRGB"
        elif im.mode == "L":
            colorspace = "/DeviceGray"
        else:
            raise ValueError("JPEG должен быть RGB или Grayscale.")

    with open(jpeg_path, "rb") as f:
        jpeg_bytes = f.read()

    page_w_pt = page_w_mm * MM_TO_PT
    page_h_pt = page_h_mm * MM_TO_PT

    content = (
        f"q\n{page_w_pt:.4f} 0 0 {page_h_pt:.4f} 0 0 cm\n"
        f"/Im0 Do\nQ\n"
    ).encode("ascii")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 {page_w_pt:.4f} {page_h_pt:.4f}] "
            f"/Resources << /XObject << /Im0 4 0 R >> >> "
            f"/Contents 5 0 R >>"
        ).encode("ascii"),
        (
            f"<< /Type /XObject /Subtype /Image "
            f"/Width {w_px} /Height {h_px} "
            f"/ColorSpace {colorspace} /BitsPerComponent 8 "
            f"/Filter /DCTDecode /Length {len(jpeg_bytes)} >>\nstream\n"
        ).encode("ascii") + jpeg_bytes + b"\nendstream",
        (
            f"<< /Length {len(content)} >>\nstream\n".encode("ascii")
            + content + b"endstream"
        ),
    ]

    with open(pdf_path, "wb") as out:
        out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]

        for i, obj in enumerate(objects, 1):
            offsets.append(out.tell())
            out.write(f"{i} 0 obj\n".encode("ascii"))
            out.write(obj)
            out.write(b"\nendobj\n")

        xref_pos = out.tell()
        out.write(f"xref\n0 {len(objects)+1}\n".encode("ascii"))
        out.write(b"0000000000 65535 f \n")
        for off in offsets[1:]:
            out.write(f"{off:010d} 00000 n \n".encode("ascii"))

        out.write(
            (
                f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\n"
                f"startxref\n{xref_pos}\n%%EOF\n"
            ).encode("ascii")
        )


class App:
    def __init__(self):
        self.root = TkinterDnD.Tk() if DND_AVAILABLE else tk.Tk()
        self.root.title("JPEG → PDF 1:1")
        self.root.resizable(False, False)

        self.file_path = ""
        self.img_w = 0
        self.img_h = 0
        self._updating = False

        self.keep_ratio = tk.BooleanVar(value=True)
        self.width_var = tk.StringVar(value="1000")
        self.height_var = tk.StringVar(value="")
        self.file_var = tk.StringVar(value="Файл не выбран")
        self.info_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")

        self.build_ui()

        self.width_var.trace_add("write", lambda *_: self.dimension_changed("w"))
        self.height_var.trace_add("write", lambda *_: self.dimension_changed("h"))

        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            self.load_file(sys.argv[1])

    def build_ui(self):
        f = ttk.Frame(self.root, padding=12)
        f.grid()

        ttk.Label(f, text="JPEG / PNG / WebP → PDF заданного размера",
                  font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 8)
        )

        drop = ttk.Label(
            f,
            text="Перетащите изображение сюда\nили нажмите «Выбрать файл»",
            anchor="center",
            relief="groove",
            padding=(18, 18),
        )
        drop.grid(row=1, column=0, columnspan=4, sticky="ew")

        if DND_AVAILABLE:
            drop.drop_target_register(DND_FILES)
            drop.dnd_bind("<<Drop>>", self.on_drop)

        ttk.Button(f, text="Выбрать файл…", command=self.choose_file).grid(
            row=2, column=0, columnspan=4, sticky="ew", pady=(8, 5)
        )

        ttk.Label(f, textvariable=self.file_var, wraplength=500).grid(
            row=3, column=0, columnspan=4, sticky="w"
        )
        ttk.Label(f, textvariable=self.info_var).grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(2, 10)
        )

        ttk.Label(f, text="Ширина, мм:").grid(row=5, column=0, sticky="e")
        ttk.Entry(f, textvariable=self.width_var, width=12).grid(
            row=5, column=1, sticky="w", padx=(6, 18)
        )

        ttk.Label(f, text="Высота, мм:").grid(row=5, column=2, sticky="e")
        ttk.Entry(f, textvariable=self.height_var, width=12).grid(
            row=5, column=3, sticky="w", padx=(6, 0)
        )

        ttk.Checkbutton(
            f,
            text="Сохранять пропорции",
            variable=self.keep_ratio,
            command=self.ratio_toggled,
        ).grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 10))

        ttk.Button(f, text="Создать PDF", command=self.create_pdf).grid(
            row=7, column=0, columnspan=4, sticky="ew"
        )

        ttk.Label(f, textvariable=self.status_var, wraplength=500).grid(
            row=8, column=0, columnspan=4, sticky="w", pady=(8, 0)
        )

        hint = (
            "RGB/Grayscale JPEG встраивается без перекодирования — "
            "PDF обычно почти того же размера.\n"
            "Размер страницы задаётся в мм; DPI JPEG на физический размер PDF не влияет."
        )
        if not DND_AVAILABLE:
            hint += "\nDrag&Drop прямо в окно: pip install tkinterdnd2 (необязательно)."

        ttk.Label(f, text=hint, foreground="#555555", wraplength=520).grid(
            row=9, column=0, columnspan=4, sticky="w", pady=(10, 0)
        )

    def on_drop(self, event):
        paths = self.root.tk.splitlist(event.data)
        if paths:
            self.load_file(paths[0])

    def choose_file(self):
        path = filedialog.askopenfilename(
            title="Выберите изображение",
            filetypes=[
                ("Изображения", "*.jpg *.jpeg *.png *.webp"),
                ("JPEG", "*.jpg *.jpeg"),
                ("PNG", "*.png"),
                ("WebP", "*.webp"),
                ("Все файлы", "*.*"),
            ],
        )
        if path:
            self.load_file(path)

    def load_file(self, path):
        try:
            with Image.open(path) as im:
                self.img_w, self.img_h = im.size
                fmt = im.format or "?"
                dpi = im.info.get("dpi")

            self.file_path = path
            self.file_var.set(os.path.basename(path))

            dpi_text = ""
            if dpi and isinstance(dpi, tuple) and dpi[0]:
                dpi_text = f", DPI: {dpi[0]:.0f}"

            self.info_var.set(
                f"{self.img_w} × {self.img_h} px, {fmt}, "
                f"{human_size(os.path.getsize(path))}{dpi_text}"
            )

            if self.keep_ratio.get():
                try:
                    w = float(self.width_var.get().replace(",", "."))
                    self._updating = True
                    self.height_var.set(self.fmt(w * self.img_h / self.img_w))
                finally:
                    self._updating = False

            self.status_var.set("")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть изображение:\n{e}")

    @staticmethod
    def fmt(v):
        return f"{v:.2f}".rstrip("0").rstrip(".")

    def dimension_changed(self, source):
        if self._updating or not self.keep_ratio.get() or not self.img_w or not self.img_h:
            return
        try:
            self._updating = True
            if source == "w":
                t = self.width_var.get().replace(",", ".").strip()
                if t:
                    w = float(t)
                    self.height_var.set(self.fmt(w * self.img_h / self.img_w))
            else:
                t = self.height_var.get().replace(",", ".").strip()
                if t:
                    h = float(t)
                    self.width_var.set(self.fmt(h * self.img_w / self.img_h))
        except ValueError:
            pass
        finally:
            self._updating = False

    def ratio_toggled(self):
        if self.keep_ratio.get() and self.img_w and self.img_h:
            self.dimension_changed("w")

    def create_pdf(self):
        if not self.file_path:
            messagebox.showwarning("Нет файла", "Сначала выберите изображение.")
            return

        try:
            w_mm = float(self.width_var.get().replace(",", "."))
            h_mm = float(self.height_var.get().replace(",", "."))
            if w_mm <= 0 or h_mm <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Размер", "Введите корректные ширину и высоту в мм.")
            return

        base, _ = os.path.splitext(self.file_path)
        default_pdf = base + " (просмотр).pdf"

        pdf_path = filedialog.asksaveasfilename(
            title="Сохранить PDF",
            initialdir=os.path.dirname(default_pdf),
            initialfile=os.path.basename(default_pdf),
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
        )
        if not pdf_path:
            return

        tmp = None
        try:
            direct = jpeg_direct_ok(self.file_path)
            source = self.file_path

            if not direct:
                self.status_var.set("Подготовка изображения…")
                self.root.update_idletasks()
                tmp = normalize_to_jpeg(self.file_path)
                source = tmp

            write_jpeg_pdf(source, pdf_path, w_mm, h_mm)

            src_size = os.path.getsize(self.file_path)
            pdf_size = os.path.getsize(pdf_path)
            mode = "JPEG встроен без перекодирования" if direct else "изображение преобразовано в JPEG"

            self.status_var.set(
                f"Готово: {w_mm:g} × {h_mm:g} мм • {human_size(pdf_size)} • {mode}"
            )
            messagebox.showinfo(
                "Готово",
                f"Размер страницы: {w_mm:g} × {h_mm:g} мм\n"
                f"Исходный файл: {human_size(src_size)}\n"
                f"PDF: {human_size(pdf_size)}\n\n{mode}."
            )
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать PDF:\n{e}")
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
