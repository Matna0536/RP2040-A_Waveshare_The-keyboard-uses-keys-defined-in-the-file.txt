# code_led.py - Macro Keypad + LED State Selector
#
# ฮาร์ดแวร์:
#   LED 3 หลอด: GP13 (LED1), GP12 (LED2), GP11 (LED3) - Active HIGH
#   ปุ่ม L+ (state increment): GP10 - Active HIGH
#   ปุ่ม L- (state decrement): GP9 - Active HIGH
#
# ระบบสถานะ LED (4 สถานะ):
#   State 0: ทั้ง 3 LED ดับ → ใช้ config แบบปกติ (GP1=...)
#   State 1: LED1 สว่าง → ใช้ config GP1_L1=...
#   State 2: LED2 สว่าง → ใช้ config GP1_L2=...
#   State 3: LED3 สว่าง → ใช้ config GP1_L3=...

import time
import board
import usb_hid
import digitalio
import analogio
from adafruit_hid.keyboard import Keyboard, Keycode
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode

DEBOUNCE_SEC = 0.05
REPEAT_SEC = 0.25

REPEATABLE_MODES = (
    "VOLUME_UP", "VOLUME_DOWN",
    "ARROW_UP", "ARROW_DOWN", "ARROW_LEFT", "ARROW_RIGHT",
)

# ---------- Alias คำสั่ง ----------
MODE_ALIASES = {
    "PIN": "PIN", "รหัส": "PIN",
    "TEXT": "TEXT", "ข้อความ": "TEXT",
    "THAI": "THAI", "TH": "THAI", "ภาษาไทย": "THAI",
    "VOLUME_UP": "VOLUME_UP", "+VOLUME": "VOLUME_UP", "เพิ่มเสียง": "VOLUME_UP",
    "VOLUME_DOWN": "VOLUME_DOWN", "-VOLUME": "VOLUME_DOWN", "ลดเสียง": "VOLUME_DOWN",
    "ARROW_UP": "ARROW_UP", "ลูกศรขึ้น": "ARROW_UP",
    "ARROW_DOWN": "ARROW_DOWN", "ลูกศรลง": "ARROW_DOWN",
    "ARROW_LEFT": "ARROW_LEFT", "ลูกศรซ้าย": "ARROW_LEFT",
    "ARROW_RIGHT": "ARROW_RIGHT", "ลูกศรขวา": "ARROW_RIGHT",
    "PREV_TRACK": "PREV_TRACK", "เพลงก่อนหน้า": "PREV_TRACK",
    "PLAY_PAUSE": "PLAY_PAUSE", "เล่นหยุด": "PLAY_PAUSE",
    "NEXT_TRACK": "NEXT_TRACK", "เพลงถัดไป": "NEXT_TRACK",
}
CHROME_ALIASES = {"CHROME", "GOOGLE", "เปิดเว็บ"}
RUN_ALIASES = {"RUN", "รัน"}


def parse_value(value):
    items = value.split(",")
    payload = items[0].strip()
    mode = "TEXT"
    enter = False
    use_chrome = False
    use_run = False

    for extra in items[1:]:
        e = extra.strip()
        eu = e.upper()
        if eu in MODE_ALIASES:
            mode = MODE_ALIASES[eu]
        elif e in MODE_ALIASES:
            mode = MODE_ALIASES[e]
        elif eu in CHROME_ALIASES or e in CHROME_ALIASES:
            use_chrome = True
        elif eu in RUN_ALIASES or e in RUN_ALIASES:
            use_run = True
        elif eu == "ENTER":
            enter = True

    return {
        "payload": payload, "mode": mode, "enter": enter,
        "use_chrome": use_chrome, "use_run": use_run,
    }


# ---------- โหลด config ----------
CONFIG_PATH = "/config.txt"
config_all = {}          # เก็บทุก key: "GP28", "GP28_L1", "GP28_L2", ...
led_triggers = {}        # frozenset(pins) -> base string (เช่น "GP28")
JOYSTICK_CFG = None

LED_PINS = ("GP13", "GP12", "GP11")
BUTTON_L_PLUS = "GP10"
BUTTON_L_MINUS = "GP9"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    lines = f.readlines()

# --- pass 1: อ่านค่� hardware ก่อน ---
for line in lines:
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    up = line.upper()
    if up.startswith("LED_PINS="):
        LED_PINS = tuple(p.strip() for p in line.split("=", 1)[1].split(","))
    elif up.startswith("BUTTON_L_PLUS="):
        BUTTON_L_PLUS = line.split("=", 1)[1].strip()
    elif up.startswith("BUTTON_L_MINUS="):
        BUTTON_L_MINUS = line.split("=", 1)[1].strip()
    elif up.startswith("JOYSTICK="):
        JOYSTICK_CFG = tuple(p.strip() for p in line.split("=", 1)[1].split(","))

# --- pass 2: parse trigger ทั้งหมด ---
for line in lines:
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    up = line.upper()
    if up.startswith(("LED_PINS=", "BUTTON_L_PLUS=", "BUTTON_L_MINUS=", "JOYSTICK=")):
        continue
    if "=" not in line:
        continue

    trig_str, value = line.split("=", 1)
    trig_str = trig_str.strip()
    value = value.strip()
    if not value:
        continue

    cfg = parse_value(value)
    config_all[trig_str] = cfg

    # หา base (ตัด suffix _L1.._L3)
    base = trig_str
    for suffix in ("_L1", "_L2", "_L3"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break

    pins = tuple(p.strip() for p in base.split("+"))

    # ข้ามปุ่ม L+/L-
    if BUTTON_L_PLUS in pins or BUTTON_L_MINUS in pins:
        print(f"[SKIP] {trig_str} ชนกับปุ่ม L+/L-")
        continue

    led_triggers[frozenset(pins)] = base


def get_config_key(trigger_str, state):
    if state == 0:
        return trigger_str
    return f"{trigger_str}_L{state}"


# ---------- โหลด TH_keyboard ----------
THAI_MAP_PATH = "/TH_keyboard.txt"
thai_map = {}
try:
    with open(THAI_MAP_PATH, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.rstrip("\n")
            if " #" in raw:
                raw = raw.split(" #", 1)[0]
            raw = raw.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            th, en = raw.split("=", 1)
            th, en = th.strip(), en.strip()
            if th and en:
                thai_map[th] = en
except OSError:
    print("[TH] ไม่พบไฟล์ TH_keyboard.txt")

time.sleep(3)

keyboard = Keyboard(usb_hid.devices)
layout = KeyboardLayoutUS(keyboard)
consumer = ConsumerControl(usb_hid.devices)

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


# ---------- LED State System ----------
led_state = 0
led_outputs = []

for pin_name in LED_PINS:
    po = digitalio.DigitalInOut(getattr(board, pin_name))
    po.direction = digitalio.Direction.OUTPUT
    po.value = False
    led_outputs.append(po)


def update_led_state(new_state):
    global led_state
    led_state = new_state % 4
    for i, po in enumerate(led_outputs):
        po.value = (i == (led_state - 1)) if led_state > 0 else False
    print(f"[LED STATE] {led_state} - LED: {[po.value for po in led_outputs]}")


# ---------- PIN mode ----------
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


def type_text(text, send_enter):
    layout.write(text)
    if send_enter:
        keyboard.send(Keycode.ENTER)
    keyboard.release_all()


def type_thai(text, send_enter):
    out = []
    for ch in text:
        if ch == " ":
            out.append(" ")
        elif ord(ch) < 128:
            out.append(ch)
        elif ch in thai_map:
            out.append(thai_map[ch])
        else:
            print(f"[TH] ไม่พบ: {ch!r}")
    layout.write("".join(out))
    if send_enter:
        keyboard.send(Keycode.ENTER)
    keyboard.release_all()


def run_generic(text):
    keyboard.send(Keycode.WINDOWS, Keycode.R)
    time.sleep(0.5)
    layout.write(text)
    keyboard.send(Keycode.ENTER)
    keyboard.release_all()


def execute(cfg):
    mode = cfg["mode"]
    payload = cfg["payload"]

    if mode == "PIN":
        if cfg["use_run"]:
            run_generic(payload)
        else:
            type_pin(payload, cfg["enter"])

    elif mode == "THAI":
        if cfg["use_run"]:
            run_generic(payload)
        else:
            type_thai(payload, cfg["enter"])

    elif mode == "TEXT":
        text = ("chrome.exe " + payload) if cfg["use_chrome"] else payload
        if cfg["use_run"]:
            run_generic(text)
        else:
            type_text(text, cfg["enter"])

    elif mode == "VOLUME_UP":
        consumer.send(ConsumerControlCode.VOLUME_INCREMENT)
    elif mode == "VOLUME_DOWN":
        consumer.send(ConsumerControlCode.VOLUME_DECREMENT)
    elif mode == "ARROW_UP":
        keyboard.send(Keycode.UP_ARROW)
    elif mode == "ARROW_DOWN":
        keyboard.send(Keycode.DOWN_ARROW)
    elif mode == "ARROW_LEFT":
        keyboard.send(Keycode.LEFT_ARROW)
    elif mode == "ARROW_RIGHT":
        keyboard.send(Keycode.RIGHT_ARROW)
    elif mode == "PREV_TRACK":
        consumer.send(ConsumerControlCode.SCAN_PREVIOUS_TRACK)
    elif mode == "PLAY_PAUSE":
        consumer.send(ConsumerControlCode.PLAY_PAUSE)
    elif mode == "NEXT_TRACK":
        consumer.send(ConsumerControlCode.SCAN_NEXT_TRACK)


# ---------- ตั้งค่าปุ่ม ----------
pin_names = set()
for trig in led_triggers:
    pin_names.update(trig)

pin_names.add(BUTTON_L_PLUS)
pin_names.add(BUTTON_L_MINUS)

button_pins = {}
for name in pin_names:
    obj = digitalio.DigitalInOut(getattr(board, name))
    obj.direction = digitalio.Direction.INPUT
    obj.pull = digitalio.Pull.DOWN
    button_pins[name] = obj

last_state = {trig: False for trig in led_triggers}
last_state[BUTTON_L_PLUS] = False
last_state[BUTTON_L_MINUS] = False
last_repeat_time = {trig: 0.0 for trig in led_triggers}

# ---------- Joystick ----------
JOY_DEADZONE_LOW = 20000
JOY_DEADZONE_HIGH = 45000
JOY_REPEAT_SEC = 0.15

joy_x = joy_y = None
joy_keys = {}
HAS_JOY_SW = False

if JOYSTICK_CFG:
    cfg_parts = JOYSTICK_CFG
    if len(cfg_parts) == 4:
        x_pin, y_pin, sw_pin, keyset = cfg_parts
        joy_x = analogio.AnalogIn(getattr(board, x_pin))
        joy_y = analogio.AnalogIn(getattr(board, y_pin))
        joy_sw = digitalio.DigitalInOut(getattr(board, sw_pin))
        joy_sw.direction = digitalio.Direction.INPUT
        joy_sw.pull = digitalio.Pull.DOWN
        HAS_JOY_SW = True
    else:
        x_pin, y_pin, keyset = cfg_parts
        joy_x = analogio.AnalogIn(getattr(board, x_pin))
        joy_y = analogio.AnalogIn(getattr(board, y_pin))
        HAS_JOY_SW = False

    if keyset == "WASD":
        joy_keys = {"up": Keycode.W, "down": Keycode.S,
                     "left": Keycode.A, "right": Keycode.D}
    else:
        joy_keys = {"up": Keycode.UP_ARROW, "down": Keycode.DOWN_ARROW,
                     "left": Keycode.LEFT_ARROW, "right": Keycode.RIGHT_ARROW}

joy_last_repeat = {"up": 0.0, "down": 0.0, "left": 0.0, "right": 0.0}
joy_sw_last_state = False

print("=== RP2040-Zero Macro Keypad + LED State ===")
print(f"LED Pins: {LED_PINS}")
print(f"L+ Button: {BUTTON_L_PLUS}, L- Button: {BUTTON_L_MINUS}")
print(f"Triggers:")
for key, cfg in config_all.items():
    print(f"  {key}: [{cfg['mode']}] {cfg['payload']!r}")
print("Ready!")
blink((0, 0, 255), times=1)

# ---------- Loop หลัก ----------
while True:
    now = time.monotonic()
    states = {name: button_pins[name].value for name in pin_names}

    # ตรวจจับปุ่ม L+/L-
    l_plus_now = states[BUTTON_L_PLUS]
    l_minus_now = states[BUTTON_L_MINUS]

    if l_plus_now and not last_state[BUTTON_L_PLUS]:
        update_led_state(led_state + 1)
        blink((255, 200, 0), times=1)

    if l_minus_now and not last_state[BUTTON_L_MINUS]:
        update_led_state(led_state - 1)
        blink((200, 100, 0), times=1)

    last_state[BUTTON_L_PLUS] = l_plus_now
    last_state[BUTTON_L_MINUS] = l_minus_now

    # ตรวจจับปุ่มข้อมูลอื่น
    for trig, base_str in led_triggers.items():
        combo_now = all(states[p] for p in trig)

        config_key = get_config_key(base_str, led_state)
        cfg = config_all.get(config_key)

        # fallback ไป state 0 ถ้า state ปัจจุบันไม่มี config
        if cfg is None and led_state != 0:
            cfg = config_all.get(base_str)

        if cfg is None:
            last_state[trig] = combo_now
            continue

        repeatable = cfg["mode"] in REPEATABLE_MODES

        if repeatable:
            if combo_now:
                if not last_state[trig] or (now - last_repeat_time[trig]) >= REPEAT_SEC:
                    print(f"trigger: {config_key} -> {cfg['mode']} (LED {led_state})")
                    execute(cfg)
                    last_repeat_time[trig] = now
                    blink((0, 255, 0), times=1, delay=0.03)
        else:
            if combo_now and not last_state[trig]:
                print(f"trigger: {config_key} -> {cfg['mode']} (LED {led_state})")
                execute(cfg)
                blink((0, 255, 0), times=2)
                time.sleep(DEBOUNCE_SEC)

        last_state[trig] = combo_now

    # Joystick
    if JOYSTICK_CFG:
        x_val = joy_x.value
        y_val = joy_y.value
        directions = {
            "left":  x_val < JOY_DEADZONE_LOW,
            "right": x_val > JOY_DEADZONE_HIGH,
            "up":    y_val > JOY_DEADZONE_HIGH,
            "down":  y_val < JOY_DEADZONE_LOW,
        }
        for d, active in directions.items():
            if active and (now - joy_last_repeat[d]) >= JOY_REPEAT_SEC:
                keyboard.send(joy_keys[d])
                joy_last_repeat[d] = now

        if HAS_JOY_SW:
            sw_now = joy_sw.value
            if sw_now and not joy_sw_last_state:
                keyboard.send(Keycode.ENTER)
            joy_sw_last_state = sw_now

    time.sleep(0.005)
