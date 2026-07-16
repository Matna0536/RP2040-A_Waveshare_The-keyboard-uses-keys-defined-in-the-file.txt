# code.py - Multi-Button Macro Keypad for RP2040-Zero
# อ่าน config จาก /config.txt บนตัวบอร์ด รองรับ 3 โหมด: PIN, TEXT, RUN
#
# รูปแบบไฟล์ config.txt ต่อบรรทัด:
#   KEY=VALUE,MODE[,ENTER]
#
#   MODE = PIN   -> พิมพ์ผ่าน numpad (ตัวเลขล้วน, เสถียรทุกภาษา)
#   MODE = TEXT  -> พิมพ์ผ่านคีย์บอร์ดเต็มรูปแบบ (ต้องเป็นเครื่องภาษาอังกฤษ ไม่มีการสลับภาษาให้)
#   MODE = RUN   -> เปิด Win+R -> เปิด Chrome ผ่าน path เต็ม -> รอ -> พิมพ์ลิงก์ที่ address bar

import time
import board
import usb_hid
import digitalio
from adafruit_hid.keyboard import Keyboard, Keycode
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS

# ---------- โหลด config จากไฟล์ ----------
CONFIG_PATH = "/config.txt"
config = {}

with open(CONFIG_PATH, "r") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        key, value = line.split("=", 1)
        items = value.split(",")

        payload = items[0]
        mode = "PIN"
        enter = False

        for extra in items[1:]:
            extra = extra.strip().upper()
            if extra in ("PIN", "TEXT", "RUN"):
                mode = extra
            elif extra == "ENTER":
                enter = True

        config[key.strip()] = {"payload": payload, "mode": mode, "enter": enter}

# ---------- รอ USB HID enumerate ก่อน สำคัญมาก ห้ามข้าม ----------
time.sleep(3)

keyboard = Keyboard(usb_hid.devices)
layout = KeyboardLayoutUS(keyboard)

# ---------- LED แจ้งสถานะ (ถ้ามี) ----------
try:
    from neopixel import NeoPixel
    led = NeoPixel(board.GP16, 1)
    led.brightness = 0.3
    HAS_LED = True
except Exception:
    HAS_LED = False


def blink(color, times=1, delay=0.1):
    if not HAS_LED:
        return
    for _ in range(times):
        led.fill(color)
        time.sleep(delay)
        led.fill((0, 0, 0))
        time.sleep(delay)


# ---------- PIN mode: numpad + เช็ค Num Lock (เสถียรทุกภาษา) ----------
NUMPAD_MAP = {
    "0": Keycode.KEYPAD_ZERO, "1": Keycode.KEYPAD_ONE,
    "2": Keycode.KEYPAD_TWO, "3": Keycode.KEYPAD_THREE,
    "4": Keycode.KEYPAD_FOUR, "5": Keycode.KEYPAD_FIVE,
    "6": Keycode.KEYPAD_SIX, "7": Keycode.KEYPAD_SEVEN,
    "8": Keycode.KEYPAD_EIGHT, "9": Keycode.KEYPAD_NINE,
}


def ensure_numlock_on():
    try:
        if not keyboard.led_on(Keyboard.LED_NUM_LOCK):
            keyboard.send(Keycode.KEYPAD_NUMLOCK)
            time.sleep(0.15)
    except Exception:
        pass


def type_pin(digits, send_enter):
    ensure_numlock_on()
    for ch in digits:
        keyboard.send(NUMPAD_MAP[ch])
        time.sleep(0.03)
    time.sleep(0.1)
    if send_enter:
        keyboard.send(Keycode.ENTER)
    keyboard.release_all()


# ---------- TEXT mode: คีย์บอร์ดเต็มรูปแบบ ----------
# หมายเหตุ: ไม่มีการสลับ/เดาภาษาใดๆ ทั้งสิ้น
# ต้องมั่นใจเองว่าเครื่องปลายทางตั้งคีย์บอร์ดเป็นภาษาอังกฤษอยู่ก่อนใช้โหมดนี้
def type_text(text, send_enter):
    layout.write(text)
    if send_enter:
        keyboard.send(Keycode.ENTER)
    keyboard.release_all()


# ---------- RUN mode: เปิด Win+R -> เปิด Chrome ผ่าน path เต็ม -> ค่อยป้อนลิงก์ ----------
CHROME_PATH = r'"C:\Program Files\Google\Chrome\Application\chrome.exe"'


def run_command(target):
    # ขั้นที่ 1: Win+R เปิด Chrome ผ่าน path เต็มโดยตรง
    keyboard.send(Keycode.WINDOWS, Keycode.R)
    time.sleep(0.5)  # รอ Run dialog เปิด
    layout.write(CHROME_PATH)
    keyboard.send(Keycode.ENTER)

    # ขั้นที่ 2: รอ Chrome เปิดขึ้นมา
    time.sleep(2.5)

    # ขั้นที่ 3: โฟกัส address bar แล้วค่อยพิมพ์ลิงก์จริง
    keyboard.send(Keycode.CONTROL, Keycode.L)  # Ctrl+L = โฟกัส address bar
    time.sleep(0.3)
    layout.write(target)
    keyboard.send(Keycode.ENTER)
    keyboard.release_all()


def execute(cfg):
    if cfg["mode"] == "PIN":
        type_pin(cfg["payload"], cfg["enter"])
    elif cfg["mode"] == "TEXT":
        type_text(cfg["payload"], cfg["enter"])
    elif cfg["mode"] == "RUN":
        run_command(cfg["payload"])


# ---------- ตั้งค่าขาปุ่มกด (ทุกปุ่มต่อขา -> 3V3) ----------
buttons = {}
last_state = {}
for name, cfg in config.items():
    pin_obj = digitalio.DigitalInOut(getattr(board, name))
    pin_obj.direction = digitalio.Direction.INPUT
    pin_obj.pull = digitalio.Pull.DOWN  # Active High (ต่อกับ 3.3V)
    buttons[name] = pin_obj
    last_state[name] = False

print("=== RP2040-Zero Macro Keypad ===")
for name, cfg in config.items():
    print(f"{name}: [{cfg['mode']}] {cfg['payload']!r} enter={cfg['enter']}")
print("Ready! Press a button to run its action...")
blink((0, 0, 255), times=1)

# ---------- Loop หลัก ----------
while True:
    for name, pin_obj in buttons.items():
        current = pin_obj.value
        if current and not last_state[name]:
            cfg = config[name]
            print(f"{name} pressed -> {cfg['mode']}")
            execute(cfg)
            print(f"done {name}")
            blink((0, 255, 0), times=3)
            time.sleep(0.3)  # debounce
        last_state[name] = current
    time.sleep(0.02)
