# Ghostty Website

## Basics

- Verify all changes with `npm run build`
- Lint all code with `npm run lint` and fix all issues including warnings
- The site should be fully static, no server-side rendering, functions, etc.

## Code Style

- All functions and top-level constants should be documented with comments

## Project บ่าวเบน อยากเป็นไทบ้าน (content work, not the website)

When a task is about Ben's channel "บ่าวเบน อยากเป็นไทบ้าน" (clips, scripts,
footage, captions, delivery, results), do this before anything else:

- Read `.claude/skills/baoben-start/SKILL.md` first, then the skill that fits
  the task (`baoben-script`, `baoben-footage`, `baoben-edit`,
  `baoben-captions`, `baoben-qc`, `baoben-results`). They hold Ben's rules.
- The live status is the Notion page "บ่าวเบน อยากเป็นไทบ้าน — แผนหลักและงานทั้งหมด"
  (https://app.notion.com/p/40b52d4a2f43818d8e8ccf778995100f). If Notion is
  not connected, say so and work only from what Ben gives you.
- Handoff with Claude: before stopping, commit and push to the current branch
  and write in the Notion plan (or in your reply for Ben to paste) what was
  done, what was checked, file locations, and the next step.
- Never post, delete files, change sharing, or buy services unless Ben says
  so explicitly. Never invent details of Ben's accident.
- Talk with Ben in Thai.
- Working as a pair with Claude: read section 7.10 of the Notion plan,
  including the "สมุดส่งงาน Claude ↔ Codex" table, before starting. Answer
  any request addressed to you there, and add a row before you stop.
  Work meant for Ben should be reviewed by the other agent first, or marked
  "ยังไม่ผ่านตรวจไขว้" (not yet cross-checked).
- Log progress after every step, not only at the end: add a row to the
  handoff table saying which task, which step it reached, files/commit, and
  the next step. Commit and push file work at each step too, so the other
  agent can continue if you run out of quota mid-task.
