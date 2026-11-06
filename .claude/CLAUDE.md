# กติกางานช่อง บ่าวเบน อยากเป็นไทบ้าน

ชื่อช่องปัจจุบันคือ **บ่าวเบน อยากเป็นไทบ้าน** ตามคำสั่งผู้ใช้วันที่ 4 พฤศจิกายน 2026

- ใช้ชื่อนี้ในคำตอบ บท แคปชัน ชิ้นงาน และเอกสารใหม่ทั้งหมด
- “ไทบ้านคุณภาพ” เป็นชื่อเดิม พบได้ในเอกสารอ้างอิงและต้นฉบับ ห้ามนำมาใช้เป็นชื่อช่องปัจจุบัน
- `thai-work-kit` เป็นรหัสแพ็กเกจทางเทคนิค ไม่ใช่ชื่อช่อง ไม่เปลี่ยนรหัสหรือเส้นทางโดยไม่ตรวจ dependencies
- ก่อนทำงานผลิต อ่าน `.claude/references/ben-working-standard.md` และ `.claude/references/central-knowledge.md`
- ตรวจเครื่องมือจริงก่อนอ้างว่าทำงานได้ ไม่อ้างว่าเชื่อมบัญชีแล้ว หรือว่าทุกแชตเก่าและทุกโปรเจกต์ถูกส่งออกมาครบ

## โครงสร้างที่ติดตั้ง (thai-work-kit 0.7.2)

- `.claude/skills/<สกิล>/` มี 9 สกิล: plan-work, write-and-revise, summarize-evidence, quality-check,
  cross-chat-handoff, ffmpeg-skill, thai-captions, watch, clip-breakdown
- `.claude/references/` เอกสารกลางที่สกิลอ้างผ่าน `../../references/...` ห้ามย้ายแยกจาก `skills/`
- `.claude/thai-work-kit-README.md` ดัชนีปลั๊กอิน และ `.claude/thai-work-kit/` เก็บ plugin.json, inventory และ changelog ต้นฉบับ

## Runtime

- ffmpeg-skill และ watch ต้องใช้ Python 3 กับ FFmpeg/FFprobe
- thai-captions ต้องสร้าง venv แยกด้วย `python3 .claude/skills/thai-captions/scripts/setup.py --venv <dir-ใหม่>`
  และต้องดาวน์โหลดโมเดล faster-whisper จาก huggingface.co ตอนใช้ครั้งแรก
- remotion-hook ต้องรัน `npm install` ในโฟลเดอร์ของมันเอง และต้องเพิ่มไฟล์ `public/Thai.ttf` (Noto Sans Thai) ด้วยตัวเอง
