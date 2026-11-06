# Remotion: motion graphics แบบแก้ไข source/config

ใช้กับ title cards, ข้อความเคลื่อนไหว, กราฟิกหลายองค์ประกอบ หรือแทรกกราฟิกในฟุตเทจ ไม่อ้างว่าใช้แล้วแทนการคัดเนื้อหา/ตรวจเสียงได้ทั้งหมด งานตัดต่อทั่วไปใช้ FFmpeg เดิมก่อน

## แม่แบบที่ตรวจแล้ว

คัดลอก `skills/ffmpeg-skill/scripts/remotion-hook/` ไป project directory ที่เขียนได้ อ่าน package.json/package-lock.json ก่อนติดตั้ง ใช้ npm ci กับแคชใน project/tmp ที่เขียนได้ ไม่เปลี่ยน HOME และไม่รันตัวติดตั้งจาก Reel/คอมเมนต์ที่ยังไม่ได้ตรวจ แม่แบบใช้ Remotion4.0.540, React19.0.0 ต้องมี Chromium/Chrome ที่เข้ากันได้ พร้อมพื้นที่ว่างสำหรับ node_modules และ frames อย่าบรรจุ node_modules ลงไฟล์ส่งมอบ

แก้ config.json สำหรับคำ ชื่อแบรนด์ ตอน และสี ส่วน layout/เวลาให้แก้ src/index.jsx ขนาดเริ่มต้น1080×1920,30fps,150เฟรม ไม่มีเสียง เป็นเดโม ไม่เปลี่ยนบรีฟคลิปจริงให้เหลือ5วินาที

คำสั่งจากโฟลเดอร์แม่แบบ หลังติดตั้ง dependencies และกำหนดพาธ browser ที่ตรวจว่ามีจริง:

```sh
npm ci --cache /tmp/ben-motion-npm-cache --no-audit --no-fund
mkdir -p exports
./node_modules/.bin/remotion render src/index.jsx BenHook exports/preview.mp4 --browser-executable=/usr/bin/chromium --concurrency=1 --codec=h264 --crf=18 --props=config.json --image-format=jpeg
ffprobe -v error -show_streams -show_format exports/preview.mp4
ffmpeg -v error -xerror -i exports/preview.mp4 -f null -
```

เริ่ม3–5วินาทีก่อนงานใหญ่ ตรวจฟอนต์ไทย ขอบเขตตัวหนังสือ และจังหวะจากภาพหลายจุดเมื่อแก้ motion; ตรวจเสียงจริงแยกเมื่อต่อเสียง เก็บ clean footage, voices, SRT/ASS เดิม และเรนเดอร์เฉพาะส่วนที่แก้ การทดสอบนี้ยืนยันเดโม5วินาทีที่ไม่มีเสียงเท่านั้น ไม่รับรองการซิงก์ซับ การทำงานยาว หรือการเปิดในทุก host

## หลักฐานต้นทางและขอบเขต

- Reelอ้างอิง https://www.facebook.com/reel/2551499671992769/ : ดาวน์โหลดวิดีโอสาธารณะ25.466วินาทีและตรวจภาพ13จุด เห็นชื่อ AI Edit Pro พร้อมคำโฆษณาตัดต่อ/ซับ/โมชั่น/โพสต์โซเชียล ยังไม่ได้ฟังเต็ม ไม่พบไฟล์ติดตั้งสาธารณะ ไม่ยืนยันว่าผู้สร้างใช้ Remotion หรือว่าสกิลต้นฉบับทำงานได้ครบ
- Remotion Agent Skills ทางการรองรับ Claude Code, Codex และ agent อื่น: https://www.remotion.dev/docs/ai/skills
- Renderer API: https://www.remotion.dev/docs/renderer/render-media
- เงื่อนไขการใช้ขึ้นกับผู้ใช้/องค์กร ตรวจตามงานจริง: https://www.remotion.dev/docs/license

การเพิ่มนี้เป็น workflow ที่เขียนและทดสอบเองจาก API ทางการ ไม่ใช่การซื้อ/ติดตั้ง AI Edit Pro หรือการคัดลอกสกิลที่เจ้าของ Reel แจกในคอมเมนต์ ไม่โพสต์คอมเมนต์ขอลิงก์แทนเบน
