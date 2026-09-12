```markdown
# Macro Keypad + LED State Selector

เฟิร์มแวร์สำหรับ **RP2040-Zero** (CircuitPython) ที่ทำให้บอร์ดกลายเป็น **Macro Keypad** พร้อม **LED State Selector 4 สถานะ** โดยแต่ละ state สามารถผูก config ที่แตกต่างกันให้ปุ่มเดียวกันได้ — ปุ่มเดียวใช้งานได้ 4 อย่าง

> **เวอร์ชันนี้:** ก่อนการเพิ่มฟังก์ชัน config-driven GPIO (L+/L-, LED pins, `LED_set_up`)
> **สถานะ:** เสถียร — pin ของ L+/L- และ LED ถูก hardcode ในโค้ด
> **ไฟล์หลัก:** `code_led.py` (rename เป็น `code.py` เมื่ออัปโหลด)
> **ไฟล์ประกอบ:** `config.txt`, `TH_keyboard.txt`

---

## สารบัญ

- [1. ภาพรวม](#1-ภาพรวม)
- [2. ฮาร์ดแวร์](#2-ฮาร์ดแวร์)
- [3. รูปแบบไฟล์ config.txt](#3-รูปแบบไฟล์-configtxt)
- [4. รูปแบบไฟล์ TH_keyboard.txt](#4-รูปแบบไฟล์-th_keyboardtxt)
- [5. ฟังก์ชันทั้งหมดในโค้ด](#5-ฟังก์ชันทั้งหมดในโค้ด)
- [6. โครงสร้างข้อมูลหลัก](#6-โครงสร้างข้อมูลหลัก)
- [7. ลูปหลัก (Main Loop)](#7-ลูปหลัก-main-loop)
- [8. State Machine ของปุ่ม](#8-state-machine-ของปุ่ม)
- [9. ฟีเจอร์ที่มีในเวอร์ชันนี้](#9-ฟีเจอร์ที่มีในเวอร์ชันนี้)
- [10. ข้อจำกัด](#10-ข้อจำกัด)
- [11. วิธีอัปโหลด](#11-วิธีอัปโหลด)
- [12. ลำดับการ boot](#12-ลำดับการ-boot)
- [13. เปรียบเทียบกับเวอร์ชันถัดไป](#13-เปรียบเทียบกับเวอร์ชันถัดไป)

---

## 1. ภาพรวม

เฟิร์มแวร์นี้ทำให้ RP2040-Zero กลายเป็น **Macro Keypad** ที่มี **LED State Selector 4 สถานะ** โดยแต่ละสถานะสามารถผูก config ที่แตกต่างกันให้ปุ่มเดียวกันได้ — ทำให้ปุ่มเดียวใช้งานได้ 4 อย่าง (1 config ต่อ 1 state + ค่า fallback)

**จุดเด่น:**

- รองรับปุ่มเดี่ยวหรือปุ่มคู่ (กดพร้อมกัน)
- 4 state เลือกด้วยปุ่ม L+ / L-
- LED 3 หลอดแสดง state ปัจจุบัน
- รองรับ PIN / TEXT / THAI / VOLUME / ARROW / MEDIA
- เปิด Chrome / รัน Win+R ได้
- รองรับ Joystick แบบ analog (WASD หรือ Arrow)

---

## 2. ฮาร์ดแวร์

### 2.1 Pin ที่ hardcode ในโค้ด

| หน้าที่ | GPIO | ค่า logic | หมายเหตุ |
|---|---|---|---|
| LED1 (state 1) | GP13 | Active HIGH | ต่อผ่าน resistor |
| LED2 (state 2) | GP12 | Active HIGH | |
| LED3 (state 3) | GP11 | Active HIGH | |
| ปุ่ม L+ (เพิ่ม state) | GP10 | Active HIGH | ใช้ Pull.DOWN ภายใน |
| ปุ่ม L- (ลด state) | GP9 | Active HIGH | ใช้ Pull.DOWN ภายใน |
| NeoPixel (status) | GP16 | — | 1 ดวง |

### 2.2 Pin ที่กำหนดใน `config.txt`

| หน้าที่ | ตัวอย่าง |
|---|---|
| ปุ่ม macro | `GP28`, `GP27`, `GP26`, `GP15`, `GP14` |
| ปุ่มคู่ | `GP0+GP1` (กดพร้อมกัน) |
| Joystick (optional) | `JOYSTICK=GPx,GPy,WASD` หรือ `JOYSTICK=GPx,GPy,GPsw,WASD` |

### 2.3 LED State mapping

| State | LED1 (GP13) | LED2 (GP12) | LED3 (GP11) | config ที่ใช้ |
|-------|-------------|-------------|-------------|------------------------|
|   0   |      ดับ     |      ดับ     |      ดับ     | `GPx=...` (ไม่มี suffix) |
|   1   |      ติด     |      ดับ     |      ดับ     | `GPx_L1=...`           |
|   2   |      ดับ     |      ติด     |      ดับ     | `GPx_L2=...`           |
|   3   |      ดับ     |      ดับ     |      ติด     | `GPx_L3=...`           |

- **L+** → state เพิ่ม: `0 → 1 → 2 → 3 → 0` (วนรอบ)
- **L-** → state ลด: `0 → 3 → 2 → 1 → 0` (วนรอบ)
- **Fallback:** ถ้า state ปัจจุบันไม่มี config (`GPx_L2=` ไม่มี) → ใช้ state 0

---

## 3. รูปแบบไฟล์ `config.txt`

### 3.1 Syntax พื้นฐาน

```

ปุ่ม=ข้อความหรือลิงก์,โหมด[,CHROME][,RUN][,ENTER]

```

- `ปุ่ม` = พินเดียว (`GP28`) หรือพินคู่ (`GP0+GP1`)
- `ข้อความ` = payload ที่จะพิมพ์/รัน
- `โหมด` = ดูหัวข้อ 3.2
- `CHROME`, `RUN`, `ENTER` = ตัวเลือกเสริม ใส่ต่อท้ายได้ไม่จำกัดลำดับ

### 3.2 โหมดที่รองรับ

| โหมด | Alias | คำอธิบาย |
|---|---|---|
| `PIN` | `รหัส` | พิมพ์ตัวเลขผ่าน numpad (เสถียรทุกภาษาเครื่อง) — เปิด NumLock อัตโนมัติ |
| `TEXT` | `ข้อความ` | พิมพ์ข้อความภาษาอังกฤษ |
| `THAI` | `TH`, `ภาษาไทย` | พิมพ์ข้อความภาษาไทย (ผสมอังกฤษ/สัญลักษณ์ได้) |
| `VOLUME_UP` | `+VOLUME`, `เพิ่มเสียง` | เพิ่มเสียง (กดค้างทำซ้ำได้) |
| `VOLUME_DOWN` | `-VOLUME`, `ลดเสียง` | ลดเสียง (กดค้างทำซ้ำได้) |
| `ARROW_UP` | `ลูกศรขึ้น` | ลูกศรขึ้น (กดค้างทำซ้ำได้) |
| `ARROW_DOWN` | `ลูกศรลง` | ลูกศรลง (กดค้างทำซ้ำได้) |
| `ARROW_LEFT` | `ลูกศรซ้าย` | ลูกศรซ้าย (กดค้างทำซ้ำได้) |
| `ARROW_RIGHT` | `ลูกศรขวา` | ลูกศรขวา (กดค้างทำซ้ำได้) |
| `PREV_TRACK` | `เพลงก่อนหน้า` | เพลงก่อนหน้า |
| `PLAY_PAUSE` | `เล่นหยุด` | เล่น/หยุดเพลง |
| `NEXT_TRACK` | `เพลงถัดไป` | เพลงถัดไป |

### 3.3 ตัวเลือกเสริม

|  ตัวเลือก   |       Alias       |  ใช้กับ  |                    ผล                   |
|----------|-------------------|--------|-----------------------------------------|
| `CHROME` | `GOOGLE`, `เปิดเว็บ` | `TEXT` | แปลง payload เป็น `chrome.exe <payload>` |
| `RUN`    | `รัน`              | ทุกโหมด | เปิด Win+R พิมพ์ payload แล้ว Enter         |
| `ENTER`  | —                 | ทุกโหมด | กด Enter ต่อท้ายหลังพิมพ์                   |

> **หมายเหตุ:** ถ้ามี `RUN` โค้ดจะกด Enter ให้อัตโนมัติอยู่แล้ว ไม่ต้องใส่ `ENTER` ซ้ำ

### 3.4 ตัวอย่าง

```

PIN 4 หลัก + Enter

GP28=993180,PIN,ENTER

ข้อความ/ความอีเมล

GP15=สวัสดี,TEXT

เปิดลิงค์ผ่าน Chrome

GP15_L1=https://www.youtube.com,TEXT,CHROME,RUN

ภาษาไทย (ผสมอังกฤษ)

GP26=สวัสดีครับ,TH

```

---

## 4. รูปแบบไฟล์ `TH_keyboard.txt`

ใช้แปลงอักษรไทย → ปุ่มคีย์บอร์ด US (เพราะ CircuitPython พิมพ์ไทยตรงๆ ไม่ได้)

```

รูปแบบ

<อักษรไทย>=<ปุ่ม US>

ตัวอย่าง

ก=t
ข=b
ค=f
...

```

- รองรับ comment ด้วย `#`
- บรรทัดว่างถูกข้าม
- ถ้าอักษรไทยตัวไหนไม่อยู่ใน map จะ print `[TH] ไม่พบ: 'x'` แล้วข้าม

---

## 5. ฟังก์ชันทั้งหมดในโค้ด

### 5.1 ฟังก์ชัน parse

#### `parse_value(value) -> dict`

แปลง string ทางขวาของ `=` เป็น dict ของ config

```python
{
  "payload": "993180",
  "mode": "PIN",
  "enter": True,
  "use_chrome": False,
  "use_run": False,
}
```

· ตัวแรกของ comma = payload
· ตัวถัดไปหา mode จาก MODE_ALIASES
· CHROME / RUN / ENTER เป็น flag

get_config_key(trigger_str, state) -> str

· state 0 → คืน trigger_str
· state N → คืน f"{trigger_str}_L{N}"

---

5.2 ฟังก์ชัน LED

blink(color, times=1, delay=0.1)

กระพริบ NeoPixel (GP16) ตามสีและจำนวนครั้ง

· ใช้เป็น visual feedback เวลากดปุ่ม
· ถ้าไม่พบ NeoPixel จะ no-op

update_led_state(new_state)

· new_state % 4 เพื่อวนรอบ
· state N → 点亮 LED หลอดที่ N (index N-1)
· state 0 → ดับทั้งหมด
· print log [LED STATE] N - LED: [...]

---

5.3 ฟังก์ชันพิมพ์ข้อความ

ensure_numlock_on()

ตรวจและเปิด NumLock ถ้าปิดอยู่ (จำเป็นสำหรับ PIN mode ผ่าน numpad)

type_pin(digits, send_enter)

· เรียก ensure_numlock_on() ก่อน
· พิมพ์ทีละหลักผ่าน NUMPAD_MAP
· หน่วง 30 ms ระหว่างหลัก
· ถ้า send_enter=True → กด Enter
· release_all() ทุกครั้ง

type_text(text, send_enter)

· ใช้ layout.write() พิมพ์ทีเดียว
· ถ้า send_enter=True → กด Enter

type_thai(text, send_enter)

· วนแต่ละตัวอักษร
·   → คงไว้
· ASCII → คงไว้
· ไทย → lookup จาก thai_map
· ไทยที่ไม่พบ → print warning แล้วข้าม
· ส่งเข้า layout.write() เป็น string เดียว

run_generic(text)

· กด Win+R เปิด Run dialog
· รอ 0.5 วินาที
· พิมพ์ text
· กด Enter

---

5.4 ฟังก์ชัน execute

execute(cfg)

ตัว dispatch หลัก — รับ cfg dict แล้วทำงานตาม mode

mode เงื่อนไข การทำงาน
PIN use_run=True run_generic(payload)
PIN ปกติ type_pin(payload, enter)
THAI use_run=True run_generic(payload)
THAI ปกติ type_thai(payload, enter)
TEXT use_chrome=True prepend chrome.exe 
TEXT use_run=True run_generic(text)
TEXT ปกติ type_text(text, enter)
VOLUME_UP — ConsumerControlCode.VOLUME_INCREMENT
VOLUME_DOWN — ConsumerControlCode.VOLUME_DECREMENT
ARROW_UP — Keycode.UP_ARROW
ARROW_DOWN — Keycode.DOWN_ARROW
ARROW_LEFT — Keycode.LEFT_ARROW
ARROW_RIGHT — Keycode.RIGHT_ARROW
PREV_TRACK — SCAN_PREVIOUS_TRACK
PLAY_PAUSE — PLAY_PAUSE
NEXT_TRACK — SCAN_NEXT_TRACK

---

6. โครงสร้างข้อมูลหลัก

ตัวแปร ชนิด คำอธิบาย
config_all dict[str, dict] key = "GP28", "GP28_L1", ... → cfg dict
led_triggers dict[frozenset, str] frozenset ของ pins → base string ("GP28")
button_pins dict[str, DigitalInOut] ชื่อ pin → object
last_state dict[frozenset\|str, bool] สถานะก่อนหน้าของทุกปุ่ม (รวม L+/L-)
last_repeat_time dict[frozenset, float] timestamp ของ repeat ล่าสุด
thai_map dict[str, str] อักษรไทย → ปุ่ม US
led_outputs list[DigitalInOut] 3 หลอด เรียงตาม LED_PINS
led_state int 0..3

---

7. ลูปหลัก (Main Loop)

ทำงานทุก ~5 ms:

1. อ่านสถานะปุ่มทั้งหมด ลง states dict
2. ตรวจจับ L+ (rising edge) → update_led_state(led_state + 1) + blink สีเหลือง
3. ตรวจจับ L- (rising edge) → update_led_state(led_state - 1) + blink สีส้ม
4. วนทุก trigger:
   · คำนวณ combo_now (ทุก pin ใน combo ต้อง HIGH)
   · ดึง config_key = get_config_key(base, led_state)
   · cfg = config_all.get(config_key) — ถ้าไม่มี → fallback base (state 0)
   · ถ้า mode อยู่ใน REPEATABLE_MODES → ทำงานเมื่อกดค้าง (ทุก 0.25 s)
   · ถ้าไม่ repeat → ทำงานเฉพาะ rising edge
5. Joystick (ถ้ามี):
   · อ่าน analog X/Y
   · เทียบ deadzone (20000 / 45000)
   · ส่งปุ่มตามทิศทาง ทุก 0.15 s
   · ถ้ามี SW → กดปุ่ม = Enter
6. sleep 5 ms

---

8. State Machine ของปุ่ม

```
        rising edge          holding
IDLE ───────────────► PRESSED ─────────► REPEAT (ถ้า repeatable)
  ▲                      │
  └────── falling ───────┘
```

· Non-repeatable: ทำงานแค่ rising edge → sleep DEBOUNCE_SEC (50 ms)
· Repeatable: ทำงาน rising edge + ทุก REPEAT_SEC (250 ms) จนปล่อย

---

9. ฟีเจอร์ที่มีในเวอร์ชันนี้

· ✅ Macro keypad หลายปุ่ม (เดี่ยว + คู่)
· ✅ 4-state LED selector
· ✅ Fallback ไป state 0 อัตโนมัติ
· ✅ PIN / TEXT / THAI / VOLUME / ARROW / MEDIA
· ✅ เปิด Chrome, รัน Win+R
· ✅ ภาษาไทยผ่าน mapping table
· ✅ Joystick analog (WASD / Arrow)
· ✅ NeoPixel feedback ตอนกดปุ่ม
· ✅ Auto NumLock

---

10. ข้อจำกัด

· ❌ GPIO ของ L+/L- และ LED hardcode ในโค้ด (LED_PINS, BUTTON_L_PLUS, BUTTON_L_MINUS) — ต้องแก้โค้ดถ้าจะย้ายขา
· ❌ จำนวน LED ตายตัว 3 หลอด และ state ตายตัว 4 สถานะ
· ❌ มีโหมด MC (Minecraft) ค้างอยู่ในเอกสาร config แต่ไม่ implement จริง
· ❌ ไม่มี fallback config ที่ต่างจาก state 0

ข้อจำกัดเหล่านี้ถูกแก้ใน เวอร์ชันถัดไป ที่เปลี่ยนเป็น config-driven

---

11. วิธีอัปโหลด

1. ติดตั้ง CircuitPython ให้ RP2040-Zero
2. คัดลอกไปยังไดรฟ์ CIRCUITPY:
   · code_led.py → เปลี่ยนชื่อเป็น code.py
   · config.txt
   · TH_keyboard.txt
3. ต่อ USB → บอร์ดจะ reboot และเริ่มทำงาน
4. เปิด Serial console (115200) เพื่อดู log

---

12. ลำดับการ boot

```
1.  อ่าน config.txt (pass 1) → LED_PINS, BUTTON_L_*, JOYSTICK
2.  อ่าน config.txt (pass 2) → config_all, led_triggers
3.  อ่าน TH_keyboard.txt → thai_map
4.  sleep(3) รอ USB enumerate
5.  สร้าง Keyboard, Layout, ConsumerControl
6.  สร้าง NeoPixel (ถ้ามี)
7.  สร้าง LED outputs ทั้ง 3
8.  สร้าง button_pins จากทุก pin ที่ใช้
9.  สร้าง Joystick (ถ้ามี)
10. print ข้อมูลทั้งหมด
11. blink น้ำเงิน 1 ครั้ง
12. เข้า main loop
```

---

13. เปรียบเทียบกับเวอร์ชันถัดไป

หัวข้อ เวอร์ชันนี้ เวอร์ชันถัดไป
GPIO ของ L+/L- hardcode กำหนดใน config (GPx=,L+)
GPIO ของ LED hardcode กำหนดใน config (GPx=out_L1)
จำนวน LED 3 หลอดตายตัว กำหนดด้วย LED_set_up=(N)
จำนวน state 4 ตายตัว เท่ากับ N ใน LED_set_up
โหมด MC มีในเอกสาร ลบออก
Fallback state 0 state 0 (เหมือนเดิม)
Alias level_LED+/- ไม่มี มี

---

License

ใช้งานส่วนตัวได้อิสระ แก้ไข/ดัดแปลงได้ตามต้องการ

```
