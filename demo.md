# notion-todo demo — screen recording script

A single continuous agent session, recorded as a screen capture. The user types natural-language prompts; the agent calls the notion-sync skill (CLI + mirror queries) and answers in plain language. No act titles — it just looks like a real terminal chat.

**Prereqs:** repo cloned, `uv sync` done, `.env` with `NOTION_TOKEN` + database ids. The mirror should have been synced at least once.

**Recording notes:**
- Terminal: light background, system font, 14px. Show the full agent chat interface (user → agent).
- Agent tool calls appear as collapsed/expanded code blocks in the chat — the viewer sees the commands the agent ran, then the agent's text response.
- Keep the cursor blinking at the prompt between turns. Let responses appear character-by-character (typewriter) for the agent's text; tool output appears all-at-once.
- Total runtime target: ~2–3 minutes.

---

## Session

**User:**
> What's on my plate today?

**Agent** *(tool: `bash <root>/scripts/run.sh notion_cards recent`)*
**Agent** *(tool: `bash <root>/scripts/run.sh notion_cards frequent`)*
**Agent** *(tool: mirror query — "What's on my plate today?")*

> You've got three on Today:
>
> 1. Checkout Open Code Review
> 2. prepared for manulife interview
> 3. 营业执照变更 (due Oct 1)
>
> All in Next Job / Life. Nothing priority-tagged, so it's first-come-first-served.

---

**User:**
> Add a task: follow up on the interview result, priority 5, due tomorrow.

**Agent** *(tool: `bash <root>/scripts/run.sh notion_cards create "follow up on the interview result" --status "Today" --priority 5 --due YYYY-MM-DD --project "Next Job"`)*

> Done — "follow up on the interview result" is on Today, P5, due tomorrow. Synced to Notion and the mirror.

---

**User:**
> Move it to This Week, I'm not actually following up until then.

**Agent** *(tool: `bash <root>/scripts/run.sh notion_cards modify "follow up on the interview" --status "This Week"`)*

> Moved. It's in This Week now — still P5.

---

**User:**
> What's my workload look like right now?

**Agent** *(tool: mirror query — "Workload overview")*

> Here's the breakdown:
>
> | Status | Count |
> |---|---|
> | Today | 3 |
> | This Week | 4 |
> | This Month | 1 |
> | Blocked | 3 |
> | Long Running | 18 |
> | Ready | 3 |
>
> The three blocked ones are "Notion ToDo Phase 2" (due Oct 1), plus two older items. Nothing looks stacked up on the hot path.

---

**User:**
> Start a timer on Checkout Open Code Review.

**Agent** *(tool: `bash <root>/scripts/run.sh notion_cards start "Checkout Open Code Review"`)*

> Timer running on "Checkout Open Code Review". I'll stop it when you say so.

*(small pause — let the viewer feel the rhythm)*

---

**User:**
> Stop it.

**Agent** *(tool: `bash <root>/scripts/run.sh notion_cards end`)*

> Stopped — 7m 42s logged on "Checkout Open Code Review".

---

**User:**
> How much time have I spent this week?

**Agent** *(tool: mirror query — "Time spent this week per project")*

> This week across your projects:
>
> | Project | Hours |
> |---|---|
> | Next Job | 4.2 |
> | Life | 3.8 |
> | Self Improvement | 1.1 |
>
> Total: 9.1 hours. Next Job is carrying the load — the Open Code Review and interview prep are the biggest chunks.

---

**User:**
> Leave a note on the interview task: "Got a reply — they want a second round."

**Agent** *(tool: `bash <root>/scripts/run.sh notion_cards comment "follow up on the interview" create "Got a reply — they want a second round."`)*

> Done — "Got a reply — they want a second round." is on the task in Notion.

---

**User:**
> Okay, delete that follow-up task, I'll create a new one for the second round.

**Agent** *(tool: `bash <root>/scripts/run.sh notion_cards delete "follow up on the interview"`)*

> Archived "follow up on the interview result" — recoverable from Notion. Mirror re-synced.

---

**User:**
> Create one then: "prep for second round — system design", This Week, P4.

**Agent** *(tool: `bash <root>/scripts/run.sh notion_cards create "prep for second round — system design" --status "This Week" --priority 4 --project "Next Job"`)*

> Done — "prep for second round — system design" is in This Week, P4, under Next Job.

---

*End of session. Cursor blinks. Fade out.*
