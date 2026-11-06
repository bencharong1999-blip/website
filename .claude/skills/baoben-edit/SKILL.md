---
name: baoben-edit
description: ตัดต่อคลิปบ่าวเบนด้วย ffmpeg — ต่อช่วงเสียงจริง วางภาพตามเสียง ข้อความไทยบนจอ ดนตรีลดใต้เสียงพูด ปรับความดัง ส่งออก 1080x1920 60fps และเก็บโปรเจกต์แก้เฉพาะจุดได้ ใช้หลังมีบท/paper edit ที่เบนยืนยันแล้ว ไม่ใช้สำหรับเขียนบท
---

# ตัดต่อและเสียง — บ่าวเบน อยากเป็นไทบ้าน

แทน ffmpeg-skill + กระบวนการตัดต่อเล่าเรื่องของชุดเดิม ต้องมี Bash + ffmpeg

## ค่าตั้งต้น (เบนเลือกแล้ว — เปลี่ยนเมื่อเบนสั่งเท่านั้น)

- 1080 × 1920, 9:16, **60 fps คงที่**, H.264 (yuv420p, BT.709) + AAC 48 kHz, `-movflags +faststart`
- ความดังเป้าหมาย ≈ **-16 LUFS**, true peak ≤ **-1.5 dBTP**
- ข้อความบนจอ: ไทยตัวหนา ขาว-เหลือง ขอบดำ pop สั้นตามประโยค ไม่บังหน้า เว้นขอบล่าง/ขวาให้ UI ของ TikTok/Reels
- เสียงพูดจริงของเบนเป็นฐาน ดนตรีลดใต้เสียงพูด เอฟเฟกต์เฉพาะที่ช่วยเล่าเรื่อง
- ต้นฉบับเฟรมต่ำ: ส่งออก 60fps ได้ แต่ห้ามอ้างว่าเพิ่มรายละเอียด/ความลื่นจริง

## ขั้นตอน

1. **ตัวอย่างก่อนเสมอ**: ทำตัวอย่างสั้น (ฮุก 10–20 วิ, 720×1280 ได้) ให้เบนตรวจฟอนต์ สี จังหวะ ก่อนเรนเดอร์เต็ม
2. **โปรเจกต์แก้ต่อได้** ในโฟลเดอร์งานเดียว:
   ```
   project.json   # รายการช็อต: ไฟล์ต้นทาง, in/out, ข้อความ, เวลาในฉบับตัด
   captions.json  # ข้อความบนจอ + เวลา (แหล่งเดียวของ SRT/ASS)
   audio/ voice.wav music.wav sfx.wav  (แยกแทร็ก)
   cache/         # ช็อตที่เรนเดอร์แล้ว ตั้งชื่อด้วยแฮชของ input+พารามิเตอร์
   exports/
   ```
   แก้จุดเดียว → แก้ JSON แล้วเรนเดอร์เฉพาะช็อตที่ได้รับผล ใช้แคชส่วนที่เหลือ
   **เรนเดอร์ด้วย `scripts/render.py`** (อ่าน project.json schema 1 แบบเดียวกับแพ็กเกจ EP01 v02 — `shots[]` มี `source`, `source_start`, `duration`, `timeline_start`, `blur_fill`, `gentle_push`, `color`; `text/captions.json` มี `start`/`end`/`text`/`highlight`/`motion`):
   ```bash
   python3 .claude/skills/baoben-edit/scripts/render.py <โฟลเดอร์งาน> --dry-run        # ตรวจช่องว่าง/ซ้อนของช็อต ความยาวรวม ซับเกินภาพ + บอกช็อตไหนใช้แคช
   python3 .claude/skills/baoben-edit/scripts/render.py <โฟลเดอร์งาน> --shots S01,S02  # ตัวอย่างเฉพาะช็อต → exports/preview.mp4 ให้เบนตรวจก่อน
   python3 .claude/skills/baoben-edit/scripts/render.py <โฟลเดอร์งาน>                  # เรนเดอร์ส่วนที่เปลี่ยน + ต่อ master ด้วย -c copy + ใส่เสียง audio.mix
   ```
   ได้: `exports/picture_master.mp4` · `captioned_master.mp4` · `<code>_<version>_final.mp4` · `_clean.mp4` · `text/captions.ass/.srt` · `reports/render-jobs.json`
   แคช: ช็อตสะอาดผูกกับไฟล์ต้นฉบับ+จุดตัด+ค่าภาพ ช็อตมีข้อความผูกกับซับที่ทับช็อตนั้น → แก้ข้อความ 1 ประโยค เรนเดอร์ใหม่แค่ช็อตเดียว
   ฟอนต์: ใช้ `assets/fonts/` ของโปรเจกต์ถ้ามี ไม่มีใช้ Kanit ของสกิล · **EP01 v02 ใช้ "Noto Sans Thai" 84 สีเน้น `&H004CE7FF&`** (จาก project.json ใน Drive) ทำ EP ต่อเนื่องให้ใส่ค่าเดิมใน project.json
   ทดสอบ 5 พ.ย. 2026 กับไฟล์สังเคราะห์ 3 ช็อต (1080×1920, 1080×1440 blur_fill+gentle_push, 720×1280 BT.601): ได้ 450/450 เฟรม 60fps BT.709 qc.py ผ่าน (ยกเว้นความดังเพราะเสียงทดสอบเบา) แก้ซับช็อตเดียว → เรนเดอร์ใหม่ 1 ช็อต · ยังไม่ได้รันกับฟุตเทจ EP01 จริง (ZIP 480 MB ใน Drive) และยังไม่ได้เทียบภาพกับ render_project.py เดิม
3. **เตรียมเสียงพูดจากแอปบันทึกเสียง iPhone (ทดสอบแล้ว 5 พ.ย. 2026)**:
   ```bash
   python3 .claude/skills/baoben-edit/scripts/voice.py report <เสียง.m4a> -o voice_report.json   # หาช่วงพูด/ช่วงหยุดพร้อมเวลา → เลือกเทก/ประโยคที่พูดใหม่
   python3 .claude/skills/baoben-edit/scripts/voice.py clean  <เสียง.m4a> -o voice.wav --preview 10  # ตัดเสียงต่ำ 80 Hz + ลดเสียงรบกวน RNNoise + ปรับดัง -16 LUFS สองรอบ
   ```
   `--preview` สร้างไฟล์ฟัง A/B (ต้นฉบับ→หลังล้าง) ให้เบนฟังก่อนใช้ ถ้าเสียงพูดฟังแปลก/ขาด ลด `--mix 0.5` หรือ `--no-denoise` ไม่แก้ต้นฉบับ
   ผลทดสอบเสียงสังเคราะห์ (โทน + เสียงซ่า): SNR 24 → 37 dB, ดัง -16.0 LUFS, หาช่วงพูด 3 ช่วงตรงเวลา; ยังไม่ได้ทดสอบกับเสียงเบนจริง ไม่รับรองว่ากู้คำที่ลมกลบได้
   โมเดล `models/std.rnnn` (Xiph RNNoise, BSD-3) แหล่งและแฮชใน `models/README.md`
4. **ต่อเสียงพูด**: ตัดช่วงจากเทกที่เลือก ต่อด้วย crossfade สั้น (~0.06 วิ) เช่น `acrossfade=d=0.06`
5. **ภาพ**: แต่ละช็อต `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=60,format=yuv420p`
6. **ข้อความไทย**: ใช้ ASS ผ่าน `ass=` (libass จัดสระ/วรรณยุกต์ไทยถูก) ฟอนต์ Kanit Bold (OFL, ใบอนุญาต `fonts/OFL.txt`) อยู่ในสกิลแล้ว — `ass=subs.ass:fontsdir=.claude/skills/baoben-edit/fonts` แม่แบบสไตล์ขาว-เหลือง ขอบดำ pop อยู่ที่ `caption-style.ass` (ทดสอบเรนเดอร์ 1080×1920 แล้ว สระ/วรรณยุกต์ถูก)
7. **มิกซ์เสียง**: ดนตรี `sidechaincompress` หรือลด ~-18 dB ใต้เสียงพูด แล้ว `loudnorm=I=-16:TP=-1.5:LRA=11` (สองรอบถ้าต้องแม่น)
8. **ส่งออก**: `-c:v libx264 -preset medium -crf 18 -r 60 -pix_fmt yuv420p -colorspace bt709 -color_primaries bt709 -color_trc bt709 -c:a aac -b:a 192k -ar 48000 -movflags +faststart`
   ส่ง 3 ไฟล์ที่ใช้ฉบับตัดเดียวกัน: มีข้อความ · clean ไม่มีข้อความ · `.srt`
9. ส่งต่อ `baoben-qc` ตรวจก่อนบอกเบน

## แก้เฉพาะจุด

- แก้เฉพาะเสียงและเวลาไม่เปลี่ยน → ใช้ภาพเดิม `-c:v copy` แล้วประกอบเสียงใหม่
- คำพูด/เวลาเปลี่ยน → ปรับ captions.json และช็อตที่ได้รับผล ทดลองรอยต่อก่อนประกอบเต็ม
- คงขนาด/fps ของฉบับเดิม คงชื่อ/ID ไฟล์ใน Drive ถ้าอัปเดตได้ บันทึกเวอร์ชันและสิ่งที่เปลี่ยน

## ข้อห้าม

- ไม่โคลนเสียงหรือเรนเดอร์ยาวทั้งชุดล่วงหน้าก่อนเบนตรวจตัวอย่าง
- ไม่ใช้เพลง/ภาพที่ไม่รู้สิทธิ์ บันทึกแหล่งที่มาทุกครั้ง
- ถ้ารันตัดต่อไม่ได้ ส่งลำดับทำต่อใน CapCut แทน และบอกว่ายังไม่มี MP4

## ต่อเสียงจริงของเบนจากคลิปเล่าเรื่อง (ทำ EP02 ตัวอย่าง 5 พ.ย. 2026)

1. ถอดเสียงด้วย `baoben-captions/scripts/asr.py` แล้วเลือกประโยคพร้อมเวลา
2. เขียน cut list (src, in, out, gap, text, highlight) → `scripts/narration.py cuts.json -o assets/audio/voice_raw.wav --captions text/captions.json --timeline timeline.json`
3. **ตรวจจุดตัด:** ถอดเสียงไฟล์ที่ต่อแล้วซ้ำ และดูความดังทีละ 20 มิลลิวินาทีหาช่องเงียบระหว่างคำ (Whisper มักตัดพยางค์ท้าย อย่าเชื่อเวลา ASR อย่างเดียว)
4. `scripts/voice.py clean voice_raw.wav -o voice.wav` แล้วให้ project.json `audio.mix` ชี้ไฟล์นี้
5. รูปนิ่งใช้เป็นช็อตได้ (`source` เป็น .jpg) · รูปแนวนอนใส่ `blur_fill: true` · สายรัดข้อมือ/ป้ายชื่อผู้ป่วยใส่ `blur_boxes` [x, y, w, h] เป็นสัดส่วนของรูปต้นฉบับ · หัวเรื่องด้านบนใส่ caption ที่มี `pos` และ `size`
6. ฟอนต์ EP01: Noto Sans Thai Bold (OFL) อยู่ใน `fonts/` แล้ว คัดลอกเข้า `assets/fonts/` ของโปรเจกต์
7. ห้ามใส่ไฟล์เสียง/บท/รูปของเบนใน repo นี้ (repo เป็นสาธารณะ) เก็บใน Drive

## ลูกเล่นเพิ่มความตื่นเต้น (เบนขอ 5 พ.ย. 2026: ฮุกตัวหนังสือใหญ่ + ตื่นเต้น)

- ฟอนต์ที่เบนเลือก: **Kanit หนาพิเศษ** (`fonts/KanitEB.ttf`, family "Kanit EB", ตั้ง `font_bold: 0` เพราะไฟล์หนาอยู่แล้ว) ขนาดซับปกติ 92 ขอบ 8
- ฮุก: คำยักษ์เด้งตามจังหวะเสียง caption `motion: "slam"` + `pos` + `size` (คำหลัก 185 สีแดง `accent: "&H003030FF&"`, คำรอง 150) · ระวังคำยาวตกขอบตอนซูม: ทดสอบภาพก่อนเรนเดอร์ยาว
- `look` ต่อช็อต เช่น `eq=brightness=-0.07:saturation=0.65` ให้ฮุกดูหนัก
- `scripts/fx.py captioned_master.mp4 voice.wav fx.json -o final.mp4`: จอสั่น (`shake`), ซูมกระแทก (`punch`), แฟลชขาว (`flash`), จอดับ (`blackout`), เสียงประกอบสร้างเองด้วย ffmpeg (impact, boom, whoosh, heartbeat, riser) ไม่มีปัญหาลิขสิทธิ์ · qc.py จะเตือน black frames ตรงจอดับที่ตั้งใจ
- หาเวลาคำแม่น ๆ: ถอดเสียงทีละช่วงสั้นขึ้นเรื่อย ๆ (prefix decode) + ดูช่องเงียบ
- เพลง: เบนเลือกใส่เพลงในแอป TikTok ตอนโพสต์ (ไม่ใส่เพลงในไฟล์)
