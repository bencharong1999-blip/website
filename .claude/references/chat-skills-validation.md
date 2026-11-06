# ผลตรวจรุ่น 0.7.0 — 5 พฤศจิกายน 2026

- อ่านและแก้สกิลเดิม 8 รายการ เพิ่ม clip-breakdown รวม 9 สกิล; ตรวจ YAML/JSON และชื่อสกิลตรงโฟลเดอร์
- agents/openai.yaml ทั้ง 9 เปิด implicit invocation และ products CHAT/CODEX/HERMES
- manifest สองไฟล์เทียบแบบข้อมูลกับรุ่น 0.6.4 เปลี่ยนเฉพาะ version เป็น 0.7.0; defaultPrompt รูปแบบ ลำดับ ข้อความ และข้อมูลอื่นคงเดิม
- ตรวจลิงก์ไฟล์ภายในกับ inventory เดิมและไฟล์ใหม่ เก็บ scripts/assets เดิมด้วย partial overlay ไม่ขอลบไฟล์ใด
- helper Python stdlib แยก metadata จาก HTML จริงสองคลิปได้ และปฏิเสธหน้าที่ไม่มี metadata
- ทดสอบ live กับคลิป @augustvee: อ่าน metadata ซับไทย WEBVTT และภาพปกสำเร็จ evidence แยก video_viewed/audio_listened เป็น false
- ยังไม่ทดสอบการค้นพบสกิลใหม่ใน Chat ใหม่ การควบคุม Browser การฟังเสียงหรือเล่น MP4 และไม่ได้รันทดสอบ FFmpeg/ASR เดิมซ้ำเพราะไม่ได้แก้สคริปต์เหล่านั้น
- สถานะบันทึกปลั๊กอินต้องยืนยันจากผล update_plugin และ readback แยกจากผลตรวจแพ็กเกจนี้
