"""
Kai Desktop Pet (Shimeji-style)
Font: Auto-detects any .ttf/.otf in assets/fonts/ (e.g. BeVietnamPro-Regular.ttf),
with automatic fallback to Windows Segoe UI / Arial for 100% Vietnamese safety.
"""

import ctypes
import datetime
import glob
import math
import os
import random
import sys
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

if sys.platform == "win32":
    import winreg
    from ctypes import wintypes

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    _user32.MonitorFromPoint.restype = wintypes.HMONITOR
    _user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
    _user32.GetMonitorInfoW.restype = wintypes.BOOL
    _user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetAncestor.restype = wintypes.HWND
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    _user32.SetWindowPos.restype = wintypes.BOOL
else:
    winreg = None
    _user32 = None

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk


RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "HungDesktopPet"
AUTOSTART_OFF_FLAG = os.path.join(os.path.expanduser("~"), ".hung_pet_no_autostart")


def get_startup_command() -> str:
    """Return command registered in Windows Run key for auto-start."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{os.path.abspath(__file__)}"'


def is_startup_enabled() -> bool:
    """Check whether HungDesktopPet is enabled in HKCU Run registry."""
    if sys.platform != "win32" or winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            val, _typ = winreg.QueryValueEx(key, RUN_VALUE_NAME)
            return bool(str(val).strip())
    except OSError:
        return False


def set_startup_enabled(enable: bool) -> bool:
    """Enable or disable Windows startup via HKCU Run registry."""
    if sys.platform != "win32" or winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, get_startup_command())
                if os.path.exists(AUTOSTART_OFF_FLAG):
                    try:
                        os.remove(AUTOSTART_OFF_FLAG)
                    except OSError:
                        pass
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE_NAME)
                except FileNotFoundError:
                    pass
                try:
                    with open(AUTOSTART_OFF_FLAG, "w", encoding="utf-8") as f:
                        f.write("off")
                except OSError:
                    pass
        return True
    except OSError:
        return False


def ensure_default_startup() -> None:
    """Auto-enable Windows startup on first packaged EXE launch unless opted out."""
    if getattr(sys, "frozen", False) and not os.path.exists(AUTOSTART_OFF_FLAG):
        set_startup_enabled(True)


def resource_path(relative_path: str) -> str:
    """Resolve path for both dev mode and PyInstaller --onefile."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)


def find_font_file() -> Optional[str]:
    """Find and register .ttf/.otf in assets/fonts/, else fall back to Windows system fonts."""
    fonts_dir = resource_path(os.path.join("assets", "fonts"))
    if os.path.isdir(fonts_dir):
        candidates = sorted(
            glob.glob(os.path.join(fonts_dir, "*.ttf"))
            + glob.glob(os.path.join(fonts_dir, "*.otf"))
        )
        if candidates:
            if sys.platform == "win32":
                FR_PRIVATE = 0x10
                for font_file in candidates:
                    try:
                        ctypes.windll.gdi32.AddFontResourceExW(font_file, FR_PRIVATE, 0)
                    except Exception:
                        pass
            for preferred in ("Quicksand-SemiBold.ttf", "Quicksand-Regular.ttf"):
                p = os.path.join(fonts_dir, preferred)
                if os.path.exists(p):
                    return p
            return candidates[0]

    for sys_font in (
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\tahoma.ttf",
    ):
        if os.path.exists(sys_font):
            return sys_font
    return None


def get_work_area(
    root: tk.Tk, point_x: Optional[float] = None, point_y: Optional[float] = None
) -> Tuple[int, int, int, int]:
    """Return usable desktop bounds (left, top, right, bottom) of the monitor at point."""
    if sys.platform == "win32" and _user32 is not None:
        try:
            if point_x is not None and point_y is not None:
                hmon = _user32.MonitorFromPoint(wintypes.POINT(int(point_x), int(point_y)), 2)
                mi = _MONITORINFO()
                mi.cbSize = ctypes.sizeof(_MONITORINFO)
                if hmon and _user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                    return mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom

            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def clamp_to_monitor(
    root: tk.Tk, x: float, y: float, w: int, h: int, ref_x: float, ref_y: float
) -> Tuple[int, int]:
    """Clamp window (x, y) inside the usable work area of the monitor containing (ref_x, ref_y)."""
    wl, wt, wr, wb = get_work_area(root, ref_x, ref_y)
    cx = max(wl + 8, min(int(x), wr - w - 8))
    cy = max(wt + 8, min(int(y), wb - h - 8))
    return cx, cy


def keep_window_topmost(win: Optional[tk.Misc]) -> None:
    """Re-assert topmost Z-order without activating or stealing focus."""
    if win is None:
        return
    try:
        if sys.platform == "win32" and _user32 is not None:
            hwnd = _user32.GetAncestor(win.winfo_id(), 2) or win.winfo_id()
            _user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        else:
            win.wm_attributes("-topmost", True)
    except Exception:
        pass


def prep_photo(
    pil_img: Image.Image,
    size: Tuple[int, int],
    chroma_rgb: Tuple[int, int, int] = (1, 1, 1),
    for_canvas: bool = False,
) -> ImageTk.PhotoImage:
    """Resize RGBA image and threshold alpha cleanly for Windows -transparentcolor."""
    resized = pil_img.resize(size, Image.Resampling.LANCZOS).convert("RGBA")
    if sys.platform == "win32":
        r, g, b, a = resized.split()
        a = a.point(lambda p: 255 if p >= 95 else 0)
        merged = Image.merge("RGBA", (r, g, b, a))
        if for_canvas:
            cleaned = Image.new("RGBA", size, (0, 0, 0, 0))
            cleaned.paste(merged, (0, 0), a)
            return ImageTk.PhotoImage(cleaned)
        bg = Image.new("RGBA", size, chroma_rgb + (255,))
        bg.paste(merged, (0, 0), merged)
        return ImageTk.PhotoImage(bg.convert("RGB"))
    return ImageTk.PhotoImage(resized)


CLICK_MESSAGES = [
    "Cậu vẫn ổn chứ?",
    "Hôm nay của cậu thế nào rồi ạ?",
    "Nhớ tớ rồi đúng không?",
    "Mệt không đó, nghỉ ngơi xíu nha!",
]

LOVE_MESSAGES = [
    "Yêu cậu nhiều lắm đó!",
    "Thương vợ iu của tớ nhất ><",
    "Tớ chỉ thích mình cậu thôi~",
    "Cảm ơn cậu vì đã đến bên tớ!",
]

DAYDREAM_MESSAGES = [
    "Đang tơ tưởng về cậu...",
    "Không biết giờ này cậu đang làm gì nhỉ?",
    "Trong đầu tớ toàn là hình bóng cậu~",
    "Nhớ nụ cười của cậu quá đi...",
]

QA_CONVERSATIONS = [
    {
        "question": "Cậu vẫn ổn chứ?",
        "options": [
            ("Tớ ổn ạ", "Cậu ổn là tớ yên tâm rồi, cố lên nha!", "happy"),
            ("Tớ nhớ cậu", "Tớ cũng nhớ cậu điên lên được ><", "love"),
            ("Tớ đang muốn gặp cậu", "Chờ tớ nhé, tớ phi qua ôm cậu ngay đây!", "daydream"),
        ],
    },
    {
        "question": "Hôm nay của cậu thế nào rồi ạ?",
        "options": [
            ("Vui lắm cậu ơi", "Nghe cậu vui là tớ cũng cười cả ngày luôn~", "happy"),
            ("Hơi mệt một xíu...", "Thương thế... Lại đây tớ xoa đầu nạp pin cho cậu nha!", "love"),
            ("Chỉ muốn ở cạnh cậu", "Nghe xong đỏ hết cả mặt rồi này ><", "shy"),
        ],
    },
    {
        "question": "Đố cậu biết tớ đang nghĩ gì đó?",
        "options": [
            ("Đang nghĩ về tớ chứ gì", "Sao cậu đoán trúng tim đen của tớ thế!", "daydream"),
            ("Đang đói bụng à?", "Đói thật... nhưng vẫn thích ngắm cậu hơn!", "happy"),
            ("Thương tớ không?", "Thương vợ iu của tớ nhất trên đời ><", "love"),
        ],
    },
    {
        "question": "Mệt không đó, nghỉ ngơi xíu nha!",
        "options": [
            ("Tớ nghỉ ngơi đây", "Ngoan lắm, uống thêm ngụm nước ấm nữa nha!", "happy"),
            ("Ôm tớ một cái đi", "Ôm chặt cứng luôn, hết mệt chưa nào~", "love"),
            ("Kể chuyện cho tớ nghe", "Ngày xửa ngày xưa, có một người siêu thích cậu đó...", "daydream"),
        ],
    },
]

CARE_ITEMS = [
    ("Trà sữa full topping", "Trà sữa cậu mời ngọt ngang nụ cười của cậu luôn~", "headpat"),
    ("Đồ ăn vặt ngon lành", "No cái bụng rồi, cảm ơn cậu yêu nhiều nha!", "happy"),
    ("Ôm chặt một cái", "Được cậu ôm một cái là tớ đầy 100% pin luôn ><", "love"),
    ("Hôn má cái chóc", "Ngại quá đi mất... tim tớ đập thình thịch rồi này!", "shy"),
]

SECRET_LOVE_NOTES = [
    "Gửi cậu,\nCảm ơn cậu đã luôn xuất hiện, vẽ cho tớ một phiên bản thật đáng yêu và ở bên cạnh tớ mỗi ngày. Dù bận thế nào nhớ uống nước và giữ gìn sức khỏe nhé!",
    "Kai iu dấu của tớ, có mệt mỏi muộn phiền thì hãy dựa vào tớ nhiều nhé! Tớ sẽ ở đây và lắng nghe cậu mọi lúc ạ. Yêu và thương cậu vô điều kiện suốt đời!",
    "Mỗi lúc cậu mệt hay áp lực, cứ bấm vào tớ trên màn hình nha. Tớ lúc nào cũng đứng ở góc nhỏ này chờ lắng nghe và thương cậu thật nhiều!",
    "Thương vợ iu của tớ nhất trên đời! Chúc cậu hôm nay thật nhiều niềm vui và luôn mỉm cười thật tươi như lúc cậu đang đọc những dòng này nhé ><",
]


@dataclass
class FxParticle:
    x: float
    y: float
    vx: float
    vy: float
    gravity: float
    life: int
    max_life: int
    img_key: str
    sway_phase: float


class AttachedBubble:
    """Pill-shaped pastel speech bubble (blue or pink) with Vietnamese-safe font."""

    CHROMA = "#010101"

    def __init__(self, parent: tk.Tk, font_path: Optional[str], pet: Optional["KaiDesktopPet"] = None):
        self.parent = parent
        self.font_path = font_path
        self.pet = pet
        self.win: Optional[tk.Toplevel] = None
        self.after_id: Optional[str] = None
        self.photo: Optional[ImageTk.PhotoImage] = None

    def show(
        self,
        text: str,
        anchor_x: float,
        anchor_y: float,
        pet_w: int,
        style: str = "blue",
        duration_ms: int = 3400,
    ) -> None:
        self.hide()
        bw = tk.Toplevel(self.parent)
        bw.overrideredirect(True)
        bw.wm_attributes("-topmost", True)
        bw.configure(bg=self.CHROMA)
        if sys.platform == "win32":
            bw.wm_attributes("-transparentcolor", self.CHROMA)
        elif sys.platform == "darwin":
            bw.wm_attributes("-transparent", True)

        bg_color = "#BCE6FF" if style == "blue" else "#FFD1E3"
        border_color = "#94D4FA" if style == "blue" else "#F7A8C8"
        text_color = "#1E293B" if style == "blue" else "#5C1D38"

        try:
            pil_font = (
                ImageFont.truetype(self.font_path, 15)
                if self.font_path
                else ImageFont.load_default()
            )
        except Exception:
            pil_font = ImageFont.load_default()

        dummy = Image.new("RGBA", (10, 10))
        d = ImageDraw.Draw(dummy)
        bbox = d.textbbox((0, 0), text, font=pil_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        pad_x, pad_y = 18, 10
        w = max(90, tw + pad_x * 2)
        h = max(38, th + pad_y * 2)

        img = Image.new("RGBA", (w + 4, h + 4), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [1, 1, w + 1, h + 1],
            radius=h // 2,
            fill=bg_color,
            outline=border_color,
            width=2,
        )
        tx = (w + 2 - tw) / 2 - bbox[0]
        ty = (h + 2 - th) / 2 - bbox[1] - 1
        draw.text((tx, ty), text, font=pil_font, fill=text_color)

        self.photo = prep_photo(img, (w + 4, h + 4))
        lbl = tk.Label(bw, image=self.photo, bg=self.CHROMA, bd=0)
        lbl.pack()

        self.win = bw
        self.reposition(anchor_x, anchor_y, pet_w, w + 4, h + 4)
        self.after_id = self.parent.after(duration_ms, self.hide)

    def reposition(
        self,
        pet_x: float,
        pet_y: float,
        pet_w: int,
        bw_w: Optional[int] = None,
        bw_h: Optional[int] = None,
    ) -> None:
        if self.win is None:
            return
        try:
            w = bw_w or self.win.winfo_width()
            h = bw_h or self.win.winfo_height()
            extra_lift = 0
            if self.pet is not None:
                if self.pet.thought_popup is not None and self.pet.thought_popup.win is not None:
                    extra_lift = 120
                elif self.pet.heart_popup is not None and self.pet.heart_popup.win is not None:
                    extra_lift = 66
            x = int(pet_x + pet_w / 2 - w / 2)
            y = int(pet_y - h + 4 - extra_lift)
            x, y = clamp_to_monitor(self.parent, x, y, w, h, pet_x + pet_w / 2, pet_y)
            self.win.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def hide(self) -> None:
        if self.after_id is not None:
            try:
                self.parent.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        if self.win is not None:
            try:
                self.win.destroy()
            except Exception:
                pass
            self.win = None


class FloatingImagePopup:
    """Attached transparent floating image popup with gentle pop-and-bob animation."""

    CHROMA = "#010101"

    def __init__(
        self,
        parent: tk.Tk,
        pil_img: Image.Image,
        img_size: Tuple[int, int] = (64, 58),
        duration_ms: int = 2400,
        max_steps: int = 60,
    ):
        self.parent = parent
        self.base_img = pil_img
        self.img_size = img_size
        self.duration_ms = duration_ms
        self.max_steps = max_steps
        self.win: Optional[tk.Toplevel] = None
        self.after_id: Optional[str] = None
        self.anim_id: Optional[str] = None
        self.photo: Optional[ImageTk.PhotoImage] = None
        self.step = 0

    def _compute_pos(
        self, pet_x: float, pet_y: float, pet_w: int, pop_offset: float, bob: float
    ) -> Tuple[int, int]:
        x = int(pet_x + pet_w / 2 - self.img_size[0] / 2)
        y = int(pet_y - self.img_size[1] + 4 + pop_offset + bob)
        return clamp_to_monitor(
            self.parent, x, y, self.img_size[0], self.img_size[1], pet_x + pet_w / 2, pet_y
        )

    def show(self, pet_x: float, pet_y: float, pet_w: int) -> None:
        self.hide()
        bw = tk.Toplevel(self.parent)
        bw.overrideredirect(True)
        bw.wm_attributes("-topmost", True)
        bw.configure(bg=self.CHROMA)
        if sys.platform == "win32":
            bw.wm_attributes("-transparentcolor", self.CHROMA)
        elif sys.platform == "darwin":
            bw.wm_attributes("-transparent", True)

        self.photo = prep_photo(self.base_img, self.img_size)
        self.lbl = tk.Label(bw, image=self.photo, bg=self.CHROMA, bd=0)
        self.lbl.pack()
        self.win = bw
        self.step = 0
        self._animate(pet_x, pet_y, pet_w)
        self.after_id = self.parent.after(self.duration_ms, self.hide)

    def _animate(self, pet_x: float, pet_y: float, pet_w: int) -> None:
        if self.win is None:
            return
        self.step += 1
        pop_offset = -math.sin(min(self.step, 10) / 10 * math.pi) * 8
        bob = math.sin(self.step * 0.25) * 2.5
        x, y = self._compute_pos(pet_x, pet_y, pet_w, pop_offset, bob)
        try:
            self.win.geometry(f"+{x}+{y}")
            if self.step < self.max_steps:
                self.anim_id = self.parent.after(33, lambda: self._animate(pet_x, pet_y, pet_w))
        except Exception:
            pass

    def hide(self) -> None:
        for attr in ("anim_id", "after_id"):
            timer_id = getattr(self, attr)
            if timer_id is not None:
                try:
                    self.parent.after_cancel(timer_id)
                except Exception:
                    pass
                setattr(self, attr, None)
        if self.win is not None:
            try:
                self.win.destroy()
            except Exception:
                pass
            self.win = None


class HeartBubblePopup(FloatingImagePopup):
    """Attached pixel heart bubble popup with gentle pop animation."""

    def __init__(self, parent: tk.Tk, pil_img: Image.Image):
        super().__init__(parent, pil_img, img_size=(64, 58), duration_ms=2400, max_steps=60)


class ThoughtBubblePopup(FloatingImagePopup):
    """Floating cloud thought bubble displaying Kai's chibi sprite at upper-right of head."""

    def __init__(self, parent: tk.Tk, pil_img: Image.Image):
        super().__init__(parent, pil_img, img_size=(118, 108), duration_ms=4000, max_steps=115)

    def _compute_pos(
        self, pet_x: float, pet_y: float, pet_w: int, pop_offset: float, bob: float
    ) -> Tuple[int, int]:
        wl, _wt, wr, _wb = get_work_area(self.parent, pet_x + pet_w / 2, pet_y)
        x = int(pet_x + pet_w * 0.46)
        if x + self.img_size[0] > wr - 8:
            x = max(wl + 8, int(pet_x - self.img_size[0] * 0.45))
        y = int(pet_y - 104 + pop_offset + bob)
        return clamp_to_monitor(
            self.parent, x, y, self.img_size[0], self.img_size[1], pet_x + pet_w / 2, pet_y
        )


class BaseFloatingCard:
    """Shared topmost rounded speech-bubble card rendered cleanly with PIL."""

    CHROMA = "#010101"

    THEMES = {
        "blue": {
            "bg": "#EAF6FF",
            "border": "#84CAFF",
            "title": "#0369A1",
            "text": "#1E293B",
            "btn_bg": "#FFFFFF",
            "btn_hover": "#D6EEFF",
            "btn_border": "#A5D8FF",
            "btn_fg": "#1E3A8A",
            "close": "#64748B",
        },
        "pink": {
            "bg": "#FFF0F6",
            "border": "#F7A8C8",
            "title": "#BE185D",
            "text": "#5C1D38",
            "btn_bg": "#FFFFFF",
            "btn_hover": "#FFD8E8",
            "btn_border": "#FBCFE8",
            "btn_fg": "#831843",
            "close": "#9D174D",
        },
    }

    def __init__(self, pet: "KaiDesktopPet"):
        self.pet = pet
        self.win: Optional[tk.Toplevel] = None
        self.lbl: Optional[tk.Label] = None
        self.photo: Optional[ImageTk.PhotoImage] = None
        self.after_id: Optional[str] = None
        self.hotspots: List[Tuple[int, int, int, int, Callable[[], None]]] = []
        self.hover_idx: Optional[int] = None
        self._current_spec: Optional[dict] = None

    def _load_font(self, size: int, bold: bool = False) -> ImageFont.ImageFont:
        candidates = []
        if bold:
            candidates.append(resource_path(os.path.join("assets", "fonts", "Quicksand-Bold.ttf")))
            candidates.append(r"C:\Windows\Fonts\segoeuib.ttf")
        if self.pet.font_path:
            candidates.append(self.pet.font_path)
        candidates.extend([r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"])
        for path in candidates:
            if path and os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    pass
        return ImageFont.load_default()

    @staticmethod
    def _wrap_text(
        draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int
    ) -> List[str]:
        lines: List[str] = []
        for para in text.split("\n"):
            words = para.split(" ")
            cur = ""
            for word in words:
                trial = word if not cur else f"{cur} {word}"
                bbox = draw.textbbox((0, 0), trial, font=font)
                if bbox[2] - bbox[0] <= max_w or not cur:
                    cur = trial
                else:
                    lines.append(cur)
                    cur = word
            if cur:
                lines.append(cur)
        return lines

    @staticmethod
    def _text_size(
        draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont
    ) -> Tuple[int, int, int, int]:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox[0], bbox[1]

    def build_bubble_image(self, hover_idx: Optional[int] = None) -> Image.Image:
        """Render the rounded speech-bubble card and pill buttons to an RGBA PIL image."""
        spec = self._current_spec
        if spec is None:
            raise RuntimeError("No bubble spec initialized")

        title: str = spec["title"]
        body_text: Optional[str] = spec["body_text"]
        buttons: List[Tuple[str, Callable[[], None]]] = spec["buttons"]
        theme = self.THEMES.get(spec["theme"], self.THEMES["blue"])
        width: int = spec["width"]
        inline_buttons: bool = spec["inline_buttons"]

        f_title = self._load_font(13, bold=True)
        f_body = self._load_font(14, bold=bool(buttons and not inline_buttons))
        f_btn = self._load_font(13, bold=inline_buttons)
        f_close = self._load_font(14, bold=True)

        dummy_draw = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        pad_x = 18
        inner_w = width - pad_x * 2

        body_lines = self._wrap_text(dummy_draw, body_text, f_body, inner_w) if body_text else []
        line_h = 20

        # Vertical layout computation
        y_cursor = 14
        title_y = y_cursor
        y_cursor += 24

        body_y = y_cursor
        if body_lines:
            y_cursor += len(body_lines) * line_h + 10

        btn_rects: List[Tuple[int, int, int, int, str, Callable[[], None]]] = []
        if inline_buttons and buttons:
            gap = 8
            btn_h = 30
            btn_w = (inner_w - gap * (len(buttons) - 1)) // len(buttons)
            for idx, (label, cb) in enumerate(buttons):
                bx0 = pad_x + idx * (btn_w + gap)
                btn_rects.append((bx0, y_cursor, bx0 + btn_w, y_cursor + btn_h, label, cb))
            y_cursor += btn_h + 6
        else:
            btn_h = 31
            for label, cb in buttons:
                btn_rects.append((pad_x, y_cursor, width - pad_x, y_cursor + btn_h, label, cb))
                y_cursor += btn_h + 7

        body_h = y_cursor + 10
        tail_h = 12
        total_h = body_h + tail_h + 2

        # Draw shapes at 2x supersampling for crisp rounded edges and tail
        ss = 2
        sw, sh = width * ss, total_h * ss
        shape_img = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shape_img)

        sd.rounded_rectangle(
            [2 * ss, 2 * ss, (width - 3) * ss, (body_h - 1) * ss],
            radius=22 * ss,
            fill=theme["bg"],
            outline=theme["border"],
            width=2 * ss,
        )
        # Speech bubble pointer tail at bottom-center pointing down toward Hùng
        cx_s = (width // 2) * ss
        by_s = (body_h - 2) * ss
        tip_y_s = (body_h + tail_h - 1) * ss
        half_tw = 10 * ss
        sd.polygon(
            [(cx_s - half_tw, by_s - 2), (cx_s + half_tw, by_s - 2), (cx_s, tip_y_s)],
            fill=theme["bg"],
        )
        sd.line([(cx_s - half_tw, by_s), (cx_s, tip_y_s)], fill=theme["border"], width=2 * ss)
        sd.line([(cx_s + half_tw, by_s), (cx_s, tip_y_s)], fill=theme["border"], width=2 * ss)

        # Draw pill-shaped option buttons at 2x
        for idx, (x0, y0, x1, y1, _label, _cb) in enumerate(btn_rects):
            fill_c = theme["btn_hover"] if hover_idx == idx else theme["btn_bg"]
            sd.rounded_rectangle(
                [x0 * ss, y0 * ss, x1 * ss, y1 * ss],
                radius=14 * ss,
                fill=fill_c,
                outline=theme["btn_border"],
                width=max(2, ss),
            )

        canvas_img = shape_img.resize((width, total_h), Image.Resampling.LANCZOS)
        td = ImageDraw.Draw(canvas_img)

        # Crisp 1x text rendering + mini vector heart beside title (no missing font glyph)
        td.text((pad_x, title_y), title, font=f_title, fill=theme["title"])
        tw_title, _th_title, ox_title, _oy_title = self._text_size(td, title, f_title)
        hx = pad_x + ox_title + tw_title + 9
        hy = title_y + 8
        heart_col = "#EC4899" if spec["theme"] == "pink" else "#38BDF8"
        td.polygon(
            [
                (hx, hy + 4),
                (hx - 5, hy - 1),
                (hx - 4, hy - 4),
                (hx - 2, hy - 4),
                (hx, hy - 2),
                (hx + 2, hy - 4),
                (hx + 4, hy - 4),
                (hx + 5, hy - 1),
            ],
            fill=heart_col,
        )

        # Close hitbox at top right
        close_box = (width - 32, 8, width - 10, 30)
        close_col = theme["title"] if hover_idx == len(btn_rects) else theme["close"]
        td.text((width - 25, 11), "×", font=f_close, fill=close_col)

        for i, line in enumerate(body_lines):
            td.text((pad_x, body_y + i * line_h), line, font=f_body, fill=theme["text"])

        self.hotspots = []
        for idx, (x0, y0, x1, y1, label, cb) in enumerate(btn_rects):
            tw, th, ox, oy = self._text_size(td, label, f_btn)
            tx = (x0 + (x1 - x0 - tw) / 2 - ox) if inline_buttons else (x0 + 14 - ox)
            ty = y0 + (y1 - y0 - th) / 2 - oy - 1
            td.text((tx, ty), label, font=f_btn, fill=theme["btn_fg"])
            self.hotspots.append((x0, y0, x1, y1, cb))

        self.hotspots.append((*close_box, self.hide))
        return canvas_img

    def _refresh_image(self) -> None:
        if self.lbl is None or self._current_spec is None:
            return
        img = self.build_bubble_image(hover_idx=self.hover_idx)
        self.photo = prep_photo(img, img.size)
        self.lbl.configure(image=self.photo)

    def _hit_test(self, x: int, y: int) -> Optional[int]:
        for idx, (x0, y0, x1, y1, _cb) in enumerate(self.hotspots):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return idx
        return None

    def _on_motion(self, event: tk.Event) -> None:
        idx = self._hit_test(event.x, event.y)
        if idx != self.hover_idx:
            self.hover_idx = idx
            if self.lbl is not None:
                self.lbl.configure(cursor="hand2" if idx is not None else "")
            self._refresh_image()

    def _on_click(self, event: tk.Event) -> None:
        idx = self._hit_test(event.x, event.y)
        if idx is not None:
            cb = self.hotspots[idx][4]
            cb()

    def show_bubble_card(
        self,
        title: str,
        body_text: Optional[str],
        buttons: List[Tuple[str, Callable[[], None]]],
        theme: str = "blue",
        width: int = 276,
        inline_buttons: bool = False,
        auto_close_ms: Optional[int] = 18000,
    ) -> None:
        self.hide()
        self.hover_idx = None
        self._current_spec = {
            "title": title,
            "body_text": body_text,
            "buttons": buttons,
            "theme": theme,
            "width": width,
            "inline_buttons": inline_buttons,
        }
        img = self.build_bubble_image(hover_idx=None)

        m = tk.Toplevel(self.pet.win)
        m.overrideredirect(True)
        m.wm_attributes("-topmost", True)
        m.configure(bg=self.CHROMA)
        if sys.platform == "win32":
            m.wm_attributes("-transparentcolor", self.CHROMA)
        elif sys.platform == "darwin":
            m.wm_attributes("-transparent", True)

        self.photo = prep_photo(img, img.size)
        lbl = tk.Label(m, image=self.photo, bg=self.CHROMA, bd=0)
        lbl.pack()
        lbl.bind("<Motion>", self._on_motion)
        lbl.bind("<Leave>", lambda _e: self._clear_hover())
        lbl.bind("<Button-1>", self._on_click)
        self.lbl = lbl
        self.win = m

        mw, mh = img.size
        pet_cx = self.pet.x + self.pet.canvas_pad + self.pet.pet_size / 2
        pet_top = self.pet.y + self.pet.canvas_pad
        x, y = clamp_to_monitor(
            self.pet.win, int(pet_cx - mw / 2), int(pet_top - mh + 2), mw, mh, pet_cx, pet_top
        )
        m.geometry(f"+{x}+{y}")

        if auto_close_ms is not None:
            self.after_id = self.pet.win.after(auto_close_ms, self.hide)

    def _clear_hover(self) -> None:
        if self.hover_idx is not None:
            self.hover_idx = None
            if self.lbl is not None:
                self.lbl.configure(cursor="")
            self._refresh_image()

    def hide(self) -> None:
        if self.after_id is not None:
            try:
                self.pet.win.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        if self.win is not None:
            try:
                self.win.destroy()
            except Exception:
                pass
            self.win = None
        self.lbl = None


class InteractiveChatPopup(BaseFloatingCard):
    """3-option Q&A conversation speech bubble above Hùng."""

    def __init__(self, pet: "KaiDesktopPet"):
        super().__init__(pet)
        self.qa_index = 0

    def show(self) -> None:
        qa = QA_CONVERSATIONS[self.qa_index % len(QA_CONVERSATIONS)]
        self.qa_index += 1
        buttons = [
            (opt_text, lambda r=reply_text, k=reaction_kind: self._choose(k, r))
            for opt_text, reply_text, reaction_kind in qa["options"]
        ]
        self.show_bubble_card(
            title="Hùng hỏi cậu nè",
            body_text=qa["question"],
            buttons=buttons,
            theme="blue",
            width=268,
            inline_buttons=False,
            auto_close_ms=18000,
        )

    def _choose(self, reaction_kind: str, reply_text: str) -> None:
        self.hide()
        self.pet.apply_reaction(reaction_kind, reply_text)


class FeedCarePopup(BaseFloatingCard):
    """Feed & care selection speech bubble above Hùng."""

    def show(self) -> None:
        buttons = [
            (label, lambda r=reply_text, k=reaction_kind: self._choose(k, r))
            for label, reply_text, reaction_kind in CARE_ITEMS
        ]
        self.show_bubble_card(
            title="Nạp năng lượng cho Hùng",
            body_text=None,
            buttons=buttons,
            theme="pink",
            width=268,
            inline_buttons=False,
            auto_close_ms=18000,
        )

    def _choose(self, reaction_kind: str, reply_text: str) -> None:
        self.hide()
        self.pet.apply_reaction(reaction_kind, reply_text)


class LoveNotePopup(BaseFloatingCard):
    """Pastel secret love letter speech bubble displaying long messages for Kai."""

    def __init__(self, pet: "KaiDesktopPet"):
        super().__init__(pet)
        self.note_idx = 0

    def show(self) -> None:
        idx = self.note_idx % len(SECRET_LOVE_NOTES)
        note_text = SECRET_LOVE_NOTES[idx]
        self.show_bubble_card(
            title=f"Thư nhỏ gửi cậu ({idx + 1}/{len(SECRET_LOVE_NOTES)})",
            body_text=note_text,
            buttons=[
                ("Thư tiếp theo ->", self._next_note),
                ("Đóng", self.hide),
            ],
            theme="pink",
            width=312,
            inline_buttons=True,
            auto_close_ms=None,
        )

    def _next_note(self) -> None:
        self.note_idx = (self.note_idx + 1) % len(SECRET_LOVE_NOTES)
        self.pet.spawn_heart_particles(count=4)
        self.show()


class CleanSettingsMenu:
    """Clean white floating settings card with crisp vector line icons."""

    def __init__(self, pet: "KaiDesktopPet"):
        self.pet = pet
        self.win: Optional[tk.Toplevel] = None
        self.font_family = pet.tk_font_family

    def show(self, screen_x: int, screen_y: int) -> None:
        self.hide()
        m = tk.Toplevel(self.pet.win)
        m.overrideredirect(True)
        m.wm_attributes("-topmost", True)
        m.configure(bg="#E5E7EB")

        card = tk.Frame(m, bg="#FFFFFF", padx=8, pady=8)
        card.pack(padx=1, pady=1)

        header = tk.Frame(card, bg="#FFFFFF", padx=10, pady=6)
        header.pack(fill="x")
        tk.Label(
            header,
            text="Hùng",
            font=(self.font_family, 11, "bold"),
            bg="#FFFFFF",
            fg="#111827",
        ).pack(side="left")

        pill_bg = "#E0F2FE" if self.pet.walking_enabled else "#F3F4F6"
        pill_fg = "#0369A1" if self.pet.walking_enabled else "#6B7280"
        pill_txt = "Đang đi dạo" if self.pet.walking_enabled else "Đứng yên"
        tk.Label(
            header,
            text=pill_txt,
            font=(self.font_family, 8, "bold"),
            bg=pill_bg,
            fg=pill_fg,
            padx=8,
            pady=2,
        ).pack(side="right")

        self._divider(card)

        walk_label = "Tắt đi lại" if self.pet.walking_enabled else "Bật đi lại"
        self._item(card, "walk", walk_label, self._toggle_walk)
        self._item(card, "chat", "Trò chuyện với Hùng", self._open_chat)
        self._item(card, "heart", "Nói lời yêu", self._say_love)
        self._item(card, "thought", "Tơ tưởng về cậu", self._trigger_daydream)
        self._item(card, "gift", "Nạp năng lượng cho Hùng", self._open_feed)
        self._item(card, "mail", "Hộp thư bí mật", self._open_note)
        self._item(card, "heart", "Xoa đầu Hùng", self._trigger_pet)

        size_names = {145: "Nhỏ", 175: "Vừa", 210: "Lớn"}
        cur_size = size_names.get(self.pet.pet_size, "Vừa")
        self._item(card, "size", f"Kích thước: {cur_size}", self._cycle_size)

        if sys.platform == "win32":
            startup_label = (
                "Tự mở cùng Windows: Bật" if is_startup_enabled() else "Tự mở cùng Windows: Tắt"
            )
            self._item(card, "startup", startup_label, self._toggle_startup)

        self._divider(card)
        self._item(card, "exit", "Thoát Hùng", self.pet.quit_app, danger=True)

        m.update_idletasks()
        mw, mh = m.winfo_width(), m.winfo_height()
        x, y = clamp_to_monitor(self.pet.win, screen_x, screen_y, mw, mh, screen_x, screen_y)
        m.geometry(f"+{x}+{y}")

        m.bind("<FocusOut>", lambda _e: self.hide())
        m.focus_force()
        self.win = m

    def _divider(self, parent: tk.Frame) -> None:
        tk.Frame(parent, bg="#F1F5F9", height=1).pack(fill="x", padx=6, pady=5)

    def _draw_icon(self, c: tk.Canvas, kind: str, color: str) -> None:
        if kind == "walk":
            c.create_oval(5, 3, 10, 8, outline=color, width=1.6)
            c.create_line(7, 8, 7, 13, fill=color, width=1.6)
            c.create_line(7, 10, 4, 13, fill=color, width=1.6)
            c.create_line(7, 10, 11, 12, fill=color, width=1.6)
            c.create_line(7, 13, 5, 17, fill=color, width=1.6)
            c.create_line(7, 13, 10, 17, fill=color, width=1.6)
        elif kind == "chat":
            c.create_oval(3, 4, 17, 14, outline=color, width=1.6)
            c.create_line(6, 14, 4, 17, 9, 14, fill=color, width=1.6)
        elif kind == "heart":
            c.create_polygon(
                10, 16, 4, 10, 4, 6, 7, 4, 10, 7, 13, 4, 16, 6, 16, 10,
                outline=color, fill="", width=1.6, smooth=True,
            )
        elif kind == "thought":
            c.create_oval(3, 5, 11, 13, outline=color, width=1.5)
            c.create_oval(7, 3, 15, 11, outline=color, width=1.5)
            c.create_oval(11, 6, 18, 13, outline=color, width=1.5)
            c.create_oval(5, 14, 7, 16, outline=color, width=1.4)
        elif kind == "gift":
            c.create_rectangle(4, 8, 16, 16, outline=color, width=1.6)
            c.create_rectangle(3, 6, 17, 9, outline=color, width=1.5)
            c.create_line(10, 6, 10, 16, fill=color, width=1.5)
            c.create_oval(6, 3, 10, 6, outline=color, width=1.4)
            c.create_oval(10, 3, 14, 6, outline=color, width=1.4)
        elif kind == "mail":
            c.create_rectangle(3, 5, 17, 15, outline=color, width=1.6)
            c.create_line(3, 6, 10, 11, 17, 6, fill=color, width=1.5)
        elif kind == "size":
            c.create_rectangle(4, 4, 16, 16, outline=color, width=1.6)
            c.create_line(7, 13, 13, 7, fill=color, width=1.5)
        elif kind == "startup":
            c.create_rectangle(3, 4, 17, 13, outline=color, width=1.6)
            c.create_line(7, 16, 13, 16, fill=color, width=1.6)
            c.create_line(10, 13, 10, 16, fill=color, width=1.6)
            c.create_line(7, 8, 9, 10, 13, 6, fill=color, width=1.5)
        elif kind == "exit":
            c.create_line(11, 4, 4, 4, 4, 16, 11, 16, fill=color, width=1.6)
            c.create_line(8, 10, 16, 10, fill=color, width=1.6)
            c.create_line(13, 7, 16, 10, 13, 13, fill=color, width=1.6)

    def _item(
        self,
        parent: tk.Frame,
        icon_kind: str,
        label: str,
        command,
        danger: bool = False,
    ) -> None:
        row = tk.Frame(parent, bg="#FFFFFF", cursor="hand2")
        row.pack(fill="x", pady=1)

        fg_color = "#DC2626" if danger else "#1F2937"
        hover_bg = "#FEF2F2" if danger else "#F3F4F6"

        icon_canvas = tk.Canvas(
            row, width=20, height=20, bg="#FFFFFF", highlightthickness=0, bd=0
        )
        icon_canvas.pack(side="left", padx=(8, 4), pady=6)
        self._draw_icon(icon_canvas, icon_kind, fg_color)

        txt_lbl = tk.Label(
            row,
            text=label,
            font=(self.font_family, 10),
            bg="#FFFFFF",
            fg=fg_color,
            anchor="w",
            padx=4,
            pady=6,
        )
        txt_lbl.pack(side="left", fill="x", expand=True, padx=(0, 12))

        def on_enter(_e):
            row.configure(bg=hover_bg)
            icon_canvas.configure(bg=hover_bg)
            txt_lbl.configure(bg=hover_bg)

        def on_leave(_e):
            row.configure(bg="#FFFFFF")
            icon_canvas.configure(bg="#FFFFFF")
            txt_lbl.configure(bg="#FFFFFF")

        def on_click(_e):
            self.hide()
            command()

        for w in (row, icon_canvas, txt_lbl):
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", on_click)

    def _toggle_walk(self) -> None:
        self.pet.walking_enabled = not self.pet.walking_enabled
        if not self.pet.walking_enabled and self.pet.state == "walk":
            self.pet.state = "idle"
            self.pet.state_timer = 60

    def _open_chat(self) -> None:
        self.pet.open_interactive_chat()

    def _say_love(self) -> None:
        self.pet.trigger_love_talk()

    def _trigger_daydream(self) -> None:
        self.pet.trigger_daydream()

    def _open_feed(self) -> None:
        self.pet.open_feed_menu()

    def _open_note(self) -> None:
        self.pet.open_love_note()

    def _trigger_pet(self) -> None:
        self.pet.start_petting(force_intense=True)

    def _cycle_size(self) -> None:
        order = [145, 175, 210]
        idx = (order.index(self.pet.pet_size) + 1) % len(order) if self.pet.pet_size in order else 1
        self.pet.set_pet_size(order[idx])

    def _toggle_startup(self) -> None:
        new_state = not is_startup_enabled()
        set_startup_enabled(new_state)
        msg = (
            "Đã bật tự mở cùng Windows, mở máy là thấy tớ ngay!"
            if new_state
            else "Đã tắt tự mở cùng Windows rồi nha!"
        )
        self.pet.bubble.show(
            msg,
            self.pet.x + self.pet.canvas_pad,
            self.pet.y + self.pet.canvas_pad,
            self.pet.pet_size,
            style="pink" if new_state else "blue",
            duration_ms=3400,
        )

    def hide(self) -> None:
        if self.win is not None:
            try:
                self.win.destroy()
            except Exception:
                pass
            self.win = None


class KaiDesktopPet:
    CHROMA = "#010101"

    def __init__(self):
        if sys.platform == "win32":
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

        self.font_path = find_font_file()
        ensure_default_startup()

        self.win = tk.Tk()
        available = set(tkfont.families(self.win))
        if "Quicksand SemiBold" in available:
            self.tk_font_family = "Quicksand SemiBold"
        elif "Quicksand" in available:
            self.tk_font_family = "Quicksand"
        elif "Be Vietnam Pro" in available:
            self.tk_font_family = "Be Vietnam Pro"
        elif "Segoe UI" in available:
            self.tk_font_family = "Segoe UI"
        else:
            self.tk_font_family = "Arial"

        self.pet_size = 145
        self.canvas_pad = 36
        self.win_size = self.pet_size + self.canvas_pad * 2

        self.win.overrideredirect(True)
        self.win.wm_attributes("-topmost", True)
        self.win.configure(bg=self.CHROMA)
        if sys.platform == "win32":
            self.win.wm_attributes("-transparentcolor", self.CHROMA)
        elif sys.platform == "darwin":
            self.win.wm_attributes("-transparent", True)

        self.canvas = tk.Canvas(
            self.win,
            width=self.win_size,
            height=self.win_size,
            bg=self.CHROMA,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack()

        self.raw_sprites: Dict[int, Image.Image] = {}
        for i in range(1, 15):
            p = resource_path(os.path.join("assets", "sprites", f"{i}.png"))
            if os.path.exists(p):
                self.raw_sprites[i] = Image.open(p).convert("RGBA")
        if 13 not in self.raw_sprites and 5 in self.raw_sprites:
            self.raw_sprites[13] = self.raw_sprites[5]
        if 14 not in self.raw_sprites and 12 in self.raw_sprites:
            self.raw_sprites[14] = self.raw_sprites[12]

        self.photos_normal: Dict[int, ImageTk.PhotoImage] = {}
        self.photos_mirrored: Dict[int, ImageTk.PhotoImage] = {}
        self._rebuild_sprite_cache()

        self.fx_photos: Dict[str, ImageTk.PhotoImage] = {}
        for i in range(8):
            p = resource_path(os.path.join("assets", "effects", f"fall_fx_{i}.png"))
            if os.path.exists(p):
                im = Image.open(p).convert("RGBA")
                sz = 22 if i < 3 else 16
                self.fx_photos[f"fall_{i}"] = prep_photo(im, (sz, sz), for_canvas=True)
        for i in range(4):
            p = resource_path(os.path.join("assets", "effects", f"heart_fx_{i}.png"))
            if os.path.exists(p):
                im = Image.open(p).convert("RGBA")
                self.fx_photos[f"heart_{i}"] = prep_photo(im, (20, 20), for_canvas=True)

        hb_path = resource_path(os.path.join("assets", "effects", "heart_bubble.png"))
        self.heart_popup = HeartBubblePopup(self.win, Image.open(hb_path).convert("RGBA"))
        tk_path = resource_path(os.path.join("assets", "effects", "thought_kai.png"))
        self.thought_popup = (
            ThoughtBubblePopup(self.win, Image.open(tk_path).convert("RGBA"))
            if os.path.exists(tk_path)
            else None
        )
        self.bubble = AttachedBubble(self.win, self.font_path, pet=self)
        self.settings_menu = CleanSettingsMenu(self)
        self.chat_popup = InteractiveChatPopup(self)
        self.feed_popup = FeedCarePopup(self)
        self.note_popup = LoveNotePopup(self)

        self.work_left, self.work_top, self.work_right, self.work_bottom = get_work_area(self.win)
        self.x = float(self.work_right - self.win_size - 140)
        self.y = float(self.work_bottom - self.win_size + self.canvas_pad)
        self.vx = 0.0
        self.vy = 0.0
        self.facing = -1

        self.state = "idle"
        self.state_timer = 75
        self.frame = 0
        self.walking_enabled = True
        self.fall_frames = 0

        self.is_pressing = False
        self.drag_off_x = 0
        self.drag_off_y = 0
        self.press_mx = 0
        self.press_my = 0
        self.last_mx = 0
        self.last_my = 0
        self.drag_moved = False
        self.drag_dir = 0
        self.drag_dir_hold = 0

        self.last_hover_x: Optional[int] = None
        self.last_hover_dir: int = 0
        self.pet_swipes: int = 0
        self.pet_decay_timer: int = 0
        self.intense_cooldown: int = 0

        self.particles: List[FxParticle] = []
        self.click_cycle = 0
        self.auto_romance_timer = random.randint(1800, 3600)
        self._last_photo = self.photos_normal[1]
        self._had_fx = False
        self._last_geom: Optional[str] = None
        self.pet_item = self.canvas.create_image(
            self.canvas_pad + self.pet_size / 2,
            self.canvas_pad + self.pet_size / 2,
            image=self._last_photo,
        )

        self.last_night_slot: Optional[str] = None
        self.last_hourly_slot: Optional[str] = None

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Motion>", self.on_hover)
        self.canvas.bind("<Button-3>", self.on_right_click)
        if sys.platform == "darwin":
            self.canvas.bind("<Button-2>", self.on_right_click)

        self.update_pos()
        self.win.after(600, self.check_startup_greeting)
        self.loop()

    def refresh_work_area(self) -> None:
        self.work_left, self.work_top, self.work_right, self.work_bottom = get_work_area(
            self.win, self.x + self.win_size / 2, self.y + self.win_size / 2
        )

    def _ensure_topmost(self) -> None:
        keep_window_topmost(self.win)
        for popup in (
            self.bubble,
            self.heart_popup,
            self.thought_popup,
            self.chat_popup,
            self.feed_popup,
            self.note_popup,
            self.settings_menu,
        ):
            if popup is not None:
                keep_window_topmost(popup.win)

    def _rebuild_sprite_cache(self) -> None:
        sz = (self.pet_size, self.pet_size)
        for i, im in self.raw_sprites.items():
            self.photos_normal[i] = prep_photo(im, sz, for_canvas=True)
            if i in (2, 3):
                self.photos_mirrored[i] = prep_photo(ImageOps.mirror(im), sz, for_canvas=True)

    def set_pet_size(self, new_size: int) -> None:
        self.pet_size = new_size
        self.win_size = self.pet_size + self.canvas_pad * 2
        self.canvas.configure(width=self.win_size, height=self.win_size)
        self._rebuild_sprite_cache()
        self._last_photo = None
        self._last_geom = None
        self.refresh_work_area()
        floor_y = self.work_bottom - self.win_size + self.canvas_pad
        if self.y > floor_y:
            self.y = float(floor_y)
        self.x = max(float(self.work_left), min(self.x, float(self.work_right - self.win_size)))
        self.update_pos()

    def check_startup_greeting(self) -> None:
        now = datetime.datetime.now()
        if 5 <= now.hour < 12:
            self.bubble.show(
                "Buổi sáng nha cậu!",
                self.x + self.canvas_pad,
                self.y + self.canvas_pad,
                self.pet_size,
                style="blue",
                duration_ms=4200,
            )

    def check_time_triggers(self) -> None:
        now = datetime.datetime.now()
        if 0 <= now.hour < 5 and now.minute in (0, 30):
            slot = f"{now.strftime('%Y-%m-%d %H')}:{now.minute:02d}"
            if slot != self.last_night_slot:
                self.last_night_slot = slot
                self.state = "talk_4"
                self.state_timer = 135
                self.bubble.show(
                    "Ngủ sớm đi cậu yêu",
                    self.x + self.canvas_pad,
                    self.y + self.canvas_pad,
                    self.pet_size,
                    style="blue",
                    duration_ms=4500,
                )
        elif 5 <= now.hour <= 23 and now.minute == 0:
            slot = now.strftime("%Y-%m-%d %H")
            if slot != self.last_hourly_slot:
                self.last_hourly_slot = slot
                self.state = "talk_5"
                self.state_timer = 135
                self.bubble.show(
                    "Nhớ cậu quá...",
                    self.x + self.canvas_pad,
                    self.y + self.canvas_pad,
                    self.pet_size,
                    style="pink",
                    duration_ms=4500,
                )

    def on_press(self, event: tk.Event) -> None:
        self.settings_menu.hide()
        self.is_pressing = True
        self.drag_off_x = event.x
        self.drag_off_y = event.y
        self.press_mx = event.x_root
        self.press_my = event.y_root
        self.last_mx = event.x_root
        self.last_my = event.y_root
        self.drag_moved = False
        self.drag_dir = 0

    def on_drag(self, event: tk.Event) -> None:
        if not self.is_pressing:
            return
        if not self.drag_moved:
            if abs(event.x_root - self.press_mx) > 5 or abs(event.y_root - self.press_my) > 5:
                self.drag_moved = True
                self._close_interactive_popups()
                self.state = "drag"
                self.vx = 0.0
                self.vy = 0.0
            else:
                return

        dx = event.x_root - self.last_mx
        dy = event.y_root - self.last_my
        if dx < -1.5:
            self.drag_dir = -1
            self.drag_dir_hold = 6
        elif dx > 1.5:
            self.drag_dir = 1
            self.drag_dir_hold = 6

        self.vx = dx * 0.45
        self.vy = dy * 0.45
        self.x = float(event.x_root - self.drag_off_x)
        self.y = float(event.y_root - self.drag_off_y)
        self.last_mx = event.x_root
        self.last_my = event.y_root
        self.update_pos()

    def on_release(self, _event: tk.Event) -> None:
        self.is_pressing = False
        if not self.drag_moved:
            self.say_click_message()
            return

        self.refresh_work_area()
        self.x = max(float(self.work_left), min(self.x, float(self.work_right - self.win_size)))
        floor_y = self.work_bottom - self.win_size + self.canvas_pad
        if self.y < floor_y - 6:
            self.state = "fall"
            self.fall_frames = 0
            self.spawn_fall_particles(count=5)
        else:
            self.y = float(floor_y)
            self.state = "land"
            self.state_timer = 12
            self.spawn_fall_particles(count=6)

    def on_hover(self, event: tk.Event) -> None:
        if self.is_pressing or self.state in ("drag", "fall", "land"):
            return
        head_top = self.canvas_pad
        head_bottom = self.canvas_pad + self.pet_size * 0.56
        if not (head_top <= event.y <= head_bottom):
            self.last_hover_x = None
            self.last_hover_dir = 0
            return

        if self.last_hover_x is not None:
            dx = event.x - self.last_hover_x
            if abs(dx) >= 4:
                cur_dir = 1 if dx > 0 else -1
                if self.last_hover_dir != 0 and cur_dir != self.last_hover_dir:
                    self.pet_swipes += 1
                elif self.last_hover_dir == 0:
                    self.pet_swipes += 1
                self.last_hover_dir = cur_dir
                self.last_hover_x = event.x
                self.pet_decay_timer = 45
                self.start_petting(force_intense=False)
        else:
            self.last_hover_x = event.x

    def start_petting(self, force_intense: bool = False) -> None:
        if force_intense or (self.pet_swipes >= 15 and self.intense_cooldown <= 0):
            self.state = "pet_intense"
            self.state_timer = 80
            self.pet_swipes = 0
            self.intense_cooldown = 100
            self.heart_popup.show(
                self.x + self.canvas_pad,
                self.y + self.canvas_pad,
                self.pet_size,
            )
        elif self.state != "pet_intense":
            self.state = "pet"
            self.state_timer = 22

    def _close_interactive_popups(self) -> None:
        self.chat_popup.hide()
        self.feed_popup.hide()
        self.note_popup.hide()

    def _open_card(self, popup: BaseFloatingCard) -> None:
        self._close_interactive_popups()
        self.bubble.hide()
        if self.state == "walk":
            self.state = "idle"
            self.state_timer = 120
        popup.show()

    def open_interactive_chat(self) -> None:
        self._open_card(self.chat_popup)

    def open_feed_menu(self) -> None:
        self._open_card(self.feed_popup)

    def open_love_note(self) -> None:
        self._open_card(self.note_popup)

    def apply_reaction(self, kind: str, reply_text: str) -> None:
        self._close_interactive_popups()
        bx = self.x + self.canvas_pad
        by = self.y + self.canvas_pad
        specs = {
            "happy": ("talk_4", 135, 4, "blue", 4200, None),
            "love": ("love_talk", 140, 9, "pink", 4400, None),
            "daydream": ("daydream", 150, 5, "pink", 4400, "thought"),
            "shy": ("pet_intense", 140, 8, "pink", 4400, "heart"),
            "headpat": ("pet", 130, 7, "pink", 4200, "heart"),
        }
        spec = specs.get(kind)
        if spec is None:
            self.bubble.show(reply_text, bx, by, self.pet_size, style="blue", duration_ms=4000)
            return

        state_name, timer, heart_count, style, duration_ms, extra = spec
        self.state = state_name
        self.state_timer = timer
        if extra == "thought" and self.thought_popup is not None:
            self.thought_popup.show(bx, by, self.pet_size)
        elif extra == "heart":
            self.heart_popup.show(bx, by, self.pet_size)
        self.spawn_heart_particles(count=heart_count)
        self.bubble.show(reply_text, bx, by, self.pet_size, style=style, duration_ms=duration_ms)

    def say_click_message(self) -> None:
        step_mode = self.click_cycle % 3
        self.click_cycle += 1
        if step_mode == 0:
            self.bubble.show(
                random.choice(CLICK_MESSAGES),
                self.x + self.canvas_pad,
                self.y + self.canvas_pad,
                self.pet_size,
                style="blue",
                duration_ms=3200,
            )
            return
        if step_mode == 1:
            self.trigger_love_talk()
            return
        self.trigger_daydream()

    def trigger_love_talk(self) -> None:
        self.state = "love_talk"
        self.state_timer = 130
        self.spawn_heart_particles(count=8)
        self.bubble.show(
            random.choice(LOVE_MESSAGES),
            self.x + self.canvas_pad,
            self.y + self.canvas_pad,
            self.pet_size,
            style="pink",
            duration_ms=3800,
        )

    def trigger_daydream(self) -> None:
        self.state = "daydream"
        self.state_timer = 145
        if self.thought_popup is not None:
            self.thought_popup.show(
                self.x + self.canvas_pad,
                self.y + self.canvas_pad,
                self.pet_size,
            )
        self.bubble.show(
            random.choice(DAYDREAM_MESSAGES),
            self.x + self.canvas_pad,
            self.y + self.canvas_pad,
            self.pet_size,
            style="pink",
            duration_ms=4000,
        )
        self.spawn_heart_particles(count=4)

    def on_right_click(self, event: tk.Event) -> None:
        self.settings_menu.show(event.x_root, event.y_root)

    def spawn_heart_particles(self, count: int = 8) -> None:
        keys = [k for k in self.fx_photos if k.startswith("heart_")]
        if not keys:
            return
        for _ in range(count):
            self.particles.append(
                FxParticle(
                    x=self.win_size / 2 + random.uniform(-self.pet_size * 0.42, self.pet_size * 0.42),
                    y=self.canvas_pad + self.pet_size * random.uniform(0.18, 0.48),
                    vx=random.uniform(-1.3, 1.3),
                    vy=random.uniform(-2.4, -1.1),
                    gravity=-0.05,
                    life=0,
                    max_life=38,
                    img_key=random.choice(keys),
                    sway_phase=random.uniform(0, math.pi * 2),
                )
            )

    def spawn_fall_particles(self, count: int = 6) -> None:
        keys = [k for k in self.fx_photos if k.startswith("fall_")]
        if not keys:
            return
        for _ in range(count):
            angle = random.uniform(-math.pi * 0.9, -math.pi * 0.1)
            speed = random.uniform(1.8, 3.8)
            self.particles.append(
                FxParticle(
                    x=self.win_size / 2 + random.uniform(-22, 22),
                    y=self.canvas_pad + self.pet_size * 0.65,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed - 0.6,
                    gravity=0.18,
                    life=0,
                    max_life=28,
                    img_key=random.choice(keys),
                    sway_phase=random.uniform(0, math.pi * 2),
                )
            )

    def step(self) -> None:
        self.frame += 1
        if self.intense_cooldown > 0:
            self.intense_cooldown -= 1
        if self.auto_romance_timer > 0:
            self.auto_romance_timer -= 1

        if self.pet_decay_timer > 0:
            self.pet_decay_timer -= 1
        else:
            self.pet_swipes = 0
            self.last_hover_dir = 0

        if self.frame % 30 == 0:
            self.check_time_triggers()
        if self.frame % 45 == 0:
            self._ensure_topmost()
        if self.frame % 150 == 0 and self.state not in ("drag", "fall"):
            self.refresh_work_area()

        floor_y = self.work_bottom - self.win_size + self.canvas_pad
        left_lim = self.work_left
        right_lim = self.work_right - self.win_size

        if self.state == "drag":
            if self.drag_dir_hold > 0:
                self.drag_dir_hold -= 1
            else:
                self.drag_dir = 0

        elif self.state == "fall":
            self.fall_frames += 1
            self.vy += 1.25
            self.x += self.vx
            self.y += self.vy
            self.vx *= 0.96
            self.x = max(left_lim, min(self.x, right_lim))
            if self.fall_frames % 5 == 0:
                self.spawn_fall_particles(count=2)

            if self.y >= floor_y:
                self.y = float(floor_y)
                self.vy = 0.0
                self.vx = 0.0
                self.state = "land"
                self.state_timer = 12
                self.spawn_fall_particles(count=7)

        elif self.state == "land":
            self.state_timer -= 1
            if self.state_timer <= 0:
                self.state = "idle"
                self.state_timer = random.randint(45, 95)

        elif self.state == "walk":
            self.x += 2.1 * self.facing
            if self.x <= left_lim:
                self.x = float(left_lim)
                self.facing = 1
            elif self.x >= right_lim:
                self.x = float(right_lim)
                self.facing = -1

            self.state_timer -= 1
            if self.state_timer <= 0:
                self.state = "idle"
                self.state_timer = random.randint(55, 130)

        elif self.state == "idle":
            self.state_timer -= 1
            if self.state_timer <= 0:
                popups_open = any(
                    p.win is not None for p in (self.chat_popup, self.feed_popup, self.note_popup)
                )
                if self.auto_romance_timer <= 0 and not popups_open:
                    self.auto_romance_timer = random.randint(1800, 3600)
                    if random.random() < 0.5:
                        self.trigger_love_talk()
                    else:
                        self.trigger_daydream()
                elif self.walking_enabled and random.random() < 0.65:
                    self.state = "walk"
                    self.facing = random.choice([-1, 1])
                    self.state_timer = random.randint(60, 150)
                else:
                    self.state_timer = random.randint(50, 110)

        elif self.state in ("pet", "pet_intense", "talk_4", "talk_5", "love_talk", "daydream"):
            self.state_timer -= 1
            if self.state_timer <= 0:
                self.state = "idle"
                self.state_timer = random.randint(45, 90)

        self.bubble.reposition(self.x + self.canvas_pad, self.y + self.canvas_pad, self.pet_size)

    def current_sprite_and_offset(self) -> Tuple[int, float, bool]:
        if self.state == "drag":
            if self.drag_dir < 0:
                return 11, 0.0, False
            if self.drag_dir > 0:
                return 10, 0.0, False
            return 9, math.sin(self.frame * 0.25) * 1.5, False

        if self.state == "fall":
            idx = 6 if self.fall_frames < 5 else 7
            return idx, 0.0, False

        if self.state == "land":
            return 8, 2.0, False

        if self.state == "pet":
            return 12, math.sin(self.frame * 0.35) * 2.0, False

        if self.state in ("pet_intense", "talk_5"):
            return 5, math.sin(self.frame * 0.2) * 1.5, False

        if self.state == "love_talk":
            return 13, math.sin(self.frame * 0.28) * 2.2, False

        if self.state == "daydream":
            return 14, math.sin(self.frame * 0.18) * 1.5, False

        if self.state == "talk_4":
            return 4, math.sin(self.frame * 0.15) * 1.5, False

        if self.state == "walk":
            step_idx = 2 if (self.frame // 6) % 2 == 0 else 3
            bob = -abs(math.sin(self.frame * 0.32)) * 3.5
            return step_idx, bob, (self.facing > 0)

        return 1, math.sin(self.frame * 0.12) * 1.2, False

    def draw(self) -> None:
        c = self.canvas

        sprite_idx, bob, use_mirrored = self.current_sprite_and_offset()
        if use_mirrored and sprite_idx in self.photos_mirrored:
            photo = self.photos_mirrored[sprite_idx]
        else:
            photo = self.photos_normal[sprite_idx]

        if photo is not self._last_photo:
            c.itemconfig(self.pet_item, image=photo)
            self._last_photo = photo
        c.coords(
            self.pet_item,
            self.canvas_pad + self.pet_size / 2,
            self.canvas_pad + self.pet_size / 2 + bob,
        )

        if self._had_fx or self.particles:
            c.delete("fx")
        alive: List[FxParticle] = []
        for p in self.particles:
            p.x += p.vx + math.sin(self.frame * 0.25 + p.sway_phase) * 0.35
            p.y += p.vy
            p.vy += p.gravity
            p.life += 1
            if p.life < p.max_life and p.img_key in self.fx_photos:
                c.create_image(p.x, p.y, image=self.fx_photos[p.img_key], tags="fx")
                alive.append(p)
        self.particles = alive
        self._had_fx = bool(alive)

    def update_pos(self) -> None:
        geom = f"{self.win_size}x{self.win_size}+{int(self.x)}+{int(self.y)}"
        if geom != self._last_geom:
            self.win.geometry(geom)
            self._last_geom = geom

    def loop(self) -> None:
        self.step()
        self.update_pos()
        self.draw()
        self.win.after(33, self.loop)

    def quit_app(self) -> None:
        self._close_interactive_popups()
        self.bubble.hide()
        self.heart_popup.hide()
        if self.thought_popup is not None:
            self.thought_popup.hide()
        self.settings_menu.hide()
        self.win.destroy()


def main() -> None:
    pet = KaiDesktopPet()
    pet.win.mainloop()


if __name__ == "__main__":
    main()
