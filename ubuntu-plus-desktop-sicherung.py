#!/usr/bin/env python3
# ==============================================================================
# Ubuntu-PLUS Desktop-Sicherung
# ------------------------------------------------------------------------------
# Beschreibung:
# Dieses Tool ermöglicht es, den aktuellen GNOME-Desktop schnell und einfach
# zu sichern oder wiederherzustellen. Gesichert werden:
#   - GNOME-Einstellungen (über dconf)
#   - Aktive GNOME-Shell-Erweiterungen inkl. Konfiguration
#   - Themes, Icons, Fonts, GTK-Konfiguration
#   - Hintergrundbild (hell + dunkel) und Autostart-Einträge
#
# NEU: Vorlagen-System
#   - Aktuellen Desktop als benannte Vorlage speichern
#   - Per Klick zwischen Vorlagen wechseln (mit Wallpaper-Vorschau)
#   - Vorlagen importieren (aus .tar.gz) oder löschen
#   - Vorlagen exportieren als .tar.gz
#
# Autor: evilware666 & Helga
# Version: 2.1
# Datum: 2025-10-14
# ==============================================================================

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gio, GLib, GdkPixbuf
import subprocess
import os
import tempfile
import shutil
from datetime import datetime
import threading
import json


# ------------------------------------------------------------------------------
# Konstanten & Konfiguration
# ------------------------------------------------------------------------------

_DEFAULT_PRESETS_DIR = os.path.join(os.path.expanduser("~"), ".local/share/ubuntu-plus/gnome-presets")
_CONFIG_FILE         = os.path.join(os.path.expanduser("~"), ".local/share/ubuntu-plus/gnome-backup-config.json")
PRESET_META          = "preset-meta.json"
WALLPAPER_THUMB      = "wallpaper-thumb.png"   # 96x54 px Vorschaubild


def load_config():
    """App-Konfiguration laden (erstellt Standardwerte falls nicht vorhanden)."""
    try:
        if os.path.exists(_CONFIG_FILE):
            with open(_CONFIG_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {"presets_dir": _DEFAULT_PRESETS_DIR}


def save_config(cfg):
    """App-Konfiguration speichern."""
    try:
        os.makedirs(os.path.dirname(_CONFIG_FILE), exist_ok=True)
        with open(_CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def get_presets_dir():
    """Aktuell konfigurierten Vorlagen-Ordner zurückgeben."""
    return load_config().get("presets_dir", _DEFAULT_PRESETS_DIR)


def set_presets_dir(path):
    """Vorlagen-Ordner dauerhaft speichern."""
    cfg = load_config()
    cfg["presets_dir"] = path
    save_config(cfg)

INCLUDE_DIRS = [
    ".config/autostart",
    ".local/share/applications",
    ".local/share/icons",
    ".icons",
    ".themes",
    ".fonts",
    ".config/gtk-3.0",
    ".config/gtk-4.0",
    ".config/dconf",
]


# ------------------------------------------------------------------------------
# Hilfsfunktionen GNOME
# ------------------------------------------------------------------------------

def get_active_extensions():
    """Liste der aktuell aktivierten GNOME-Shell-Erweiterungen."""
    try:
        r = subprocess.run(
            ['gsettings', 'get', 'org.gnome.shell', 'enabled-extensions'],
            capture_output=True, text=True)
        raw = r.stdout.strip()
        if raw.startswith('@as') or raw in ('[]', ''):
            return []
        raw = raw.strip("[]").replace("'", '"')
        return [p.strip().strip('"') for p in raw.split(',') if p.strip().strip('"')]
    except Exception:
        return []


def get_current_wallpaper():
    """Aktuellen Wallpaper-Pfad ermitteln."""
    try:
        r = subprocess.run(
            ['gsettings', 'get', 'org.gnome.desktop.background', 'picture-uri'],
            capture_output=True, text=True)
        path = r.stdout.strip().strip("'").replace('file://', '')
        return path if os.path.exists(path) else None
    except Exception:
        return None


def get_current_theme_info():
    """Aktives GTK-Theme, Icon-Theme, Cursor-Theme und Font auslesen."""
    info = {}
    for label, schema, key in [
        ('gtk-theme',    'org.gnome.desktop.interface', 'gtk-theme'),
        ('icon-theme',   'org.gnome.desktop.interface', 'icon-theme'),
        ('cursor-theme', 'org.gnome.desktop.interface', 'cursor-theme'),
        ('font',         'org.gnome.desktop.interface', 'font-name'),
    ]:
        try:
            r = subprocess.run(['gsettings', 'get', schema, key],
                               capture_output=True, text=True)
            info[label] = r.stdout.strip().strip("'")
        except Exception:
            info[label] = '–'
    return info


def make_wallpaper_thumb(wallpaper_path, dest_path, width=96, height=54):
    """Wallpaper auf Thumbnail-Größe skalieren und als PNG speichern."""
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(wallpaper_path, width, height, False)
        pb.savev(dest_path, "png", [], [])
        return True
    except Exception:
        return False


# ------------------------------------------------------------------------------
# Kern-Backup-Logik  (wird von Backup-Tab und Vorlagen-Tab gemeinsam genutzt)
# ------------------------------------------------------------------------------

def _collect_into_tmpdir(tmpdir, cancel_flag=None):
    """
    Alle Desktop-Daten im tmpdir sammeln.
    Gibt Metadaten-Dict zurück, oder None bei Abbruch.
    """
    home = os.path.expanduser("~")

    # 1. Vollständiger dconf-Dump
    with open(f"{tmpdir}/gnome-settings.dconf", 'w') as f:
        subprocess.run(['dconf', 'dump', '/'], stdout=f)

    if cancel_flag and cancel_flag.is_set():
        return None

    # 2. Liste aktiver Erweiterungen
    active_exts = get_active_extensions()
    with open(f"{tmpdir}/active-extensions.json", 'w') as f:
        json.dump(active_exts, f, indent=2)

    # 3. User-Erweiterungsverzeichnis kopieren
    user_ext = os.path.join(home, ".local/share/gnome-shell/extensions")
    if os.path.isdir(user_ext):
        shutil.copytree(user_ext, f"{tmpdir}/gnome-extensions", dirs_exist_ok=True)

    if cancel_flag and cancel_flag.is_set():
        return None

    # 4. Wallpaper sichern (hell + dunkel)
    os.makedirs(f"{tmpdir}/wallpaper", exist_ok=True)
    for gskey, fname in [('picture-uri', 'path.txt'), ('picture-uri-dark', 'path-dark.txt')]:
        r = subprocess.run(
            ['gsettings', 'get', 'org.gnome.desktop.background', gskey],
            capture_output=True, text=True)
        if r.returncode == 0:
            wp = r.stdout.strip().strip("'").replace('file://', '')
            if wp and os.path.exists(wp):
                shutil.copy(wp, f"{tmpdir}/wallpaper/")
                with open(f"{tmpdir}/wallpaper/{fname}", 'w') as f:
                    f.write(wp)

    # 5. Metadaten zusammenstellen
    meta = {
        "created": datetime.now().isoformat(timespec='seconds'),
        "extensions_count": len(active_exts),
        "active_extensions": active_exts,
        "theme_info": get_current_theme_info(),
    }
    return meta


def _build_tar(speicherort, tmpdir):
    """TAR-Archiv aus Home-Verzeichnis-Unterordnern + tmpdir-Inhalten bauen."""
    home = os.path.expanduser("~")
    os.chdir(home)

    tar_args = ['tar', '-czf', speicherort]
    for d in INCLUDE_DIRS:
        if os.path.exists(d):
            tar_args.append(d)

    tmp_items = ['gnome-settings.dconf', 'active-extensions.json']
    if os.path.isdir(f"{tmpdir}/gnome-extensions"):
        tmp_items.append('gnome-extensions')
    if os.path.isdir(f"{tmpdir}/wallpaper"):
        tmp_items.append('wallpaper')

    tar_args.extend(['-C', tmpdir] + tmp_items)
    subprocess.run(tar_args, stderr=subprocess.DEVNULL)


def _restore_from_tmpdir(tmpdir, cancel_flag=None):
    """
    Entpackten tmpdir auf das Home-Verzeichnis anwenden.
    Gibt (restored_ext_count, reactivated_count) zurück.
    """
    home = os.path.expanduser("~")

    # Verzeichnisse per rsync zurückschreiben
    for d in INCLUDE_DIRS:
        src = os.path.join(tmpdir, d)
        dst = os.path.join(home, d)
        if os.path.exists(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            subprocess.run(['rsync', '-a', f"{src}/", f"{dst}/"], stderr=subprocess.DEVNULL)

    if cancel_flag and cancel_flag.is_set():
        return 0, 0

    # User-Erweiterungen wiederherstellen
    ext_src = os.path.join(tmpdir, "gnome-extensions")
    ext_dst = os.path.join(home, ".local/share/gnome-shell/extensions")
    restored_ext_count = 0
    if os.path.isdir(ext_src):
        os.makedirs(ext_dst, exist_ok=True)
        subprocess.run(['rsync', '-a', f"{ext_src}/", f"{ext_dst}/"], stderr=subprocess.DEVNULL)
        restored_ext_count = len([
            x for x in os.listdir(ext_dst)
            if os.path.isdir(os.path.join(ext_dst, x))
        ])

    # dconf-Einstellungen laden
    dconf_file = os.path.join(tmpdir, "gnome-settings.dconf")
    if os.path.exists(dconf_file):
        with open(dconf_file, 'r') as f:
            subprocess.run(['dconf', 'load', '/'], stdin=f)

    if cancel_flag and cancel_flag.is_set():
        return restored_ext_count, 0

    # Erweiterungen reaktivieren (nur vorhandene)
    reactivated = []
    ext_list_file = os.path.join(tmpdir, "active-extensions.json")
    if os.path.exists(ext_list_file):
        with open(ext_list_file, 'r') as f:
            saved_exts = json.load(f)
        if saved_exts:
            available = set()
            for check_dir in [ext_dst, "/usr/share/gnome-shell/extensions"]:
                if os.path.isdir(check_dir):
                    available |= {x for x in os.listdir(check_dir)
                                  if os.path.isdir(os.path.join(check_dir, x))}
            reactivated = [e for e in saved_exts if e in available]
            if reactivated:
                ext_str = "[" + ", ".join(f"'{e}'" for e in reactivated) + "]"
                subprocess.run(
                    ['gsettings', 'set', 'org.gnome.shell', 'enabled-extensions', ext_str],
                    stderr=subprocess.DEVNULL)

    # Wallpaper setzen
    bilder_dir = os.path.join(home, "Bilder")
    os.makedirs(bilder_dir, exist_ok=True)
    for fname, gskey in [('path.txt', 'picture-uri'), ('path-dark.txt', 'picture-uri-dark')]:
        pf = os.path.join(tmpdir, "wallpaper", fname)
        if os.path.exists(pf):
            with open(pf, 'r') as f:
                wall_path = f.read().strip()
            wall_file = os.path.basename(wall_path)
            src_wall  = os.path.join(tmpdir, "wallpaper", wall_file)
            if os.path.exists(src_wall):
                dst_wall = os.path.join(bilder_dir, wall_file)
                shutil.copy(src_wall, dst_wall)
                subprocess.run([
                    'gsettings', 'set', 'org.gnome.desktop.background',
                    gskey, f"file://{dst_wall}"
                ], stderr=subprocess.DEVNULL)

    return restored_ext_count, len(reactivated)


# ------------------------------------------------------------------------------
# Vorlagen-Verwaltung
# ------------------------------------------------------------------------------

def list_presets():
    """Alle gespeicherten Vorlagen auflisten → Liste von dicts {name, path, meta}."""
    presets = []
    presets_dir = get_presets_dir()
    if not os.path.isdir(presets_dir):
        return presets
    for entry in sorted(os.listdir(presets_dir)):
        preset_path = os.path.join(presets_dir, entry)
        meta_file   = os.path.join(preset_path, PRESET_META)
        if os.path.isdir(preset_path) and os.path.exists(meta_file):
            try:
                with open(meta_file, 'r') as f:
                    meta = json.load(f)
                presets.append({"name": entry, "path": preset_path, "meta": meta})
            except Exception:
                pass
    return presets


def save_preset(name, cancel_flag=None):
    """Aktuellen Desktop-Zustand als benannte Vorlage speichern."""
    try:
        safe = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
        if not safe:
            return {"success": False, "text": "Ungültiger Name."}

        preset_path = os.path.join(get_presets_dir(), safe)
        os.makedirs(preset_path, exist_ok=True)

        tmpdir = tempfile.mkdtemp()
        meta = _collect_into_tmpdir(tmpdir, cancel_flag)
        if meta is None:
            shutil.rmtree(tmpdir)
            shutil.rmtree(preset_path, ignore_errors=True)
            return {"success": False, "text": "Abgebrochen."}

        _build_tar(os.path.join(preset_path, "desktop.tar.gz"), tmpdir)

        # Wallpaper-Thumbnail
        wp = get_current_wallpaper()
        if wp:
            make_wallpaper_thumb(wp, os.path.join(preset_path, WALLPAPER_THUMB))

        meta["name"] = safe
        with open(os.path.join(preset_path, PRESET_META), 'w') as f:
            json.dump(meta, f, indent=2)

        shutil.rmtree(tmpdir)
        return {"success": True, "name": safe, "ext_count": meta["extensions_count"]}
    except Exception as e:
        return {"success": False, "text": str(e)}


def apply_preset(preset_path, cancel_flag=None):
    """Vorlage auf den Desktop anwenden."""
    try:
        tar_path = os.path.join(preset_path, "desktop.tar.gz")
        if not os.path.exists(tar_path):
            return {"success": False, "text": "Vorlage beschädigt (keine TAR-Datei)."}

        tmpdir = tempfile.mkdtemp()
        subprocess.run(['tar', '-xzf', tar_path, '-C', tmpdir], stderr=subprocess.DEVNULL)

        if cancel_flag and cancel_flag.is_set():
            shutil.rmtree(tmpdir)
            return {"success": False, "text": "Abgebrochen."}

        restored, reactivated = _restore_from_tmpdir(tmpdir, cancel_flag)
        shutil.rmtree(tmpdir)
        return {"success": True, "restored": restored, "reactivated": reactivated}
    except Exception as e:
        return {"success": False, "text": str(e)}


def import_preset_from_tar(tar_path, name, cancel_flag=None):
    """Eine .tar.gz-Backup-Datei als Vorlage importieren."""
    try:
        safe = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
        if not safe:
            return {"success": False, "text": "Ungültiger Name."}

        preset_path = os.path.join(get_presets_dir(), safe)
        os.makedirs(preset_path, exist_ok=True)

        dest_tar = os.path.join(preset_path, "desktop.tar.gz")
        shutil.copy(tar_path, dest_tar)

        # Kurz entpacken um Thumbnail + Metadaten zu extrahieren
        tmpdir = tempfile.mkdtemp()
        subprocess.run(['tar', '-xzf', dest_tar, '-C', tmpdir], stderr=subprocess.DEVNULL)

        active_exts = []
        ef = os.path.join(tmpdir, "active-extensions.json")
        if os.path.exists(ef):
            with open(ef, 'r') as f:
                active_exts = json.load(f)

        # Wallpaper-Thumbnail aus dem entpackten Archiv
        thumb_path = os.path.join(preset_path, WALLPAPER_THUMB)
        pf = os.path.join(tmpdir, "wallpaper/path.txt")
        if os.path.exists(pf):
            with open(pf) as f:
                wp_orig = f.read().strip()
            wp_src = os.path.join(tmpdir, "wallpaper", os.path.basename(wp_orig))
            if os.path.exists(wp_src):
                make_wallpaper_thumb(wp_src, thumb_path)

        shutil.rmtree(tmpdir)

        meta = {
            "name": safe,
            "created": datetime.now().isoformat(timespec='seconds'),
            "imported_from": os.path.basename(tar_path),
            "extensions_count": len(active_exts),
            "active_extensions": active_exts,
            "theme_info": {},
        }
        with open(os.path.join(preset_path, PRESET_META), 'w') as f:
            json.dump(meta, f, indent=2)

        return {"success": True, "name": safe, "ext_count": len(active_exts)}
    except Exception as e:
        return {"success": False, "text": str(e)}


# ------------------------------------------------------------------------------
# Haupt-Anwendung
# ------------------------------------------------------------------------------

class GnomeBackupRestore(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id='com.guideos.gnome-backup',
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )

    def do_activate(self):
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Ubuntu-PLUS Desktop-Sicherung")
        self.window.set_default_size(620, 600)
        self.window.set_resizable(True)

        notebook = Gtk.Notebook()
        notebook.set_margin_top(10)
        notebook.set_margin_bottom(10)
        notebook.set_margin_start(10)
        notebook.set_margin_end(10)

        notebook.append_page(
            self._build_backup_tab(),
            Gtk.Label(label="💾  Sichern / Wiederherstellen"))
        notebook.append_page(
            self._build_presets_tab(),
            Gtk.Label(label="🎨  Vorlagen"))

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(notebook)
        self.window.set_child(outer)
        self.window.present()

    # ==========================================================================
    # Tab 1: Sichern / Wiederherstellen
    # ==========================================================================

    def _build_backup_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        info = Gtk.Label()
        info.set_markup("""
<span size="large" weight="bold">🔧 GNOME Desktop Backup</span>

<span weight="bold">Was wird gesichert?</span>
Alle GNOME-Einstellungen · Erweiterungen · Themes · Icons
Fonts · Hintergrundbild (hell + dunkel) · Autostart-Einträge

<span weight="bold">Wann nützlich?</span>
• Vor großen Systemänderungen
• Nach einer Neuinstallation von Ubuntu
• Zum Übertragen auf einen anderen Computer
        """)
        info.set_wrap(True)
        info.set_halign(Gtk.Align.CENTER)
        box.append(info)

        # Aktive Erweiterungen
        ext_frame = Gtk.Frame()
        ext_frame.set_margin_top(8)
        ext_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        ext_inner.set_margin_top(8)
        ext_inner.set_margin_bottom(8)
        ext_inner.set_margin_start(12)
        ext_inner.set_margin_end(12)

        hdr = Gtk.Label()
        hdr.set_markup("<span weight='bold'>🧩 Aktive Erweiterungen:</span>")
        hdr.set_halign(Gtk.Align.START)
        ext_inner.append(hdr)

        active_exts = get_active_extensions()
        if active_exts:
            for e in active_exts:
                lbl = Gtk.Label(label=f"  • {e}")
                lbl.set_halign(Gtk.Align.START)
                lbl.set_ellipsize(3)
                ext_inner.append(lbl)
        else:
            ext_inner.append(Gtk.Label(label="  Keine aktiven Erweiterungen gefunden."))

        ext_frame.set_child(ext_inner)
        box.append(ext_frame)

        # Theme-Info-Zeile
        ti = get_current_theme_info()
        theme_lbl = Gtk.Label()
        theme_lbl.set_markup(
            f"<small>🎨 <b>{ti.get('gtk-theme','–')}</b>  "
            f"🖼 <b>{ti.get('icon-theme','–')}</b>  "
            f"🖱 <b>{ti.get('cursor-theme','–')}</b></small>"
        )
        theme_lbl.set_halign(Gtk.Align.CENTER)
        theme_lbl.set_margin_top(4)
        box.append(theme_lbl)

        # Aktions-Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_top(18)
        btn_box.set_margin_bottom(10)

        b_backup = Gtk.Button(label="💾 Backup erstellen")
        b_backup.get_style_context().add_class("suggested-action")
        b_backup.set_size_request(170, 45)
        b_backup.connect("clicked", self.on_backup_clicked)
        btn_box.append(b_backup)

        b_restore = Gtk.Button(label="🔄 Backup laden")
        b_restore.get_style_context().add_class("destructive-action")
        b_restore.set_size_request(170, 45)
        b_restore.connect("clicked", self.on_restore_clicked)
        btn_box.append(b_restore)

        box.append(btn_box)

        b_quit = Gtk.Button(label="❌ Beenden")
        b_quit.set_halign(Gtk.Align.CENTER)
        b_quit.set_size_request(100, 30)
        b_quit.connect("clicked", lambda x: self.quit())
        box.append(b_quit)

        return box

    # ==========================================================================
    # Tab 2: Vorlagen
    # ==========================================================================

    def _build_presets_tab(self):
        self._preset_list_box = None

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_top(16)
        outer.set_margin_bottom(16)
        outer.set_margin_start(16)
        outer.set_margin_end(16)

        hdr = Gtk.Label()
        hdr.set_markup(
            "<span size='large' weight='bold'>🎨 Desktop-Vorlagen</span>\n\n"
            "Speichere deinen aktuellen Desktop als Vorlage und wechsle\n"
            "mit einem Klick zwischen verschiedenen Layouts.\n"
        )
        hdr.set_halign(Gtk.Align.CENTER)
        outer.append(hdr)

        # Buttons: Neue Vorlage + Import
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_box.set_halign(Gtk.Align.CENTER)
        action_box.set_margin_bottom(12)

        b_new = Gtk.Button(label="➕ Aktuelle Einstellungen speichern")
        b_new.get_style_context().add_class("suggested-action")
        b_new.connect("clicked", self.on_preset_new_clicked)
        action_box.append(b_new)

        b_import = Gtk.Button(label="📂 Backup importieren")
        b_import.connect("clicked", self.on_preset_import_clicked)
        action_box.append(b_import)

        outer.append(action_box)

        # Scrollbare Liste
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        scroll.set_min_content_height(340)

        self._preset_list_box = Gtk.ListBox()
        self._preset_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._preset_list_box.get_style_context().add_class("boxed-list")

        scroll.set_child(self._preset_list_box)
        outer.append(scroll)

        self._refresh_preset_list()
        return outer

    def _refresh_preset_list(self):
        """Vorlagen-ListBox komplett neu aufbauen."""
        while True:
            child = self._preset_list_box.get_first_child()
            if child is None:
                break
            self._preset_list_box.remove(child)

        presets = list_presets()
        if not presets:
            ph = Gtk.Label(
                label="Noch keine Vorlagen vorhanden.\n"
                      "Erstelle deine erste Vorlage mit dem Button oben!")
            ph.set_margin_top(30)
            ph.set_margin_bottom(30)
            ph.set_halign(Gtk.Align.CENTER)
            self._preset_list_box.append(ph)
            return

        for preset in presets:
            self._preset_list_box.append(self._build_preset_row(preset))

    def _build_preset_row(self, preset):
        """Zeile für eine Vorlage: Thumbnail · Infos · Buttons."""
        meta = preset["meta"]

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_margin_top(8)
        row.set_margin_bottom(8)
        row.set_margin_start(10)
        row.set_margin_end(10)

        # --- Wallpaper-Thumbnail ---
        thumb_path = os.path.join(preset["path"], WALLPAPER_THUMB)
        if os.path.exists(thumb_path):
            try:
                pb  = GdkPixbuf.Pixbuf.new_from_file_at_scale(thumb_path, 96, 54, False)
                img = Gtk.Image.new_from_pixbuf(pb)
            except Exception:
                img = Gtk.Image.new_from_icon_name("image-missing")
                img.set_pixel_size(54)
        else:
            img = Gtk.Image.new_from_icon_name("preferences-desktop-wallpaper")
            img.set_pixel_size(54)
        img.set_valign(Gtk.Align.CENTER)
        row.append(img)

        # --- Text-Infos ---
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_box.set_hexpand(True)
        info_box.set_valign(Gtk.Align.CENTER)

        name_lbl = Gtk.Label()
        name_lbl.set_markup(f"<b>{preset['name']}</b>")
        name_lbl.set_halign(Gtk.Align.START)
        info_box.append(name_lbl)

        # Datum
        created = meta.get("created", "")
        try:
            created_str = datetime.fromisoformat(created).strftime("%d.%m.%Y %H:%M")
        except Exception:
            created_str = created or "–"

        ti   = meta.get("theme_info", {})
        exts = meta.get("extensions_count", 0)
        parts = [f"📅 {created_str}"]
        if ti.get("gtk-theme"):
            parts.append(f"🎨 {ti['gtk-theme']}")
        if ti.get("icon-theme"):
            parts.append(f"🖼 {ti['icon-theme']}")
        if exts:
            parts.append(f"🧩 {exts} Erw.")
        if meta.get("imported_from"):
            parts.append("📂 Importiert")

        detail = Gtk.Label(label="  ".join(parts))
        detail.set_halign(Gtk.Align.START)
        detail.set_ellipsize(3)
        detail.get_style_context().add_class("dim-label")
        info_box.append(detail)

        row.append(info_box)

        # --- Buttons ---
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.set_valign(Gtk.Align.CENTER)

        b_apply = Gtk.Button(label="✅ Anwenden")
        b_apply.get_style_context().add_class("suggested-action")
        b_apply.connect("clicked", self.on_preset_apply_clicked, preset)
        btn_box.append(b_apply)

        b_export = Gtk.Button(label="💾")
        b_export.set_tooltip_text("Als .tar.gz exportieren")
        b_export.connect("clicked", self.on_preset_export_clicked, preset)
        btn_box.append(b_export)

        b_del = Gtk.Button(label="🗑")
        b_del.set_tooltip_text("Vorlage löschen")
        b_del.get_style_context().add_class("destructive-action")
        b_del.connect("clicked", self.on_preset_delete_clicked, preset)
        btn_box.append(b_del)

        row.append(btn_box)
        return row

    # ==========================================================================
    # Vorlagen-Aktionen
    # ==========================================================================

    def on_preset_new_clicked(self, button):
        """Namen-Dialog → Vorlage aus aktuellem Desktop speichern."""
        dialog = Gtk.Dialog(
            title="Neue Vorlage erstellen",
            transient_for=self.window, modal=True)
        dialog.set_default_size(360, 150)
        dialog.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        b_ok = dialog.add_button("Speichern", Gtk.ResponseType.OK)
        b_ok.get_style_context().add_class("suggested-action")

        content = dialog.get_content_area()
        content.set_spacing(10)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.append(Gtk.Label(label="Name der Vorlage:"))

        entry = Gtk.Entry()
        entry.set_placeholder_text("z.B. Arbeit, Dunkel, Minimal …")
        entry.set_text(f"Vorlage {datetime.now().strftime('%d.%m.%Y')}")
        entry.connect("activate", lambda e: dialog.response(Gtk.ResponseType.OK))
        content.append(entry)

        dialog.connect("response", self._on_preset_new_response, entry)
        dialog.show()

    def _on_preset_new_response(self, dialog, response, entry):
        name = entry.get_text().strip()
        dialog.destroy()
        if response == Gtk.ResponseType.OK and name:
            self.show_progress("Vorlage wird erstellt…", self._do_save_preset, name)

    def _do_save_preset(self, name, cancel_flag=None):
        r = save_preset(name, cancel_flag)
        if r["success"]:
            GLib.idle_add(self._refresh_preset_list)
            return {"success": True, "title": "✅ Vorlage gespeichert!",
                    "text": f'„{r["name"]}“ wurde erstellt.\n'
                            f'Erweiterungen gesichert: {r["ext_count"]}'}
        return {"success": False, "title": "Fehler", "text": r.get("text", "Unbekannter Fehler.")}

    # -- Import ----------------------------------------------------------------

    def on_preset_import_clicked(self, button):
        fd = Gtk.FileDialog.new()
        fd.set_title("Backup-Datei auswählen (.tar.gz)")
        f = Gtk.FileFilter()
        f.set_name("TAR-Archive (*.tar.gz)")
        f.add_pattern("*.tar.gz")
        ls = Gio.ListStore.new(Gtk.FileFilter)
        ls.append(f)
        fd.set_filters(ls)
        fd.open(self.window, None, self._on_import_tar_selected)

    def _on_import_tar_selected(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if not file:
                return
            tar_path = file.get_path()
        except GLib.GError:
            return

        nd = Gtk.Dialog(title="Vorlage benennen",
                        transient_for=self.window, modal=True)
        nd.set_default_size(360, 150)
        nd.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        b = nd.add_button("Importieren", Gtk.ResponseType.OK)
        b.get_style_context().add_class("suggested-action")

        c = nd.get_content_area()
        c.set_spacing(10)
        c.set_margin_top(16)
        c.set_margin_bottom(16)
        c.set_margin_start(16)
        c.set_margin_end(16)
        c.append(Gtk.Label(label="Name für die importierte Vorlage:"))

        entry = Gtk.Entry()
        base = os.path.basename(tar_path).replace(".tar.gz", "").replace(".tar", "")
        entry.set_text(base)
        entry.connect("activate", lambda e: nd.response(Gtk.ResponseType.OK))
        c.append(entry)

        nd.connect("response", self._on_import_name_response, entry, tar_path)
        nd.show()

    def _on_import_name_response(self, dialog, response, entry, tar_path):
        name = entry.get_text().strip()
        dialog.destroy()
        if response == Gtk.ResponseType.OK and name:
            self.show_progress("Vorlage wird importiert…",
                               self._do_import_preset, tar_path, name)

    def _do_import_preset(self, tar_path, name, cancel_flag=None):
        r = import_preset_from_tar(tar_path, name, cancel_flag)
        if r["success"]:
            GLib.idle_add(self._refresh_preset_list)
            return {"success": True, "title": "✅ Importiert!",
                    "text": f'„{r["name"]}“ wurde importiert.\n'
                            f'Erweiterungen: {r["ext_count"]}'}
        return {"success": False, "title": "Fehler", "text": r.get("text", "Unbekannter Fehler.")}

    # -- Anwenden --------------------------------------------------------------

    def on_preset_apply_clicked(self, button, preset):
        d = self.show_message_dialog(
            f'Vorlage „{preset["name"]}“ anwenden?',
            "Deine aktuellen Desktop-Einstellungen werden überschrieben.\n\nMöchtest du fortfahren?",
            is_question=True)
        d.connect("response", self._on_preset_apply_confirm, preset)
        d.show()

    def _on_preset_apply_confirm(self, dialog, response, preset):
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.show_progress(
                f'Vorlage „{preset["name"]}“ wird angewendet…',
                self._do_apply_preset, preset["path"])

    def _do_apply_preset(self, preset_path, cancel_flag=None):
        r = apply_preset(preset_path, cancel_flag)
        if r["success"]:
            return {"success": True, "title": "✅ Vorlage angewendet!",
                    "text": (f"Desktop wurde umgestellt.\n"
                             f"Erweiterungen wiederhergestellt: {r['restored']}\n"
                             f"Erweiterungen aktiviert: {r['reactivated']}\n\n"
                             "Tipp: Alt+F2 → 'r' → Enter zum Neuladen der GNOME-Shell.")}
        return {"success": False, "title": "Fehler", "text": r.get("text", "Unbekannter Fehler.")}

    # -- Export ----------------------------------------------------------------

    def on_preset_export_clicked(self, button, preset):
        fd = Gtk.FileDialog.new()
        fd.set_title("Vorlage exportieren als…")
        gfile = Gio.File.new_for_path(
            os.path.join(os.path.expanduser("~"), f"{preset['name']}.tar.gz"))
        fd.set_initial_file(gfile)
        fd.save(self.window, None, lambda d, r: self._on_export_save(d, r, preset))

    def _on_export_save(self, dialog, result, preset):
        try:
            file = dialog.save_finish(result)
            if not file:
                return
            dest = file.get_path()
        except GLib.GError:
            return
        try:
            shutil.copy(os.path.join(preset["path"], "desktop.tar.gz"), dest)
            self.show_message_dialog("✅ Exportiert!", f"Vorlage gespeichert:\n{dest}")
        except Exception as e:
            self.show_message_dialog("Fehler", str(e), is_error=True)

    # -- Löschen ---------------------------------------------------------------

    def on_preset_delete_clicked(self, button, preset):
        d = self.show_message_dialog(
            f'Vorlage „{preset["name"]}“ löschen?',
            "Die Vorlage wird unwiderruflich gelöscht.",
            is_question=True)
        d.connect("response", self._on_preset_delete_confirm, preset)
        d.show()

    def _on_preset_delete_confirm(self, dialog, response, preset):
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            try:
                shutil.rmtree(preset["path"])
            except Exception as e:
                self.show_message_dialog("Fehler", str(e), is_error=True)
                return
            self._refresh_preset_list()

    # ==========================================================================
    # Tab 1: Backup / Restore Callbacks
    # ==========================================================================

    def on_backup_clicked(self, button):
        d = self.show_message_dialog(
            "Desktop sichern?",
            "Backup deines GNOME-Desktops erstellen?\n"
            "(Einstellungen · Erweiterungen · Themes · Icons · Wallpaper)",
            is_question=True)
        d.connect("response", self._on_backup_confirm)
        d.show()

    def _on_backup_confirm(self, dialog, response):
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        fd = Gtk.FileDialog.new()
        fd.set_title("Backup speichern unter…")
        name = f"Ubuntu-PLUS-Desktop_{datetime.now().strftime('%Y-%m-%d')}.tar.gz"
        gfile = Gio.File.new_for_path(os.path.join(os.path.expanduser("~"), name))
        fd.set_initial_file(gfile)
        fd.save(self.window, None, self._on_backup_file_selected)

    def _on_backup_file_selected(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            if file:
                self.show_progress("Backup wird erstellt…", self._do_backup, file.get_path())
        except GLib.GError:
            pass

    def _do_backup(self, speicherort, cancel_flag=None):
        try:
            tmpdir = tempfile.mkdtemp()
            meta = _collect_into_tmpdir(tmpdir, cancel_flag)
            if meta is None:
                shutil.rmtree(tmpdir)
                return {"success": False, "title": "Abgebrochen", "text": "Sicherung abgebrochen."}
            _build_tar(speicherort, tmpdir)
            shutil.rmtree(tmpdir)
            return {"success": True, "title": "✅ Fertig!",
                    "text": f"Backup gespeichert:\n{speicherort}\n\n"
                            f"Erweiterungen gesichert: {meta['extensions_count']}"}
        except Exception as e:
            return {"success": False, "title": "Fehler", "text": f"Backup fehlgeschlagen:\n{e}"}

    def on_restore_clicked(self, button):
        d = self.show_message_dialog(
            "⚠️ Achtung!",
            "Die Wiederherstellung überschreibt deine aktuellen GNOME-Einstellungen.\n\nFortfahren?",
            is_question=True)
        d.connect("response", self._on_restore_confirm)
        d.show()

    def _on_restore_confirm(self, dialog, response):
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        fd = Gtk.FileDialog.new()
        fd.set_title("Backup-Datei auswählen")
        fd.open(self.window, None, self._on_restore_file_selected)

    def _on_restore_file_selected(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file:
                self.show_progress("Wiederherstellung läuft…", self._do_restore, file.get_path())
        except GLib.GError:
            pass

    def _do_restore(self, backup_file, cancel_flag=None):
        try:
            tmpdir = tempfile.mkdtemp()
            subprocess.run(['tar', '-xzf', backup_file, '-C', tmpdir], stderr=subprocess.DEVNULL)
            if cancel_flag and cancel_flag.is_set():
                shutil.rmtree(tmpdir)
                return {"success": False, "title": "Abgebrochen", "text": "Abgebrochen."}
            restored, reactivated = _restore_from_tmpdir(tmpdir, cancel_flag)
            shutil.rmtree(tmpdir)
            ext_info = (f"\nErweiterungen wiederhergestellt: {restored}"
                        f"\nErweiterungen aktiviert: {reactivated}") if restored else ""
            return {"success": True, "title": "✅ Fertig!",
                    "text": ("Desktop wiederhergestellt!" + ext_info +
                             "\n\nTipp: Alt+F2 → 'r' → Enter zum Neuladen.")}
        except Exception as e:
            return {"success": False, "title": "Fehler", "text": f"Fehler:\n{e}"}

    # ==========================================================================
    # Dialog-Hilfsmethoden
    # ==========================================================================

    def show_message_dialog(self, title, text, is_error=False, is_question=False):
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            modal=True, text=title, secondary_text=text)
        if is_question:
            dialog.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
            b = dialog.add_button("Ja", Gtk.ResponseType.OK)
            b.get_style_context().add_class("destructive-action")
            return dialog
        b = dialog.add_button("OK", Gtk.ResponseType.OK)
        if is_error:
            b.get_style_context().add_class("destructive-action")
        else:
            b.get_style_context().add_class("suggested-action")
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.show()
        return None

    def show_progress(self, title, callback, *args):
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            modal=True, text=title, secondary_text="Bitte warten…")
        spinner = Gtk.Spinner()
        spinner.start()
        spinner.set_margin_top(10)
        dialog.get_content_area().append(spinner)
        dialog.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        dialog.show()

        cancel_flag = threading.Event()

        def on_resp(d, resp):
            if resp == Gtk.ResponseType.CANCEL:
                cancel_flag.set()
                d.destroy()

        dialog.connect("response", on_resp)

        def run():
            result = callback(*args, cancel_flag)
            GLib.idle_add(lambda: self.on_progress_done(dialog, result))

        threading.Thread(target=run, daemon=True).start()

    def on_progress_done(self, dialog, result):
        dialog.destroy()
        if result and result.get("success"):
            self.show_message_dialog(result["title"], result["text"])
        elif result:
            self.show_message_dialog(
                result.get("title", "Fehler"),
                result.get("text", ""),
                is_error=True)


# ------------------------------------------------------------------------------
# Start
# ------------------------------------------------------------------------------

def main():
    app = GnomeBackupRestore()
    app.run(None)


if __name__ == "__main__":
    main()
