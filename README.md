
## Ubuntu-PLUS Desktop-Sicherung 

Version: 1.2*

Entwickler: evilware666 & Helga

## **Überblick**
Das Ubuntu-PLUS Desktop-Sicherung-Tool ist ein modernes GTK4‑Tool, das deinen kompletten GNOME‑Desktop sichern, wiederherstellen und als wiederverwendbare Vorlagen speichern kann.  
Ideal für Systemwechsel, Neuinstallationen oder das schnelle Umschalten zwischen Desktop‑Layouts.

---

## **Funktionen**

### **🔒 Backup**
Sichert deinen gesamten GNOME‑Desktop:
- GNOME‑Einstellungen (dconf‑Dump)
- GNOME‑Shell‑Erweiterungen + Konfiguration
- Themes, Icons, GTK‑Einstellungen, Fonts
- Hintergrundbilder (hell + dunkel)
- Autostart‑Einträge
- Benutzer‑Erweiterungen (`~/.local/share/gnome-shell/extensions`)

Ergebnis: **Eine .tar.gz‑Datei**, die jederzeit wiederhergestellt werden kann.

---

### **🔄 Restore**
Stellt ein Backup vollständig wieder her:
- Alle GNOME‑Einstellungen
- Erweiterungen + automatische Reaktivierung
- Themes, Icons, GTK‑Configs
- Wallpaper (hell/dunkel)
- Autostart‑Einträge

Perfekt nach Neuinstallationen oder Systemwechseln.

---

## **🎨 NEU in Version 2.1 – Vorlagen‑System**
Mit Version 1.1 wurde ein vollständiges **Preset‑System** integriert:

### **Vorlagen speichern**
- Speichere deinen aktuellen Desktop als **benannte Vorlage**
- Automatische Metadaten:
  - Datum
  - aktives GTK‑Theme, Icon‑Theme, Cursor‑Theme
  - Anzahl aktiver Erweiterungen
- Automatische Wallpaper‑Thumbnail‑Erstellung (96×54 px)

### **Vorlagen anwenden**
- Ein Klick → kompletter Desktop wird auf die Vorlage umgestellt  
  (inkl. Erweiterungen, Themes, Wallpaper, GTK‑Settings)

### **Vorlagen importieren**
- Importiere externe `.tar.gz`‑Backups als Vorlage
- Automatische Thumbnail‑Erstellung
- Metadaten werden übernommen

### **Vorlagen exportieren**
- Jede Vorlage kann als `.tar.gz` exportiert werden  
  → ideal zum Teilen oder Archivieren

### **Vorlagen löschen**
- Vollständiges Entfernen inkl. Metadaten & Thumbnail

---

## **Technische Details**
- Speichert Daten in:  
  `~/.local/share/guideos/gnome-presets/`
- Konfigurationsdatei:  
  `~/.local/share/guideos/gnome-backup-config.json`
- Unterstützt GTK4, libadwaita, GdkPixbuf
- Nutzt `dconf`, `rsync`, `tar`, `gsettings`, `ffmpeg` (für Thumbnails)

---

## **Systemvoraussetzungen**
- GNOME Desktop (40+)
- GuideOS, Ubuntu, Debian oder kompatible Distribution
- Installierte Tools:
  - `dconf`
  - `rsync`
  - `tar`
  - `gsettings`
  - `ffmpeg` (für Thumbnails)

---

## **Lizenz**
MIT-Lizenz  

