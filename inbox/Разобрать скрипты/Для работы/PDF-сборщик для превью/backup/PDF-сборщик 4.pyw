# -*- coding: utf-8 -*-
"""Пакетный PDF-сборщик на основе «JPEG в PDF без перекодирования.pyw».

Python 3.10+. Pillow и tkinterdnd2 устанавливаются автоматически при отсутствии.
JPEG RGB/L с ориентацией 1 сохраняется побайтно.
PNG RGB/Gray/Indexed без прозрачности, поворота и interlace: IDAT напрямую.
Прочие 8-битные PNG: без потерь на белом фоне, без JPEG-сжатия.
WebP и нестандартные JPEG: JPEG quality=90, 4:4:4, без уменьшения пикселей.
Анимированные файлы не принимаются. PDF записывается атомарно.
"""
import io
import math
import os
import queue
import re
import sys
import tempfile
import threading
import importlib
import subprocess
import site
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

def ensure_dependencies():
    required = {'PIL': 'Pillow', 'tkinterdnd2': 'tkinterdnd2'}
    missing = []
    for module, package in required.items():
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(package)
    if not missing:
        return
    window = tk.Tk()
    window.title('Подготовка PDF-сборщика')
    window.resizable(False, False)
    ttk.Label(window, text='Устанавливаются необходимые библиотеки:\n' + ', '.join(missing)
              + '\n\nНужен интернет. Подождите…', padding=24).pack()
    window.protocol('WM_DELETE_WINDOW', lambda: None)
    result = queue.Queue()

    def install():
        try:
            options = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, errors='replace', timeout=300)
            if os.name == 'nt':
                options['creationflags'] = subprocess.CREATE_NO_WINDOW
            def run(args):
                completed = subprocess.run([sys.executable, '-m', *args], **options)
                if completed.returncode:
                    raise RuntimeError(completed.stdout[-3000:])
            try:
                run(['pip', '--version'])
            except RuntimeError:
                run(['ensurepip', '--upgrade'])
            # A virtual environment gets its own packages; otherwise use user site.
            user = ['--user'] if sys.prefix == sys.base_prefix else []
            run(['pip', 'install', '--disable-pip-version-check', *user, *missing])
            if user:
                site.addsitedir(site.getusersitepackages())
            importlib.invalidate_caches()
            for module in required:
                importlib.import_module(module)
            result.put(None)
        except Exception as exc:
            result.put(str(exc))

    error = []
    def poll():
        try:
            error.append(result.get_nowait())
            window.quit()
        except queue.Empty:
            window.after(100, poll)
    threading.Thread(target=install, daemon=True).start()
    window.after(100, poll)
    window.mainloop()
    if error[0] is not None:
        messagebox.showerror('Не удалось установить библиотеки',
            'Проверьте интернет и права установки, затем запустите программу снова.\n\n'
            + error[0], parent=window)
    window.destroy()
    if error[0] is not None:
        raise SystemExit(1)


ensure_dependencies()
from PIL import Image, ImageOps

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
except ImportError:
    TkinterDnD = None

MM_TO_PT = 72.0 / 25.4


def positive(value):
    value = float(str(value).strip().replace(',', '.'))
    if not math.isfinite(value) or value <= 0:
        raise ValueError('Размер должен быть положительным конечным числом.')
    return value


def fmt(value):
    return f'{value:.4f}'.rstrip('0').rstrip('.')


def metadata_dpi(im):
    """EXIF (включая сантиметры), затем DPI Pillow; отдельно по двум осям."""
    exif = im.getexif()
    unit = exif.get(296, 2)
    sources = []
    if unit in (2, 3):
        factor = 2.54 if unit == 3 else 1.0
        try:
            sources.append((float(exif[282]) * factor, float(exif[283]) * factor))
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            pass
    sources.append(im.info.get('dpi'))
    for source in sources:
        try:
            x, y = source if isinstance(source, (tuple, list)) else (source, source)
            return positive(x), positive(y), False
        except (TypeError, ValueError, OverflowError):
            pass
    return 150.0, 150.0, True


@dataclass
class Page:
    path: Path
    pixels: tuple
    dpi: tuple
    fallback: bool
    original: tuple
    width: float
    height: float
    keep_ratio: bool = True

    @classmethod
    def read(cls, path):
        path = Path(path).resolve()
        with Image.open(path) as im:
            if im.format not in ('JPEG', 'PNG', 'WEBP'):
                raise ValueError('Поддерживаются только JPEG, PNG и WebP.')
            if getattr(im, 'n_frames', 1) != 1:
                raise ValueError('Анимация не поддерживается. Сохраните нужный кадр отдельно.')
            w, h = im.size
            dx, dy, fallback = metadata_dpi(im)
            if im.getexif().get(274, 1) in (5, 6, 7, 8):
                w, h, dx, dy = h, w, dy, dx
        # PNG EXIF access may load the image; verify needs a freshly opened file.
        with Image.open(path) as check:
            check.verify()
        # Round metadata-derived sizes only; manual decimal input stays exact.
        size = (max(1, math.floor(w / dx * 25.4 + 0.5)),
                max(1, math.floor(h / dy * 25.4 + 0.5)))
        return cls(path, (w, h), (dx, dy), fallback, size, *size)


def jpeg_direct_ok(im):
    return im.format == 'JPEG' and im.mode in ('RGB', 'L') and im.getexif().get(274, 1) in (None, 1)


def jpeg_data(page):
    with Image.open(page.path) as im:
        if jpeg_direct_ok(im):
            return page.path.read_bytes(), im.size, '/DeviceGray' if im.mode == 'L' else '/DeviceRGB'
        im = ImageOps.exif_transpose(im)
        if im.mode in ('RGBA', 'LA') or 'transparency' in im.info:
            rgba = im.convert('RGBA')
            converted = Image.new('RGB', rgba.size, 'white')
            converted.paste(rgba, mask=rgba.getchannel('A'))
        else:
            converted = im.convert('RGB')
        buffer = io.BytesIO()
        converted.save(buffer, 'JPEG', quality=90, optimize=True, subsampling=0)
        return buffer.getvalue(), converted.size, '/DeviceRGB'


def png_stream(raw):
    """Read PNG chunks; reuse the complete IDAT zlib stream in PDF."""
    if raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Некорректный PNG.')
    chunks = {}
    offset = 8
    while offset < len(raw):
        length = struct.unpack('>I', raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        payload = raw[offset + 8:offset + 8 + length]
        crc = raw[offset + 8 + length:offset + 12 + length]
        if len(crc) != 4 or zlib.crc32(kind + payload) & 0xffffffff != struct.unpack('>I', crc)[0]:
            raise ValueError('Повреждённый блок PNG.')
        chunks.setdefault(kind, []).append(payload)
        offset += length + 12
        if kind == b'IEND':
            break
    header = struct.unpack('>IIBBBBB', chunks[b'IHDR'][0])
    return header, chunks


def image_data(page):
    with Image.open(page.path) as source:
        if source.format != 'PNG':
            data, size, space = jpeg_data(page)
            return data, size, space, 8, '/DCTDecode', ''
        raw = page.path.read_bytes()
        header, chunks = png_stream(raw)
        px, py, depth, color, compression, filtering, interlace = header
        direct = (color in (0, 2, 3) and interlace == 0
                  and b'tRNS' not in chunks and source.getexif().get(274, 1) in (None, 1))
        if not direct:
            # Preserve visible pixels on the existing white preview background.
            # Pillow cannot preserve all channels of 16-bit RGB(A) on conversion.
            if depth == 16:
                raise ValueError('Этот 16-битный PNG требует преобразования. Сохраните копию в 8-битный PNG.')
            converted = ImageOps.exif_transpose(source)
            if converted.mode in ('RGBA', 'LA', 'P') or 'transparency' in converted.info:
                rgba = converted.convert('RGBA')
                converted = Image.new('RGB', rgba.size, 'white')
                converted.paste(rgba, mask=rgba.getchannel('A'))
            buffer = io.BytesIO()
            converted.save(buffer, 'PNG', optimize=True)
            header, chunks = png_stream(buffer.getvalue())
            px, py, depth, color, compression, filtering, interlace = header
        if color == 3:
            palette = chunks[b'PLTE'][0]
            space = f'[/Indexed /DeviceRGB {len(palette) // 3 - 1} <{palette.hex()}>]'
            colors = 1
        else:
            space = '/DeviceGray' if color == 0 else '/DeviceRGB'
            colors = 1 if color == 0 else 3
        params = (f'/DecodeParms << /Predictor 15 /Colors {colors} '
                  f'/BitsPerComponent {depth} /Columns {px} >>')
        return b''.join(chunks[b'IDAT']), (px, py), space, depth, '/FlateDecode', params


def write_pdf(pages, destination, progress=None):
    """Расширение исходного ручного PDF writer: три объекта на страницу."""
    if not pages:
        raise ValueError('Список страниц пуст.')
    destination = Path(destination)
    if any(destination.resolve() == p.path.resolve() for p in pages):
        raise ValueError('Нельзя заменить исходное изображение PDF-файлом.')
    fd, temporary = tempfile.mkstemp(prefix='.pdf-builder-', suffix='.tmp', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(b'%PDF-1.6\n%\xe2\xe3\xcf\xd3\n')
            offsets = [0]

            def obj(data):
                number = len(offsets)
                offsets.append(out.tell())
                out.write(f'{number} 0 obj\n'.encode('ascii'))
                out.write(data)
                out.write(b'\nendobj\n')

            obj(b'<< /Type /Catalog /Pages 2 0 R >>')
            kids = ' '.join(f'{3 + i * 3} 0 R' for i in range(len(pages)))
            obj(f'<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>'.encode('ascii'))
            for i, page in enumerate(pages):
                try:
                    w = positive(page.width) * MM_TO_PT
                    h = positive(page.height) * MM_TO_PT
                    # PDF 1.6 UserUnit preserves physical sizes above 200 inches.
                    unit = max(1.0, max(w, h) / 14400.0)
                    if not math.isfinite(unit) or unit > 75000:
                        raise ValueError('Размер страницы превышает предел PDF.')
                    w, h = w / unit, h / unit
                    data, (px, py), space, depth, codec, params = image_data(page)
                    number = 3 + i * 3
                    obj((f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w:.8f} {h:.8f}] '
                         f'/UserUnit {unit:.8f} /Resources << /XObject << /Im0 {number+1} 0 R >> >> '
                         f'/Contents {number+2} 0 R >>').encode('ascii'))
                    obj((f'<< /Type /XObject /Subtype /Image /Width {px} /Height {py} '
                         f'/ColorSpace {space} /BitsPerComponent {depth} /Filter {codec} {params} '
                         f'/Length {len(data)} >>\nstream\n').encode('ascii') + data + b'\nendstream')
                    content = f'q\n{w:.8f} 0 0 {h:.8f} 0 0 cm\n/Im0 Do\nQ\n'.encode('ascii')
                    obj(f'<< /Length {len(content)} >>\nstream\n'.encode('ascii') + content + b'endstream')
                    if progress:
                        progress(i + 1)
                except Exception as exc:
                    raise ValueError(f'{page.path.name}: {exc}') from exc
            xref = out.tell()
            out.write(f'xref\n0 {len(offsets)}\n'.encode('ascii'))
            out.write(b'0000000000 65535 f \n')
            for offset in offsets[1:]:
                out.write(f'{offset:010d} 00000 n \n'.encode('ascii'))
            out.write((f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n'
                       f'startxref\n{xref}\n%%EOF\n').encode('ascii'))
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def common_assembly_stem(pages):
    """Общее начало имён без расширений; не оставлять обрывок слова/номера."""
    stems = [p.path.stem for p in pages]
    if not stems:
        return ''
    prefix = os.path.commonprefix(stems)
    if prefix and prefix not in stems and prefix[-1].isalnum():
        if any(name[len(prefix):len(prefix) + 1].isalnum() for name in stems):
            prefix = re.sub(r'[^\s_\-–—.,;]+$', '', prefix)
    prefix = prefix.rstrip(' \t._-–—,;(')
    return prefix


def suggested_assembly_name(pages):
    return (common_assembly_stem(pages) or 'Сборка') + '.pdf'


def reserve_output(source):
    base = source.with_name(source.stem + ' (просмотр)')
    index = 1
    while True:
        path = Path(str(base) + ('' if index == 1 else f' ({index})') + '.pdf')
        try:
            with path.open('xb'):
                pass
            return path
        except FileExistsError:
            index += 1


class App:
    def __init__(self):
        self.root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
        self.root.title('PDF-сборщик • изображения в PDF')
        self.root.geometry('900x620')
        self.root.minsize(760, 530)
        self.pages = {}
        self.selected = None
        self.serial = 0
        self.updating = False
        self.busy = False
        self.events = queue.Queue()
        self.width_var = tk.StringVar()
        self.height_var = tk.StringVar()
        self.keep_ratio = tk.BooleanVar(value=True)
        self.merge = tk.BooleanVar(value=False)
        self.merge_manual = False
        self.status = tk.StringVar(value='Добавьте изображения. При отсутствии DPI используется 150.')
        self.caption = tk.StringVar(value='Выберите файл в списке')
        self.controls = []
        self.build_ui()
        self.width_var.trace_add('write', lambda *_: self.dimension_changed('width'))
        self.height_var.trace_add('write', lambda *_: self.dimension_changed('height'))
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        if len(sys.argv) > 1:
            self.add_files(sys.argv[1:])

    def button(self, parent, text, command):
        widget = ttk.Button(parent, text=text, command=command)
        self.controls.append(widget)
        return widget

    def build_ui(self):
        f = ttk.Frame(self.root, padding=16)
        f.pack(fill='both', expand=True)
        drop = ttk.Label(f, text='Перетащите JPEG / PNG / WebP сюда\nили добавьте файлы кнопкой ниже',
                         anchor='center', relief='groove', padding=18)
        drop.pack(fill='x')
        bar = ttk.Frame(f)
        bar.pack(fill='x', pady=8)
        for text, command in [('Добавить файлы…', self.choose_files), ('↑ Вверх', lambda: self.move(-1)),
                              ('↓ Вниз', lambda: self.move(1)), ('Удалить', self.remove)]:
            self.button(bar, text, command).pack(side='left', padx=(0, 6))
        table = ttk.Frame(f)
        table.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(table, columns=('name', 'pixels', 'dpi', 'mm'), show='headings', selectmode='browse')
        for key, label, width in [('name', 'Файл', 290), ('pixels', 'Пиксели', 130),
                                  ('dpi', 'DPI из метаданных', 160), ('mm', 'Размер PDF, мм', 180)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=80)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(table, command=self.tree.yview)
        scroll.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>', self.select)
        if TkinterDnD:
            for widget in (drop, self.tree):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind('<<Drop>>', lambda e: self.add_files(self.root.tk.splitlist(e.data)))
        edit = ttk.LabelFrame(f, text='Размер выбранной страницы', padding=10)
        edit.pack(fill='x', pady=10)
        ttk.Label(edit, textvariable=self.caption, wraplength=790).pack(anchor='w')
        row = ttk.Frame(edit)
        row.pack(fill='x', pady=6)
        for label, var in [('Ширина, мм', self.width_var), ('Высота, мм', self.height_var)]:
            ttk.Label(row, text=label).pack(side='left', padx=(0, 6))
            entry = ttk.Entry(row, textvariable=var, width=14)
            entry.pack(side='left', padx=(0, 16))
            self.controls.append(entry)
        check = ttk.Checkbutton(edit, text='Сохранять пропорции', variable=self.keep_ratio, command=self.ratio_toggled)
        check.pack(side='left')
        self.controls.append(check)
        self.button(edit, 'Вернуть размер по DPI', self.reset_size).pack(side='right')
        check = ttk.Checkbutton(f, text='Объединить в один PDF', variable=self.merge,
                                command=self.merge_toggled)
        check.pack(anchor='w')
        self.controls.append(check)
        ttk.Label(f, text='Без галочки: отдельные PDF рядом с исходниками. С галочкой: выбор имени общего PDF.').pack(anchor='w', pady=4)
        self.button(f, 'Создать PDF', self.create_pdf).pack(fill='x', pady=5)
        self.progress = ttk.Progressbar(f, mode='determinate')
        self.progress.pack(fill='x')
        ttk.Label(f, textvariable=self.status, wraplength=820).pack(anchor='w', pady=4)
        hint = 'JPEG RGB/Gray — напрямую; PNG — без JPEG-сжатия. WebP — JPEG 90%. Прозрачность на белом.'
        if not TkinterDnD:
            hint += '\nДля перетаскивания установите: pip install tkinterdnd2 — затем перезапустите программу.'
        ttk.Label(f, text=hint, foreground='#555555', wraplength=820).pack(anchor='w')

    def choose_files(self):
        self.add_files(filedialog.askopenfilenames(parent=self.root, title='Добавить изображения',
                       filetypes=[('Изображения', '*.jpg *.jpeg *.png *.webp'), ('Все файлы', '*.*')]))

    def add_files(self, paths):
        if self.busy:
            return
        errors = []
        existing = {os.path.normcase(str(p.path)) for p in self.pages.values()}
        for path in paths:
            try:
                if os.path.normcase(str(Path(path).resolve())) in existing:
                    continue
                page = Page.read(path)
                self.serial += 1
                key = str(self.serial)
                self.pages[key] = page
                self.tree.insert('', 'end', iid=key)
                self.refresh(key)
                existing.add(os.path.normcase(str(page.path)))
            except Exception as exc:
                errors.append(f'{Path(path).name}: {exc}')
        if not self.tree.selection() and self.tree.get_children():
            self.tree.selection_set(self.tree.get_children()[0])
            self.select()
        self.update_merge_default()
        self.status.set(f'Файлов: {len(self.pages)}. Порядок в списке = порядок страниц.')
        if errors:
            messagebox.showwarning('Некоторые файлы не добавлены', '\n'.join(errors), parent=self.root)

    def merge_toggled(self):
        self.merge_manual = True

    def update_merge_default(self):
        if not self.pages:
            self.merge_manual = False
            self.merge.set(False)
        elif not self.merge_manual:
            self.merge.set(len(self.pages) > 1 and bool(common_assembly_stem(list(self.pages.values()))))

    def refresh(self, key):
        p = self.pages[key]
        dpi = f'{fmt(p.dpi[0])} × {fmt(p.dpi[1])}'
        if p.fallback:
            dpi = 'Нет → 150'
        self.tree.item(key, values=(p.path.name, f'{p.pixels[0]} × {p.pixels[1]}', dpi,
                                   f'{fmt(p.width)} × {fmt(p.height)}'))

    def select(self, _event=None):
        selection = self.tree.selection()
        key = selection[0] if selection else None
        if key == self.selected:
            return
        self.selected = key
        self.show_page()

    def show_page(self):
        self.updating = True
        try:
            p = self.pages.get(self.selected)
            self.width_var.set(fmt(p.width) if p else '')
            self.height_var.set(fmt(p.height) if p else '')
            self.keep_ratio.set(p.keep_ratio if p else True)
            self.caption.set(str(p.path) if p else 'Выберите файл в списке')
        finally:
            self.updating = False

    def dimension_changed(self, source):
        if self.updating or self.busy or self.selected not in self.pages:
            return
        p = self.pages[self.selected]
        try:
            value = positive(self.width_var.get() if source == 'width' else self.height_var.get())
            setattr(p, source, value)
            if p.keep_ratio:
                ratio = p.original[0] / p.original[1]
                self.updating = True
                if source == 'width':
                    p.height = value / ratio
                    self.height_var.set(fmt(p.height))
                else:
                    p.width = value * ratio
                    self.width_var.set(fmt(p.width))
            self.refresh(self.selected)
            self.status.set('Размер сохранён для выбранного файла.')
        except ValueError:
            self.status.set('Введите размер больше нуля. Можно использовать запятую или точку.')
        finally:
            self.updating = False

    def ratio_toggled(self):
        if self.selected in self.pages:
            self.pages[self.selected].keep_ratio = self.keep_ratio.get()
            self.dimension_changed('width')

    def reset_size(self):
        if self.selected in self.pages:
            p = self.pages[self.selected]
            p.width, p.height = p.original
            self.show_page()
            self.refresh(self.selected)

    def move(self, delta):
        if self.busy or not self.selected:
            return
        index = self.tree.index(self.selected)
        self.tree.move(self.selected, '', max(0, min(len(self.pages) - 1, index + delta)))
        self.tree.see(self.selected)

    def remove(self):
        if self.busy or not self.selected:
            return
        key = self.selected
        index = self.tree.index(key)
        self.tree.delete(key)
        del self.pages[key]
        self.update_merge_default()
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[min(index, len(children) - 1)])
        self.select()

    def create_pdf(self):
        if self.busy:
            return
        if not self.pages:
            messagebox.showinfo('Нет файлов', 'Добавьте изображения.', parent=self.root)
            return
        if self.selected:
            try:
                positive(self.width_var.get())
                positive(self.height_var.get())
            except ValueError:
                messagebox.showwarning('Размер страницы', 'Введите положительные ширину и высоту.', parent=self.root)
                return
        pages = [self.pages[key] for key in self.tree.get_children()]
        destination = None
        if self.merge.get():
            destination = filedialog.asksaveasfilename(parent=self.root, title='Сохранить общий PDF',
                initialdir=pages[0].path.parent, initialfile=suggested_assembly_name(pages), defaultextension='.pdf', filetypes=[('PDF', '*.pdf')])
            if not destination:
                return
        self.busy = True
        for control in self.controls:
            control.state(['disabled'])
        self.progress.configure(maximum=len(pages), value=0)
        self.status.set('Создание PDF…')
        threading.Thread(target=self.worker, args=(pages, destination), daemon=True).start()
        self.root.after(100, self.poll)

    def worker(self, pages, destination):
        results, errors = [], []
        if destination:
            try:
                write_pdf(pages, destination, lambda n: self.events.put(('progress', n)))
                results.append(str(destination))
            except Exception as exc:
                errors.append(str(exc))
        else:
            for index, page in enumerate(pages):
                target = None
                try:
                    target = reserve_output(page.path)
                    write_pdf([page], target)
                    results.append(str(target))
                except Exception as exc:
                    errors.append(f'{page.path.name}: {exc}')
                    if target is not None:
                        try:
                            target.unlink()
                        except OSError:
                            pass
                self.events.put(('progress', index + 1))
        self.events.put(('done', (results, errors)))

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'progress':
                    self.progress.configure(value=value)
                    self.status.set(f'Обработано страниц: {value} из {len(self.pages)}')
                else:
                    self.busy = False
                    for control in self.controls:
                        control.state(['!disabled'])
                    results, errors = value
                    self.status.set(f'Готово. Создано PDF: {len(results)}. Ошибок: {len(errors)}.')
                    text = '\n'.join(results[:12])
                    if len(results) > 12:
                        text += f'\n…и ещё {len(results) - 12} рядом с исходниками.'
                    if errors:
                        messagebox.showwarning('Обработка завершена с ошибками', text + '\n\nОшибки:\n' + '\n'.join(errors), parent=self.root)
                    else:
                        messagebox.showinfo('PDF создан', text, parent=self.root)
                    return
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo('Создание PDF', 'Дождитесь завершения обработки.', parent=self.root)
        else:
            self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    App().run()
