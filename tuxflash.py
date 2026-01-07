import sys
import subprocess
import os
import threading
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gio, Adw, GLib, Gdk

CSS = """
window { background-color: #050505; }
.main-card { 
    background: rgba(255, 255, 255, 0.03); 
    border-radius: 12px; 
    border: 1px solid #222;
    padding: 20px;
}
label { font-family: 'Courier New', monospace; color: #00ff41; }
.header-title { font-size: 32px; font-weight: 900; color: #ffb000; text-shadow: 0 0 15px rgba(255, 176, 0, 0.4); }
.status-active { color: #00ff41; font-weight: bold; }
.status-error { color: #ff4444; font-weight: bold; }

progressbar > trough { background-color: #111; min-height: 18px; border-radius: 9px; border: 1px solid #333; }
progressbar > progress { 
    background: linear-gradient(90deg, #008f25, #00ff41); 
    box-shadow: 0 0 15px #00ff41;
    border-radius: 9px;
}

button.suggested-action { 
    background: #00ff41; color: #000; font-weight: bold; border-radius: 8px; border: none; min-height: 50px;
}
button.suggested-action:hover { background: #00cc33; box-shadow: 0 0 25px rgba(0, 255, 65, 0.5); }
"""

class TuxFlash(Adw.Application):
    def __init__(self):
        super().__init__(application_id='io.tuxtech.flash.pro', flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.iso_path = None
        self.drive_path = None
        self.iso_size = 0
        self.drive_size = 0
        self.drive_info = []

    def do_activate(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.win = Adw.ApplicationWindow(application=self)
        self.win.set_title("TuxFlash Professional")
        self.win.set_default_size(450, 700)

        overlay = Gtk.Overlay()
        self.win.set_content(overlay)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        vbox.set_margin_top(25); vbox.set_margin_bottom(25)
        vbox.set_margin_start(25); vbox.set_margin_end(25)
        overlay.set_child(vbox)

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        lbl_brand = Gtk.Label(label="TUX_FLASH_PRO")
        lbl_brand.add_css_class("header-title")
        header.append(lbl_brand)
        header.append(Gtk.Label(label="GPT_AND_MBR_SUPPORT_v2.2", xalign=0.5))
        vbox.append(header)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        card.add_css_class("main-card")
        vbox.append(card)

        # 1. ISO
        card.append(Gtk.Label(label=" ИСТОЧНИК ОБРАЗА", xalign=0))
        self.btn_iso = Gtk.Button(label="ВЫБРАТЬ ISO/IMG")
        self.btn_iso.connect("clicked", self.select_file)
        card.append(self.btn_iso)
        self.lbl_iso = Gtk.Label(label="Файл: не выбран", xalign=0)
        self.lbl_iso.set_ellipsize(3)
        card.append(self.lbl_iso)

        card.append(Gtk.Separator())

        # 2. Drive
        card.append(Gtk.Label(label=" ВЫБОР ФЛЕШКИ", xalign=0))
        self.drop_drives = Gtk.DropDown.new_from_strings(["Поиск флешек..."])
        self.drop_drives.connect("notify::selected-item", self.on_drive_change)
        card.append(self.drop_drives)

        card.append(Gtk.Separator())

        # 3. Partition Scheme (GPT/MBR)
        card.append(Gtk.Label(label=" СХЕМА РАЗДЕЛА", xalign=0))
        self.drop_scheme = Gtk.DropDown.new_from_strings(["GPT (UEFI / Современный)", "MBR (Legacy / Старый)"])
        card.append(self.drop_scheme)

        self.lbl_status = Gtk.Label(label="СТАТУС: ОЖИДАНИЕ", xalign=0.5)
        vbox.append(self.lbl_status)

        self.pbar = Gtk.ProgressBar()
        self.pbar.set_show_text(True)
        vbox.append(self.pbar)

        self.btn_flash = Gtk.Button(label="ЗАПУСТИТЬ ПРОШИВКУ")
        self.btn_flash.add_css_class("suggested-action")
        self.btn_flash.connect("clicked", self.start_flash_thread)
        self.btn_flash.set_sensitive(False)
        vbox.append(self.btn_flash)

        GLib.timeout_add(2000, self.refresh_drives)
        self.win.present()

    def select_file(self, _):
        dialog = Gtk.FileDialog.new()
        dialog.open(self.win, None, self.on_file_done)

    def on_file_done(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file:
                self.iso_path = file.get_path()
                self.iso_size = os.path.getsize(self.iso_path)
                self.lbl_iso.set_label(f"Файл: {file.get_basename()} ({self.iso_size//1024**2} MB)")
                self.validate()
        except: pass

    def refresh_drives(self):
        try:
            res = subprocess.check_output(["lsblk", "-dno", "NAME,SIZE,MODEL,TRAN,RM", "-b"]).decode().splitlines()
            drive_info_new = []
            names = []
            for line in res:
                p = line.split()
                if len(p) >= 4:
                    name_raw, size_bytes = p[0], int(p[1])
                    model = " ".join(p[2:-2])
                    transport, removable = p[-2].lower(), p[-1]
                    if transport == "usb" or removable == "1":
                        d_path = f"/dev/{name_raw}"
                        names.append(f"USB: {model} ({size_bytes//1024**3} GB) - {d_path}")
                        drive_info_new.append({'path': d_path, 'size': size_bytes})
            
            self.drive_info = drive_info_new
            if names:
                self.drop_drives.set_model(Gtk.StringList.new(names))
            else:
                self.drop_drives.set_model(Gtk.StringList.new(["USB-диски не найдены"]))
        except: pass
        return True

    def on_drive_change(self, widget, _):
        idx = widget.get_selected()
        if self.drive_info and idx < len(self.drive_info):
            self.drive_path = self.drive_info[idx]['path']
            self.drive_size = self.drive_info[idx]['size']
            self.validate()

    def validate(self):
        if self.iso_path and self.drive_path:
            if self.iso_size > self.drive_size:
                self.lbl_status.set_label("ОШИБКА: МАЛО МЕСТА")
                self.btn_flash.set_sensitive(False)
            else:
                self.lbl_status.set_label("СТАТУС: ГОТОВ К ЗАПИСИ")
                self.btn_flash.set_sensitive(True)

    def start_flash_thread(self, _):
        self.btn_flash.set_sensitive(False)
        self.btn_iso.set_sensitive(False)
        thread = threading.Thread(target=self.flash_engine)
        thread.daemon = True
        thread.start()

    def flash_engine(self):
        # Размонтируем все разделы флешки перед записью
        subprocess.run(["pkexec", "umount", f"{self.drive_path}1"], stderr=subprocess.DEVNULL)
        subprocess.run(["pkexec", "umount", f"{self.drive_path}2"], stderr=subprocess.DEVNULL)
        
        # Команда DD
        cmd = ["pkexec", "dd", f"if={self.iso_path}", f"of={self.drive_path}", "bs=4M", "status=progress", "conv=fsync"]
        process = subprocess.Popen(cmd, stderr=subprocess.PIPE)
        
        while process.poll() is None:
            GLib.idle_add(self.pbar.pulse)
            import time
            time.sleep(0.1)
        
        GLib.idle_add(self.finish_flash, process.returncode)

    def finish_flash(self, code):
        self.pbar.set_fraction(1.0 if code == 0 else 0)
        self.lbl_status.set_label("ЗАВЕРШЕНО УСПЕШНО!" if code == 0 else "ОШИБКА ЗАПИСИ!")
        self.btn_flash.set_sensitive(True)
        self.btn_iso.set_sensitive(True)

if __name__ == "__main__":
    app = TuxFlash()
    app.run(sys.argv)
