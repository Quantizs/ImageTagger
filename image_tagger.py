"""Run: python image_tagger.py [image_directory]."""

from __future__ import annotations

import argparse
import copy
import math
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from annotation_store import AnnotationStore, ImageRecord, Polygon, polygon_area, valid_polygon
from surface_categories import CATEGORIES, CategorizedPolygon, auto_category, edited_polygon


class ImageTagger:
    def __init__(self, root: tk.Tk, directory: Path | None = None):
        self.root = root
        self.store: AnnotationStore | None = None
        self.index = 0
        self.selected: int | None = None
        self.image: Image.Image | None = None
        self.photo: ImageTk.PhotoImage | None = None
        self.scale = 1.0
        self.offset = (0.0, 0.0)
        self.fitted = True
        self.drag: dict | None = None
        self.pan_start = None
        self.preview: Polygon | None = None
        self.force_draw = False
        self.save_job = None
        self.resize_job = None
        self.undo_stacks: dict[Path, list[list[Polygon]]] = {}
        self.redo_stacks: dict[Path, list[list[Polygon]]] = {}
        self.save_message = "Válassz egy képmappát a kezdéshez."
        self.root.title("Image Tagger – poligon annotáció")
        self.root.geometry("1280x850")
        self.root.minsize(1000, 700)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._build_ui()
        self._bind_events()
        if directory is not None:
            self.root.after_idle(lambda: self.open_directory(directory))

    @property
    def record(self) -> ImageRecord | None:
        return self.store.records[self.index] if self.store else None

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", padding=(9, 6))
        style.configure("Title.TLabel", font=("Segoe UI", 12, "bold"))
        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Mappa megnyitása…", command=self.choose_directory).pack(side="left")
        ttk.Button(toolbar, text="◀ Előző", command=lambda: self.navigate(-1)).pack(side="left", padx=(16, 3))
        ttk.Button(toolbar, text="Következő ▶", command=lambda: self.navigate(1)).pack(side="left")
        ttk.Button(toolbar, text="Új négyszög (N)", command=self.draw_mode).pack(side="left", padx=(16, 3))
        ttk.Button(toolbar, text="Kijelölés (V)", command=self.select_mode).pack(side="left")
        ttk.Button(toolbar, text="Képhez igazít (F)", command=self.fit_image).pack(side="left", padx=8)
        ttk.Button(toolbar, text="Statisztika", command=self.show_statistics).pack(side="right")

        self.title_var = tk.StringVar(value="Image Tagger")
        ttk.Label(self.root, textvariable=self.title_var, style="Title.TLabel", padding=(12, 6)).pack(anchor="w")
        body = ttk.Frame(self.root, padding=(8, 0, 8, 0))
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, background="#18212d", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(side="left", fill="both", expand=True)
        side_container = ttk.Frame(body, padding=(12, 8, 4, 4), width=300)
        side_container.pack(side="right", fill="y")
        side_container.pack_propagate(False)
        tabs = ttk.Notebook(side_container)
        tabs.pack(fill="both", expand=True)
        sidebar, help_panel = ttk.Frame(tabs, padding=8), ttk.Frame(tabs, padding=8)
        tabs.add(sidebar, text="Objektumok")
        tabs.add(help_panel, text="Súgó")
        ttk.Label(sidebar, text="Objektumok ezen a képen", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.object_list = tk.Listbox(sidebar, exportselection=False, height=8,
                                     font=("Segoe UI", 10), activestyle="none")
        self.object_list.pack(fill="x", pady=8)
        self.object_list.bind("<<ListboxSelect>>", self.list_selection)
        ttk.Label(sidebar, text="Kijelölt objektum kategóriája").pack(anchor="w", pady=(4, 4))
        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(sidebar, textvariable=self.category_var,
                                           values=list(CATEGORIES), state="disabled")
        self.category_combo.pack(fill="x")
        self.category_combo.bind("<<ComboboxSelected>>", self.set_manual_category)
        self.category_info = tk.StringVar(value="Jelölj ki egy objektumot.")
        ttk.Label(sidebar, textvariable=self.category_info, wraplength=246,
                  foreground="#1b6394").pack(anchor="w", pady=6)
        self.manual_category_button = ttk.Button(sidebar, text="Rögzítés kéziként",
                                                 command=self.set_manual_category, state="disabled")
        self.manual_category_button.pack(fill="x")
        self.auto_category_button = ttk.Button(sidebar, text="Vissza automatikusra",
                                               command=self.reset_auto_category, state="disabled")
        self.auto_category_button.pack(fill="x", pady=(3, 10))
        ttk.Button(sidebar, text="Kijelölt törlése (Delete)", command=self.delete_selected).pack(fill="x")
        ttk.Button(sidebar, text="Visszavonás (Ctrl+Z)", command=self.undo).pack(fill="x", pady=(8, 3))
        ttk.Button(sidebar, text="Újra (Ctrl+Y)", command=self.redo).pack(fill="x")
        ttk.Separator(sidebar).pack(fill="x", pady=12)
        ttk.Button(sidebar, text="Mappa automatikus kategorizálása",
                   command=self.categorize_folder).pack(fill="x")
        ttk.Label(sidebar, text="A kézi kategóriákat megőrzi.", foreground="#61758a").pack(anchor="w", pady=5)
        ttk.Label(help_panel, text=(
            "Húzás üres helyen: új téglalap.\n\n"
            "Kattintás a poligonra: kijelölés.\n"
            "Sarok húzása: alak módosítása.\n"
            "Belső rész húzása: mozgatás.\n\n"
            "N: új, akár átfedő négyszög.\n"
            "V: vissza a kijelöléshez.\n"
            "Esc: aktuális húzás elvetése.\n\n"
            "← / →: előző / következő kép.\n"
            "Görgő: nagyítás a kurzornál.\n"
            "Középső gomb: kép mozgatása.\n"
            "F: teljes kép megjelenítése.\n"
            "Ctrl+S: mentés most.\n\n"
            "A módosítások automatikusan\nmentésre kerülnek."
        ), justify="left", wraplength=215).pack(anchor="w")
        self.mode_var = tk.StringVar(value="Kijelölés / rajzolás üres helyen")
        ttk.Label(help_panel, textvariable=self.mode_var, wraplength=246,
                  foreground="#1b6394").pack(anchor="w", pady=12)
        self.count_var = tk.StringVar(value="Összes kép: 0  |  Annotált kép: 0  |  Objektum: 0")
        ttk.Label(self.root, textvariable=self.count_var, padding=(12, 6)).pack(anchor="w")
        self.status_var = tk.StringVar(value=self.save_message)
        ttk.Label(self.root, textvariable=self.status_var, padding=(12, 0, 12, 8),
                  wraplength=1200).pack(anchor="w")

    def _bind_events(self):
        for key, callback in {
            "<Left>": lambda: self.navigate(-1), "<Right>": lambda: self.navigate(1),
            "<Delete>": self.delete_selected, "<BackSpace>": self.delete_selected,
            "<Control-z>": self.undo, "<Control-y>": self.redo,
            "<Control-s>": self.save_now, "<Escape>": self.cancel_drag,
            "n": self.draw_mode, "v": self.select_mode, "f": self.fit_image,
        }.items():
            self.root.bind(key, lambda event, action=callback: self.key_action(action, event))
        self.canvas.bind("<ButtonPress-1>", self.mouse_down)
        self.canvas.bind("<B1-Motion>", self.mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.mouse_up)
        self.canvas.bind("<MouseWheel>", self.zoom)
        self.canvas.bind("<Button-4>", lambda event: self.zoom(event, 1))
        self.canvas.bind("<Button-5>", lambda event: self.zoom(event, -1))
        self.canvas.bind("<ButtonPress-2>", self.pan_down)
        self.canvas.bind("<B2-Motion>", self.pan_move)
        self.canvas.bind("<ButtonRelease-2>", lambda event: setattr(self, "pan_start", None))
        self.canvas.bind("<Configure>", self.on_resize)

    @staticmethod
    def key_action(action, event=None):
        if event is not None and isinstance(event.widget, ttk.Combobox):
            return
        action()
        return "break"

    def choose_directory(self):
        directory = filedialog.askdirectory(title="Képek munkamappája", parent=self.root,
                                             initialdir=str(self.store.directory) if self.store else str(Path.cwd()))
        if directory:
            self.open_directory(Path(directory))

    def open_directory(self, directory: Path):
        self.finish_drag()
        if self.store and not self.persist(include_statistics=True):
            return
        try:
            store = AnnotationStore(directory)
        except (OSError, ValueError) as exc:
            messagebox.showerror("A mappa nem nyitható meg", str(exc), parent=self.root)
            return
        self.store = store
        self.index = store.restore_index()
        self.undo_stacks.clear()
        self.redo_stacks.clear()
        self.load_image()
        self.persist()
        if store.session_warning:
            messagebox.showwarning("Folytatási pozíció", store.session_warning, parent=self.root)

    def load_image(self):
        record = self.record
        if record is None:
            return
        self.selected = None
        self.drag = None
        self.preview = None
        self.image = None
        self.select_mode()
        try:
            # Use the stored raster orientation, exactly matching width/height in labels.
            with Image.open(record.path) as source:
                self.image = source.convert("RGB")
            record.image_error = ""
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            record.image_error = str(exc)
        self.title_var.set(f"{self.index + 1} / {len(self.store.records)}  ·  {record.path.name}"
                           f"  ·  {record.width} × {record.height} px")
        self.root.title(f"{record.path.name} – Image Tagger – {self.store.directory}")
        self.refresh_list()
        self.fit_image()
        self.save_message = "Mentve • automatikus mentés aktív"
        self.refresh_status()

    def navigate(self, direction: int):
        if not self.store:
            return
        self.finish_drag()
        if not self.persist():
            return
        destination = max(0, min(len(self.store.records) - 1, self.index + direction))
        if destination != self.index:
            self.index = destination
            self.load_image()
            self.persist()

    def refresh_status(self):
        if self.store:
            annotated = sum(bool(record.polygons) for record in self.store.records)
            count = sum(len(record.polygons) for record in self.store.records)
            errors = sum(not record.editable for record in self.store.records)
            self.count_var.set(f"Összes kép: {len(self.store.records)}  |  Annotált kép: {annotated}"
                               f"  |  Objektum: {count}  |  Nagyítás: {self.scale * 100:.0f}%"
                               + (f"  |  Hibás fájl: {errors}" if errors else ""))
        record = self.record
        error = "; ".join(filter(None, (record.image_error, record.annotation_error))) if record else ""
        self.status_var.set(f"Csak olvasható – {error}" if error else self.save_message)

    def refresh_list(self):
        self.object_list.delete(0, "end")
        record = self.record
        if record:
            for i, polygon in enumerate(record.polygons):
                area = polygon_area(polygon) * record.width * record.height
                name = getattr(polygon, "category", "Nincs kategória")
                self.object_list.insert("end", f"{i + 1}. {name}  ·  {area:,.0f} px²")
        if self.selected is not None:
            self.object_list.selection_set(self.selected)
            self.object_list.see(self.selected)
        self.refresh_category()

    def refresh_category(self):
        if self.record and self.selected is not None and self.selected < len(self.record.polygons):
            polygon = self.record.polygons[self.selected]
            self.category_var.set(getattr(polygon, "category", ""))
            source = getattr(polygon, "category_source", None)
            self.category_info.set({"manual": "Kézzel rögzített • automatikusan nem változik.",
                                    "auto": "Automatikus javaslat • szükség esetén javítsd."}.get(
                                        source, "Régi annotáció • még nincs kategóriája."))
            enabled = self.record.editable
        else:
            self.category_var.set("")
            self.category_info.set("Jelölj ki egy objektumot.")
            enabled = False
        self.category_combo.configure(state="readonly" if enabled else "disabled")
        for button in (self.manual_category_button, self.auto_category_button):
            button.configure(state="normal" if enabled else "disabled")

    def set_manual_category(self, event=None):
        category = self.category_var.get()
        self.finish_drag()
        if not self.record or not self.record.editable or self.selected is None or category not in CATEGORIES:
            return
        self.remember(copy.deepcopy(self.record.polygons))
        self.record.polygons[self.selected] = CategorizedPolygon(self.record.polygons[self.selected], category, "manual")
        self.changed()
        self.canvas.focus_set()

    def reset_auto_category(self):
        self.finish_drag()
        if not self.record or not self.record.editable or self.selected is None:
            return
        self.remember(copy.deepcopy(self.record.polygons))
        # Explicit opt-in to discard a manual choice and return to automatic updates.
        self.record.polygons[self.selected] = auto_category(list(self.record.polygons[self.selected]),
                                                           (self.record.width, self.record.height))
        self.changed()
        self.canvas.focus_set()

    def categorize_folder(self):
        self.finish_drag()
        if not self.store or not self.persist():
            return
        changed = manual = errors = 0
        for record in self.store.records:
            if not record.editable:
                errors += 1
                continue
            before = copy.deepcopy(record.polygons)
            counts = self.store.categorize_record(record)
            if counts["changed"]:
                self.remember(before, record.path)
            changed += counts["changed"]
            manual += counts["manual_preserved"]
        self.refresh_list()
        if self.persist(include_statistics=True):
            messagebox.showinfo("Kategorizálás kész", f"Módosított objektum: {changed}\nMegőrzött kézi kategória: {manual}"
                                f"\nHiba miatt kihagyott kép: {errors}", parent=self.root)

    def list_selection(self, event=None):
        selection = self.object_list.curselection()
        if selection:
            self.finish_drag()
            self.selected = selection[0]
            self.select_mode()
            self.refresh_category()
            self.draw_overlays()

    def screen_point(self, point):
        record = self.record
        return (self.offset[0] + point[0] * record.width * self.scale,
                self.offset[1] + point[1] * record.height * self.scale)

    def image_point(self, x, y, clamp=True):
        record = self.record
        px = (x - self.offset[0]) / (record.width * self.scale)
        py = (y - self.offset[1]) / (record.height * self.scale)
        return (max(0, min(1, px)), max(0, min(1, py))) if clamp else (px, py)

    def on_resize(self, event=None):
        if self.resize_job is not None:
            self.root.after_cancel(self.resize_job)
        self.resize_job = self.root.after(70, self.resize_canvas)

    def resize_canvas(self):
        self.resize_job = None
        if self.fitted:
            self.fit_image()
        else:
            self.render_background()

    def fit_image(self):
        if self.drag:
            self.finish_drag()
        self.fitted = True
        if self.image:
            width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
            self.scale = min(max(1, width - 32) / self.image.width,
                             max(1, height - 32) / self.image.height)
            self.offset = ((width - self.image.width * self.scale) / 2,
                           (height - self.image.height * self.scale) / 2)
        self.render_background()
        self.refresh_status()

    def render_background(self):
        self.canvas.delete("background")
        if self.image:
            width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
            x0 = max(0, math.floor(-self.offset[0] / self.scale))
            y0 = max(0, math.floor(-self.offset[1] / self.scale))
            x1 = min(self.image.width, math.ceil((width - self.offset[0]) / self.scale))
            y1 = min(self.image.height, math.ceil((height - self.offset[1]) / self.scale))
            if x1 > x0 and y1 > y0:
                crop = self.image.crop((x0, y0, x1, y1))
                size = (max(1, round((x1 - x0) * self.scale)), max(1, round((y1 - y0) * self.scale)))
                self.photo = ImageTk.PhotoImage(crop.resize(size, Image.Resampling.LANCZOS))
                self.canvas.create_image(self.offset[0] + x0 * self.scale,
                                         self.offset[1] + y0 * self.scale,
                                         anchor="nw", image=self.photo, tags="background")
        else:
            self.canvas.create_text(30, 40, anchor="nw", fill="#ffffff", font=("Segoe UI", 14),
                                    text="A kép nem tölthető be." if self.store else "Nyiss meg egy képmappát a kezdéshez.",
                                    tags="background")
        self.canvas.tag_lower("background")
        self.draw_overlays()

    def draw_overlays(self):
        self.canvas.delete("overlay")
        record = self.record
        if record is None or self.image is None:
            return
        for i, polygon in enumerate(record.polygons):
            points = [self.screen_point(point) for point in polygon]
            color = "#ffcf57" if i == self.selected else "#41f2b4"
            flat = [coordinate for point in points for coordinate in point]
            self.canvas.create_polygon(*flat, fill="", outline="#172332", width=5, tags="overlay")
            self.canvas.create_polygon(*flat, fill="", outline=color, width=2, tags="overlay")
            x, y = points[0]
            self.canvas.create_text(x + 9, y + 12, text=str(i + 1), fill="#101826",
                                    font=("Segoe UI", 13, "bold"), tags="overlay")
            self.canvas.create_text(x + 8, y + 11, text=str(i + 1), fill=color,
                                    font=("Segoe UI", 13, "bold"), tags="overlay")
            if i == self.selected:
                for label, (x, y) in zip(("TL", "TR", "BR", "BL"), points):
                    self.canvas.create_oval(x - 6, y - 6, x + 6, y + 6,
                                            fill=color, outline="#172332", width=2, tags="overlay")
                    self.canvas.create_text(x + 10, y - 12, text=label, fill=color,
                                            font=("Segoe UI", 9, "bold"), tags="overlay")
        if self.preview:
            points = [coordinate for point in self.preview for coordinate in self.screen_point(point)]
            self.canvas.create_polygon(*points, fill="", outline="#ffcf57", width=2,
                                       dash=(6, 3), tags="overlay")

    def draw_mode(self):
        self.finish_drag()
        self.force_draw = True
        self.mode_var.set("Új négyszög: húzz az egyik saroktól az átellenes sarokig.")
        self.canvas.configure(cursor="crosshair")

    def select_mode(self):
        self.force_draw = False
        self.mode_var.set("Kijelölés / rajzolás üres helyen")
        self.canvas.configure(cursor="crosshair")

    @staticmethod
    def contains(polygon, point):
        return all((polygon[(i + 1) % 4][0] - a[0]) * (point[1] - a[1])
                   - (polygon[(i + 1) % 4][1] - a[1]) * (point[0] - a[0]) >= 0
                   for i, a in enumerate(polygon))

    def mouse_down(self, event):
        self.canvas.focus_set()
        record = self.record
        if not record or not record.editable or self.image is None:
            return
        point = self.image_point(event.x, event.y, clamp=False)
        # Handles on the image boundary can be grabbed a few screen pixels outside it.
        if not self.force_draw and self.selected is not None:
            for corner, position in enumerate(record.polygons[self.selected]):
                x, y = self.screen_point(position)
                if math.hypot(event.x - x, event.y - y) <= 11:
                    self.drag = {"kind": "corner", "corner": corner, "start": point,
                                 "before": copy.deepcopy(record.polygons)}
                    return
        if not all(0 <= value <= 1 for value in point):
            return
        if not self.force_draw:
            order = list(reversed(range(len(record.polygons))))
            if self.selected is not None:
                order.remove(self.selected)
                order.insert(0, self.selected)
            for i in order:
                if self.contains(record.polygons[i], point):
                    self.selected = i
                    self.drag = {"kind": "move", "start": point,
                                 "before": copy.deepcopy(record.polygons)}
                    self.refresh_list()
                    self.draw_overlays()
                    return
        self.selected = None
        self.drag = {"kind": "new", "start": point, "before": copy.deepcopy(record.polygons)}
        self.preview = None
        self.refresh_list()
        self.draw_overlays()

    def mouse_move(self, event):
        if not self.drag:
            return
        record = self.record
        point = self.image_point(event.x, event.y)
        start = self.drag["start"]
        if self.drag["kind"] == "new":
            left, right = sorted((start[0], point[0]))
            top, bottom = sorted((start[1], point[1]))
            self.preview = [(left, top), (right, top), (right, bottom), (left, bottom)]
        else:
            polygon = copy.deepcopy(self.drag["before"][self.selected])
            if self.drag["kind"] == "corner":
                polygon[self.drag["corner"]] = point
            else:
                dx = max(-min(p[0] for p in polygon), min(1 - max(p[0] for p in polygon), point[0] - start[0]))
                dy = max(-min(p[1] for p in polygon), min(1 - max(p[1] for p in polygon), point[1] - start[1]))
                polygon = [(max(0, min(1, x + dx)), max(0, min(1, y + dy))) for x, y in polygon]
            if valid_polygon(polygon) and polygon_area(polygon) * record.width * record.height >= 1:
                if record.polygons[self.selected] != polygon:
                    record.polygons[self.selected] = edited_polygon(self.drag["before"][self.selected], polygon,
                                                                    (record.width, record.height))
                    self.refresh_category()
                    self.mark_dirty()
            else:
                self.save_message = "A sarkok nem keresztezhetik egymást; az objektum legalább 1 px² legyen."
                self.refresh_status()
        self.draw_overlays()

    def mouse_up(self, event):
        if self.drag:
            self.mouse_move(event)
            self.finish_drag()

    def remember(self, before, path=None):
        path = path if path is not None else self.record.path
        stack = self.undo_stacks.setdefault(path, [])
        stack.append(before)
        del stack[:-100]
        self.redo_stacks[path] = []

    def finish_drag(self):
        if not self.drag:
            return
        record = self.record
        before = self.drag["before"]
        if self.drag["kind"] == "new" and self.preview:
            polygon = self.preview
            # Require a deliberate visible drag; stored geometry uses original pixels.
            if (valid_polygon(polygon) and polygon_area(polygon) * record.width * record.height >= 1
                    and (polygon[1][0] - polygon[0][0]) * record.width * self.scale >= 3
                    and (polygon[3][1] - polygon[0][1]) * record.height * self.scale >= 3):
                record.polygons.append(auto_category(polygon, (record.width, record.height)))
                self.selected = len(record.polygons) - 1
                self.mark_dirty()
                self.select_mode()
        self.drag = None
        self.preview = None
        if before != record.polygons:
            self.remember(before)
        self.refresh_list()
        self.draw_overlays()
        if record.dirty:
            self.persist()

    def cancel_drag(self):
        if self.drag:
            self.record.polygons = self.drag["before"]
            self.drag = None
            self.preview = None
            self.mark_dirty()
            self.persist()
        else:
            self.selected = None
        self.select_mode()
        self.refresh_list()
        self.draw_overlays()

    def delete_selected(self):
        self.finish_drag()
        if self.record and self.record.editable and self.selected is not None:
            self.remember(copy.deepcopy(self.record.polygons))
            del self.record.polygons[self.selected]
            self.selected = None
            self.changed()

    def undo(self):
        self.finish_drag()
        if self.record and self.record.editable:
            stack = self.undo_stacks.get(self.record.path, [])
            if stack:
                self.redo_stacks.setdefault(self.record.path, []).append(copy.deepcopy(self.record.polygons))
                self.record.polygons = stack.pop()
                self.selected = None
                self.changed()

    def redo(self):
        self.finish_drag()
        if self.record and self.record.editable:
            stack = self.redo_stacks.get(self.record.path, [])
            if stack:
                self.undo_stacks.setdefault(self.record.path, []).append(copy.deepcopy(self.record.polygons))
                self.record.polygons = stack.pop()
                self.selected = None
                self.changed()

    def changed(self):
        self.mark_dirty()
        self.refresh_list()
        self.draw_overlays()
        self.persist()

    def mark_dirty(self):
        self.record.dirty = True
        self.save_message = "Mentés folyamatban…"
        self.refresh_status()
        # A timer from the first change also saves during a continuous long drag.
        if self.save_job is None:
            self.save_job = self.root.after(250, self.autosave)

    def autosave(self):
        self.save_job = None
        self.persist(show_error=False)

    def persist(self, include_statistics=False, show_error=True):
        if self.save_job is not None:
            self.root.after_cancel(self.save_job)
            self.save_job = None
        if not self.store:
            return True
        try:
            self.store.save_all()
            self.store.save_session(self.index)
            if include_statistics:
                self.store.save_statistics()
        except (OSError, ValueError) as exc:
            self.save_message = f"MENTÉSI HIBA – {exc}  |  Újrapróbálás: Ctrl+S"
            self.refresh_status()
            if show_error:
                messagebox.showerror("Sikertelen mentés", f"{exc}\n\nA módosítások a memóriában maradtak. "
                                     "Ellenőrizd a szabad helyet és az írási jogosultságot, majd Ctrl+S.", parent=self.root)
            return False
        self.save_message = "Mentve • automatikus mentés aktív"
        self.refresh_status()
        return True

    def save_now(self):
        self.finish_drag()
        self.persist()

    def show_statistics(self):
        self.finish_drag()
        if not self.store or not self.persist(include_statistics=True):
            return
        stats, _ = self.store.statistics()
        category_counts = "\n".join(
            f"{name}: {stats['objects_per_category'][name]}" for name in CATEGORIES
        )
        messagebox.showinfo("Statisztika – fájlba mentve", (
            f"Összes kép: {stats['total_images']}\n"
            f"Annotált kép: {stats['annotated_images']}\n"
            f"Annotált objektum: {stats['total_objects']}\n\n"
            "Objektumok kategóriánként:\n"
            f"{category_counts}\n"
            f"Kategória nélkül: {stats['objects_without_category']}\n\n"
            f"Átlagos objektumterület: {stats['mean_object_area_px2']:,.2f} px²\n"
            f"Átlagos darabszám / összes kép: {stats['mean_objects_per_image']:.2f}\n"
            f"Átlagos darabszám / annotált kép: {stats['mean_objects_per_annotated_image']:.2f}\n"
            f"Hibás fájlt tartalmazó képek: {stats['images_with_errors']}\n\n"
            f"Mentés helye: {self.store.output_directory}\n"
            "statistics.json és statistics_per_image.csv"
        ), parent=self.root)

    def zoom(self, event, direction=None):
        if self.image is None or self.drag:
            return
        direction = direction if direction is not None else (1 if event.delta > 0 else -1)
        old = self.scale
        fit = min(max(1, self.canvas.winfo_width() - 32) / self.image.width,
                  max(1, self.canvas.winfo_height() - 32) / self.image.height)
        self.scale = max(fit * 0.2, min(max(16.0, fit), old * (1.2 if direction > 0 else 1 / 1.2)))
        ratio = self.scale / old
        self.offset = (event.x - (event.x - self.offset[0]) * ratio,
                       event.y - (event.y - self.offset[1]) * ratio)
        self.fitted = False
        self.render_background()
        self.refresh_status()

    def pan_down(self, event):
        if not self.drag:
            self.pan_start = (event.x, event.y, self.offset)

    def pan_move(self, event):
        if self.pan_start and self.image:
            x, y, offset = self.pan_start
            self.offset = (offset[0] + event.x - x, offset[1] + event.y - y)
            self.fitted = False
            self.render_background()

    def close(self):
        self.finish_drag()
        if self.persist(include_statistics=True):
            self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="Négyszög annotáció képeken, automatikus mentéssel.")
    parser.add_argument("directory", nargs="?", type=Path, help="Képeket tartalmazó munkamappa")
    args = parser.parse_args()
    root = tk.Tk()
    ImageTagger(root, args.directory)
    root.mainloop()


if __name__ == "__main__":
    main()
