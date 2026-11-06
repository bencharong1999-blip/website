# รูปแบบ JSON ส่งงาน Claude ↔ Codex (v1 · ตกลงร่วมกัน 6 พ.ย. 2026)

Claude เสนอ → Codex ยอมรับพร้อมข้อชี้แจง (Drive `json-v1-review.md`) → Claude เห็นชอบทุกข้อ และทดสอบรับส่งจริงผ่านแล้ว (ดูท้ายไฟล์)

## ข้อชี้แจงที่ตกลงแล้ว (ใช้แทนข้อความเดิมที่ขัดกัน)

- `name` ห้ามซ้ำภายในตอน · ระบุต้นฉบับด้วย `original.drive_id` + `sha256` ห้ามจับคู่ด้วยชื่อไฟล์อย่างเดียว
- ไม่แบ่งไฟล์: audio/proxy เริ่มเวลา 0 และยาวครบเท่าต้นฉบับ · proxy ลด fps/ขนาดได้ แต่ฉบับจริงเรนเดอร์จากต้นฉบับเต็มเสมอ
- แบ่งไฟล์: ชื่อ `_p001`, `_p002` … แต่ละชิ้นมี `offset` และ `duration` อิงต้นฉบับ · เวลาใน `asr` บวก offset แล้ว (อิงต้นฉบับ) ห้ามบวกซ้ำ · ดูใน proxy ใช้ `local = source - offset`
- ไม่มีเสียง: `audio` และ `asr` เป็น `null` พร้อม `notes` ห้ามแต่ง transcript
- ไฟล์เล็กแต่ละไฟล์ ≤ 5,000,000 bytes (ตรวจขนาดจริงหลังเข้ารหัส)
- `deliver.drive_folder` ต้องเป็น **ID โฟลเดอร์จริง** ไม่ใช่แค่ "05"
- `stage: "preview"` ไม่บังคับ `duration_min`/`duration_max` (ใช้กับ full) · เรนเดอร์ full หลังมีบันทึกว่าเบนอนุมัติตัวอย่างแล้วเท่านั้น
- `render_result.json` บันทึก version, sha256, offset/duration ของผลลัพธ์ · เปลี่ยน input ต้องเพิ่ม `tag`
- ฟิลด์เสริมได้: `"purpose"` (เช่น `"handoff-smoke-test"`) สำหรับไฟล์ทดสอบ

ใช้กับขั้น 2 (Codex รับไฟล์ → Claude) และขั้น 4 (Claude ส่งงานเรนเดอร์ → Codex) ใน `team.md`
ไฟล์จริงของแต่ละตอนอยู่ **Drive โฟลเดอร์รายงานของตอนนั้น** เท่านั้น (มีคำเล่า/ชื่อไฟล์ของเบน) · ไฟล์นี้เก็บแค่รูปแบบ
ทุกไฟล์เข้ารหัส UTF-8 · เวลาเป็นวินาที (ทศนิยม) · ชื่อไฟล์อ้างด้วย **ชื่อกลาง** (`name`) ไม่ใช่ path ในเครื่องใครเครื่องหนึ่ง

## 1. `intake.json` — Codex ส่ง Claude หลังขั้น 2

```json
{
  "kind": "baoben-intake", "version": 1,
  "episode": "EP03", "created_by": "Codex", "created_at": "2026-11-06T10:00:00+07:00",
  "drive_folder_id": "<โฟลเดอร์ต้นฉบับ 02 ของตอน>",
  "proxy_folder_id": "<โฟลเดอร์ _proxy ของตอน>",
  "files": [
    {
      "name": "IMG_4001",
      "original": {"drive_id": "...", "file_name": "IMG_4001.MOV", "bytes": 812345678,
                   "sha256": "...", "duration": 312.48, "width": 1080, "height": 1920,
                   "fps": 59.94, "rotation": 0, "color_space": "bt709"},
      "audio": {"drive_id": "...", "file_name": "IMG_4001.m4a", "bytes": 4800000},
      "proxy": {"drive_id": "...", "file_name": "IMG_4001_540p.mp4", "bytes": 4900000},
      "asr":   {"drive_id": "...", "file_name": "IMG_4001_asr.json"},
      "notes": ""
    }
  ],
  "problems": []
}
```

กติกา
- proxy และ audio **ต้องเริ่มที่เวลา 0 ตรงกับต้นฉบับ ไม่ตัดหัวท้าย** (เวลาที่ Claude อ่านจาก proxy ใช้กับต้นฉบับได้ทันที)
- ไฟล์ยาวที่ต้องแบ่งให้ ≤ 5 MB: ใช้ชื่อ `IMG_4001_p1`, `_p2` … และใส่ `"offset": <วินาทีเริ่มในต้นฉบับ>` ในแต่ละส่วน
- `asr` = ผลดิบจาก `asr.py run` (`{"segments":[{"start","end","text"}]}`) เวลาอิงต้นฉบับ
- `problems`: ไฟล์ที่ดาวน์โหลดไม่ได้ / แฮชไม่ตรง / VFR หนัก ฯลฯ พร้อมชื่อไฟล์

## 2. `render_job.json` — Claude ส่ง Codex สำหรับขั้น 4

ชี้ไปยังไฟล์ input ที่อยู่โฟลเดอร์เดียวกันใน Drive: `cuts.json` (รูปแบบ `narration.py`), `project.json` (schema 1 ของ `render.py`), `fx.json` (รูปแบบ `fx.py`, ไม่มีก็ได้)

```json
{
  "kind": "baoben-render-job", "version": 1,
  "episode": "EP03", "cut": "main", "tag": "v01",
  "stage": "preview",
  "created_by": "Claude", "created_at": "2026-11-06T12:00:00+07:00",
  "intake": "intake.json",
  "inputs": {"cuts": "cuts.json", "project": "project.json", "fx": "fx.json"},
  "preview_shots": ["S01", "S02", "S03"],
  "target": {"duration_min": 60, "duration_max": 90, "width": 1080, "height": 1920, "fps": 60},
  "deliver": {"drive_folder": "05", "file_name": "EP03_main_v01.mp4",
              "also": ["clean", "srt"]},
  "checks": ["render.py --dry-run ไม่มี error", "qc.py ผ่าน", "Claude ดูภาพ + ฟังจุดตัด"],
  "notes": ""
}
```

กติกา
- `stage`: `"preview"` = เรนเดอร์เฉพาะ `preview_shots` (`render.py --shots`) ให้เบนตรวจก่อน · `"full"` = ทั้งตอน (ส่งหลังเบนอนุมัติตัวอย่างเท่านั้น)
- ใน `cuts.json` ใช้ `"src": "src/<name>.m4a"` · ใน `project.json` ใช้ `"source": "assets/src/<name>.<ext>"` — `<name>` ตรงกับ `files[].name` ใน intake ผู้เรนเดอร์วางต้นฉบับเต็มไว้ที่ path นั้น (ไม่ต้องแก้ JSON)
- ลำดับรัน: `narration.py cuts.json -o assets/audio/voice_raw.wav --captions text/captions.json --timeline timeline.json` → `voice.py clean` → `render.py` → `fx.py` (ถ้ามี) → `qc.py`
- ผู้เรนเดอร์เขียน `render_result.json` กลับโฟลเดอร์เดียวกัน: `{"kind":"baoben-render-result","version":1,"job_tag":"v01","stage":"preview","outputs":[{"file_name","drive_id","bytes","sha256","duration"}],"qc":"<ผล qc.py --json>","warnings":[]}`
- เปลี่ยน input หลังส่งแล้ว: เพิ่ม `tag` ใหม่ (v02) ห้ามเขียนทับ job เดิม

## 3. สถานะใน Notion

ทุกครั้งที่วางไฟล์ข้างบนใน Drive ให้เพิ่มแถวในสมุดส่งงาน (แดชบอร์ด ส่วน 8): ไฟล์อะไร · Drive ID · ขอให้อีกฝ่ายทำอะไร

## ผลทดสอบรับส่งจริง (6 พ.ย. 2026)

Codex: ดาวน์โหลด EP02_v03_for_phone.mp4 (99,871,182 bytes) → proxy 540×960 15fps 4,389,824 bytes + เสียง m4a 1,548,701 bytes → อัป Drive (โฟลเดอร์ทดลองใต้ 04) + intake.json
Claude ตรวจไขว้: ดึง proxy + เสียงผ่าน Drive connector สำเร็จ (ใต้ 5 MB) · SHA-256 ตรงกับ intake.json ทั้งสองไฟล์ · ถอดรหัสครบไม่มี error · ความยาว proxy 185.400 / เสียง 185.375 / ต้นฉบับ 185.367 วิ (ต่าง < 1 เฟรมที่ 15fps) · เสียงใน proxy ตรงกับไฟล์เสียงแยก (lag 0 ms, corr 0.988) · ภาพ 6 จุดตลอดคลิปตรงเรื่องและซับ EP2 · เสียง -16.0 LUFS
ยังไม่ทดสอบ: ไฟล์ดิบจาก iPhone (.MOV, VFR, HEVC) และการแบ่งไฟล์ (`_p001`) — ทดสอบกับฟุตเทจ EP3 จริง
