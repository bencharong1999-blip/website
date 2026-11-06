---
name: baoben-publish
description: โพสต์หรือตั้งเวลาโพสต์คลิปบ่าวเบนลง TikTok, Facebook, Instagram, YouTube ผ่าน Metricool (connector ที่เชื่อมไว้) และเขียนแคปชั่น/แฮชแท็ก ใช้เมื่อเบนสั่งโพสต์ชัดเจนพร้อมบอกคลิป ไม่ใช้โพสต์เอง ไม่ใช้วัดผล (ใช้ baoben-results)
---

# โพสต์คลิป — บ่าวเบน อยากเป็นไทบ้าน (ทดสอบจริง 6 พ.ย. 2026 กับ EP2)

## กติกา (จากเบน)

- โพสต์/ตั้งเวลาได้ **เฉพาะเมื่อเบนสั่งชัด** และบอกคลิปที่จะโพสต์ ถ้าไม่ชัด ให้สร้าง **แบบร่าง** (`draft: true`, `autoPublish: false`) แล้วให้เบนกดเอง
- เบนเลือกเพลงในแอป TikTok เมื่อโพสต์เอง · **โพสต์ผ่าน Metricool ใส่เพลงคลัง TikTok ไม่ได้** บอกเบนทุกครั้ง
- บันทึกรหัสโพสต์ (id/uuid) และสถานะลง Notion ส่วน 8 ทุกครั้ง

## ส่งไฟล์ (สำคัญ — เครื่อง Claude Code บนคลาวด์)

1. Claude ส่ง MP4 ให้เบนทางแชตด้วย SendUserFile **`display: "attach"`** (แบบ render บนมือถือไม่มีปุ่มดาวน์โหลด) · ไฟล์ ~100 MB ส่งได้ (ใช้ crf 20–21, maxrate 9M ยังเป็น 1080×1920 60fps)
2. เบนบันทึกลงมือถือ → อัปเข้า Google Drive → ตั้งไฟล์นั้น **"ทุกคนที่มีลิงก์ · ผู้มีสิทธิ์อ่าน"** (Metricool ไม่มีเมนูเชื่อม Drive ให้เบน — ไฟล์ส่วนตัวขึ้น `Failed to normalize media`)
3. หา ID ไฟล์: Drive `search_files` (createdTime ล่าสุด, mimeType video/)
4. หลังโพสต์ครบ บอกเบนปิดลิงก์กลับเป็น "จำกัด" (Metricool เก็บสำเนาที่ static.metricool.com แล้ว)

## สร้างโพสต์ (Metricool)

- `getBrandSettings` → blogId (brand ของช่อง) และ timezone `Asia/Bangkok`
- `createScheduledPost`: `media` = ลิงก์ Drive แบบ `https://drive.google.com/file/d/<ID>/view?usp=drivesdk`
- ต้องใส่ต่อแพลตฟอร์ม:
  - TikTok: `tiktokData.title` (**บังคับ** ไม่ใส่ = error "TikTok title is required"), `privacyOption: PUBLIC_TO_EVERYONE`, `isAigc: false` (ฟุตเทจจริง ตัดต่อด้วย ffmpeg ไม่ใช่สร้างด้วย AI)
  - Instagram: `instagramData.type: REEL`, `showReelOnFeed: true`
  - Facebook: Reel ผ่าน API ≤ ~90 วิ → คลิปยาวกว่านั้นใช้ `facebookData.type: POST` + `title`
  - YouTube: Shorts ≤ 3:00 → ยาวกว่านั้นใช้ `type: video`; ต้องมี `title`, `madeForKids: false`, `category: PEOPLE_BLOGS`, `isAiGeneratedContent: false`
- เปลี่ยนแบบร่างเป็นโพสต์จริง: `updateScheduledPost` ใช้ **media URL ของ Metricool** ที่ได้จากผลครั้งก่อน, `draft: false`, `autoPublish: true`, เวลาอนาคตอย่างน้อย ~5 นาที · id เปลี่ยนทุกครั้งที่อัปเดต (uuid คงเดิม)
- เช็กสถานะหลังเวลาโพสต์: `getScheduledPosts` (โพสต์ที่ขึ้นแล้วจะหายจากรายการ/สถานะเปลี่ยน)

## แคปชั่น (แบบที่ใช้กับ EP2)

บรรทัดแรก = ฮุกจากคำพูดจริงของเบน (คนเห็นก่อนกด "เพิ่มเติม") → 1–2 บรรทัดว่าคลิปนี้เล่าอะไร → ชวนคอมเมนต์คำเดียว (เช่น “ต่อ”) ให้ตรงกับท้ายคลิป → แฮชแท็ก 8–10 ตัวที่ตรงเนื้อหา (#บ่าวเบน #อยากเป็นไทบ้าน #ไทบ้าน #ชีวิตไทบ้าน #อีสาน #เรื่องจริง #เริ่มต้นใหม่ #ชีวิตบ้านนอก + แท็กตามเรื่อง) · ห้ามแต่งข้อเท็จจริง/รายละเอียดอุบัติเหตุ ห้ามสัญญายอดวิว

## ฉบับยาว + ฉบับสั้น

ฉบับเต็ม (2–3 นาที) สำหรับคนที่สนใจจริง/ผู้ติดตาม · ฉบับสั้น (~60 วิ, เล่าจบในตัว ไม่กั๊ก) สำหรับคนใหม่บน TikTok/Reels/Shorts/FB Reel ปิดด้วย "เรื่องเต็ม EP… ดูได้ในโปรไฟล์" · วัดผลเทียบกันด้วย baoben-results
