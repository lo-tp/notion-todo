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
    text: "You've got three on Today:\n\n1. Refactor auth middleware\n2. Review PR #247 (P4)\n3. Fix flaky integration test (due Oct 1)\n\nTwo in Work, one in Personal. The PR review is the highest priority.",
  },

  {
    type: "user",
    text: "Add a task: write release notes for v2.0, priority 3, due Friday.",
  },
  {
    type: "tool",
    text: '$ bash scripts/run.sh notion_cards create "write release notes for v2.0" --status "Today" --priority 3 --due 2026-10-03 --project "Work"',
  },
  {
    type: "agent",
    text: 'Done — "write release notes for v2.0" is on Today, P3, due Friday. Synced to Notion and the mirror.',
  },

  {
    type: "user",
    text: "Move it to This Week, I'll get to it after the release cut.",
  },
  {
    type: "tool",
    text: '$ bash scripts/run.sh notion_cards modify "write release notes" --status "This Week"',
  },
  { type: "agent", text: "Moved. It's in This Week now — still P3." },

  { type: "user", text: "What's my workload look like right now?" },
  { type: "tool", text: "SELECT status, count(*) FROM tasks WHERE ... GROUP BY status" },
  {
    type: "table",
    headers: ["Status", "Count"],
    rows: [
      ["Today", "3"],
      ["This Week", "4"],
      ["This Month", "2"],
      ["Blocked", "1"],
      ["Ready", "3"],
      ["Long Running", "2"],
    ],
  },
  {
    type: "agent",
    text: "The blocked one is \"Set up staging environment\" (waiting on infra). Nothing else looks stacked up.",
  },

  {
    type: "user",
    text: "Start a timer on Refactor auth middleware.",
  },
  {
    type: "tool",
    text: '$ bash scripts/run.sh notion_cards start "Refactor auth middleware"',
  },
  {
    type: "agent",
    text: "Timer running on \"Refactor auth middleware\". I'll stop it when you say so.",
  },

  { type: "user", text: "Stop it." },
  { type: "tool", text: "$ bash scripts/run.sh notion_cards end" },
  {
    type: "agent",
    text: "Stopped — 23m 15s logged on \"Refactor auth middleware\".",
  },

  { type: "user", text: "How much time have I spent this week?" },
  {
    type: "tool",
    text: "SELECT p.name, round(sum(...), 1) FROM time_tracking WHERE tt.start_time >= datetime('now', '-7 days')",
  },
  {
    type: "table",
    headers: ["Project", "Hours"],
    rows: [
      ["Work", "12.4"],
      ["Personal", "3.2"],
      ["Side Projects", "1.8"],
    ],
  },
  {
    type: "agent",
    text: "Total: 17.4 hours. Work is carrying the load — the auth refactor and PR review are the biggest chunks.",
  },

  {
    type: "user",
    text: 'Leave a note on the PR review: "Requested changes — need better error handling in the token validation."',
  },
  {
    type: "tool",
    text: '$ bash scripts/run.sh notion_cards comment "Review PR #247" create "Requested changes — need better error handling in the token validation."',
  },
  {
    type: "agent",
    text: 'Done — "Requested changes — need better error handling in the token validation." is on the task in Notion.',
  },

  {
    type: "user",
    text: "Okay, archive the release notes task, I'll redo it with a better scope.",
  },
  {
    type: "tool",
    text: '$ bash scripts/run.sh notion_cards delete "write release notes for v2.0"',
  },
  {
    type: "agent",
    text: "Archived \"write release notes for v2.0\" — recoverable from Notion. Mirror re-synced.",
  },

  {
    type: "user",
    text: 'Create one then: "draft v2.0 release notes — API changes only", This Week, P3.',
  },
  {
    type: "tool",
    text: '$ bash scripts/run.sh notion_cards create "draft v2.0 release notes — API changes only" --status "This Week" --priority 3 --project "Work"',
  },
  {
    type: "agent",
    text: 'Done — "draft v2.0 release notes — API changes only" is in This Week, P3, under Work.',
  },
];
