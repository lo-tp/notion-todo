export type Message =
  | { type: "user"; text: string }
  | { type: "tool"; text: string }
  | { type: "agent"; text: string }
  | { type: "table"; headers: string[]; rows: string[][] };

export const session: Message[] = [
  { type: "user", text: "What's on my plate today?" },
  { type: "tool", text: "$ bash scripts/run.sh notion_cards recent" },
  { type: "tool", text: "$ bash scripts/run.sh notion_cards frequent" },
  {
    type: "agent",
    text: "You've got three on Today:\n\n1. Checkout Open Code Review\n2. prepared for manulife interview\n3. 营业执照变更 (due Oct 1)\n\nAll in Next Job / Life. Nothing priority-tagged, so it's first-come-first-served.",
  },

  {
    type: "user",
    text: "Add a task: follow up on the interview result, priority 5, due tomorrow.",
  },
  {
    type: "tool",
    text: '$ bash scripts/run.sh notion_cards create "follow up on the interview result" --status "Today" --priority 5 --due 2026-10-01 --project "Next Job"',
  },
  {
    type: "agent",
    text: 'Done — "follow up on the interview result" is on Today, P5, due tomorrow. Synced to Notion and the mirror.',
  },

  {
    type: "user",
    text: "Move it to This Week, I'm not actually following up until then.",
  },
  {
    type: "tool",
    text: '$ bash scripts/run.sh notion_cards modify "follow up on the interview" --status "This Week"',
  },
  { type: "agent", text: "Moved. It's in This Week now — still P5." },

  { type: "user", text: "What's my workload look like right now?" },
  { type: "tool", text: "SELECT status, count(*) FROM tasks WHERE ... GROUP BY status" },
  {
    type: "table",
    headers: ["Status", "Count"],
    rows: [
      ["Today", "3"],
      ["This Week", "4"],
      ["This Month", "1"],
      ["Blocked", "3"],
      ["Long Running", "18"],
      ["Ready", "3"],
    ],
  },
  {
    type: "agent",
    text: "The three blocked ones are \"Notion ToDo Phase 2\" (due Oct 1) plus two older items. Nothing stacked up on the hot path.",
  },

  {
    type: "user",
    text: "Start a timer on Checkout Open Code Review.",
  },
  {
    type: "tool",
    text: '$ bash scripts/run.sh notion_cards start "Checkout Open Code Review"',
  },
  {
    type: "agent",
    text: "Timer running on \"Checkout Open Code Review\". I'll stop it when you say so.",
  },

  { type: "user", text: "Stop it." },
  { type: "tool", text: "$ bash scripts/run.sh notion_cards end" },
  {
    type: "agent",
    text: "Stopped — 7m 42s logged on \"Checkout Open Code Review\".",
  },

  { type: "user", text: "How much time have I spent this week?" },
  {
    type: "tool",
    text: "SELECT p.name, round(sum(...), 1) AS hours FROM time_tracking tt ... WHERE tt.start_time >= datetime('now', '-7 days')",
  },
  {
    type: "table",
    headers: ["Project", "Hours"],
    rows: [
      ["Next Job", "4.2"],
      ["Life", "3.8"],
      ["Self Improvement", "1.1"],
    ],
  },
  {
    type: "agent",
    text: "Total: 9.1 hours. Next Job is carrying the load — Open Code Review and interview prep are the biggest chunks.",
  },

  {
    type: "user",
    text: 'Leave a note on the interview task: "Got a reply — they want a second round."',
  },
  {
    type: "tool",
    text: '$ bash scripts/run.sh notion_cards comment "follow up on the interview" create "Got a reply — they want a second round."',
  },
  {
    type: "agent",
    text: 'Done — "Got a reply — they want a second round." is on the task in Notion.',
  },

  {
    type: "user",
    text: "Okay, delete that follow-up task, I'll create a new one for the second round.",
  },
  {
    type: "tool",
    text: '$ bash scripts/run.sh notion_cards delete "follow up on the interview"',
  },
  {
    type: "agent",
    text: "Archived \"follow up on the interview result\" — recoverable from Notion. Mirror re-synced.",
  },

  {
    type: "user",
    text: 'Create one then: "prep for second round — system design", This Week, P4.',
  },
  {
    type: "tool",
    text: '$ bash scripts/run.sh notion_cards create "prep for second round — system design" --status "This Week" --priority 4 --project "Next Job"',
  },
  {
    type: "agent",
    text: 'Done — "prep for second round — system design" is in This Week, P4, under Next Job.',
  },
];
