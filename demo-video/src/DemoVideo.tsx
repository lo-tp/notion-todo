import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
} from "remotion";
import {fontMono, fontSans} from "./fonts";
import {theme} from "./theme";
import {session, type Message} from "./data";

// ── Timing (frames at 30fps) ──
const INITIAL_PAUSE = 50;
const USER_DUR = 50;
const TOOL_DUR = 28;
const AGENT_DUR = 60;
const TABLE_DUR = 50;
const MSG_GAP = 14;
const TURN_GAP = 40;
const END_PAUSE = 100;

function messageDuration(msg: Message): number {
  switch (msg.type) {
    case "user":
      return USER_DUR;
    case "tool":
      return TOOL_DUR;
    case "agent":
      return AGENT_DUR;
    case "table":
      return TABLE_DUR;
  }
}

const STARTS: number[] = (() => {
  const starts: number[] = [];
  let t = INITIAL_PAUSE;
  for (let i = 0; i < session.length; i++) {
    starts.push(t);
    t += messageDuration(session[i]) + MSG_GAP;
    if (i + 1 < session.length && session[i + 1].type === "user") {
      t += TURN_GAP;
    }
  }
  return starts;
})();

export const TOTAL_DURATION =
  STARTS[STARTS.length - 1] + AGENT_DUR + END_PAUSE;

// ── Layout constants ──
const WIN_W = 1600;
const WIN_H = 960;
const BAR_H = 52;
const CHAT_PAD = 40;

// ── Main component ──
export const DemoVideo: React.FC = () => {
  const frame = useCurrentFrame();

  // Compute which messages are visible and their progress
  const visibleMessages = session.map((msg, i) => {
    const start = STARTS[i];
    const dur = messageDuration(msg);
    const progress = interpolate(
      frame,
      [start, start + dur],
      [0, 1],
      {extrapolateLeft: "clamp", extrapolateRight: "clamp"},
    );
    return {msg, start, progress};
  });

  return (
    <AbsoluteFill
      name="Scene"
      style={{
        backgroundColor: "#12141a",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: fontSans,
      }}
    >
      {/* Terminal window */}
      <div
        style={{
          width: WIN_W,
          height: WIN_H,
          borderRadius: 16,
          overflow: "hidden",
          boxShadow: "0 40px 120px rgba(0,0,0,0.6)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Title bar */}
        <div
          style={{
            height: BAR_H,
            backgroundColor: "#2a2e3a",
            display: "flex",
            alignItems: "center",
            padding: "0 20px",
            gap: 8,
            flexShrink: 0,
          }}
        >
          <div style={{width: 12, height: 12, borderRadius: 6, backgroundColor: "#ff5f57"}} />
          <div style={{width: 12, height: 12, borderRadius: 6, backgroundColor: "#febc2e"}} />
          <div style={{width: 12, height: 12, borderRadius: 6, backgroundColor: "#28c840"}} />
          <span
            style={{
              position: "absolute",
              left: "50%",
              transform: "translateX(-50%)",
              color: "#8b93a6",
              fontSize: 14,
              fontFamily: fontMono,
            }}
          >
            notion-todo — agent session
          </span>
        </div>

        {/* Chat area */}
        <div
          style={{
            flex: 1,
            backgroundColor: theme.bg,
            overflow: "hidden",
            position: "relative",
          }}
        >
          {/* Content — flex-end keeps latest message at bottom */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              justifyContent: "flex-end",
              gap: 10,
              padding: CHAT_PAD,
              paddingBottom: 20,
              minHeight: "100%",
            }}
          >
            {visibleMessages.map(({msg, start, progress}, i) => (
              <ChatMessage
                key={i}
                msg={msg}
                progress={progress}
                startFrame={start}
              />
            ))}
            {/* Cursor */}
            <div
              style={{
                height: 24,
                marginTop: 6,
                display: "flex",
                alignItems: "center",
              }}
            >
              <div
                style={{
                  width: 10,
                  height: 20,
                  backgroundColor: theme.accent,
                  opacity: frame % 30 < 15 ? 1 : 0,
                }}
              />
            </div>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ── Message component ──
const ChatMessage: React.FC<{
  msg: Message;
  progress: number;
  startFrame: number;
}> = ({msg, progress, startFrame}) => {
  const fade = interpolate(
    progress,
    [0, 0.3],
    [0, 1],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.16, 1, 0.3, 1)},
  );
  const slide = interpolate(
    progress,
    [0, 0.3],
    ["0px 12px", "0px 0px"],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.16, 1, 0.3, 1)},
  );

  if (msg.type === "user") {
    return (
      <div
        style={{
          alignSelf: "flex-end",
          backgroundColor: theme.userBubble,
          color: theme.text,
          fontSize: 22,
          lineHeight: 1.4,
          borderRadius: 14,
          padding: "14px 22px",
          maxWidth: "72%",
          opacity: fade,
          translate: slide,
        }}
      >
        {msg.text}
      </div>
    );
  }

  if (msg.type === "tool") {
    return (
      <div
        style={{
          backgroundColor: theme.codeBlock,
          color: theme.code,
          fontSize: 18,
          fontFamily: fontMono,
          lineHeight: 1.5,
          borderRadius: 10,
          padding: "10px 18px",
          maxWidth: "88%",
          whiteSpace: "pre-wrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
          opacity: fade,
          translate: slide,
        }}
      >
        {msg.text}
      </div>
    );
  }

  if (msg.type === "table") {
    return (
      <div
        style={{
          opacity: fade,
          translate: slide,
          display: "grid",
          gridTemplateColumns: `repeat(${msg.headers.length}, 1fr)`,
          gap: "8px 24px",
          padding: "14px 22px",
          backgroundColor: theme.panel,
          borderRadius: 12,
          maxWidth: "60%",
        }}
      >
        {msg.headers.map((h, i) => (
          <div key={i} style={{color: theme.muted, fontSize: 18, fontWeight: 600}}>
            {h}
          </div>
        ))}
        {msg.rows.map((row, ri) =>
          row.map((cell, ci) => (
            <div
              key={`${ri}-${ci}`}
              style={{
                color: ci === 0 ? theme.text : theme.muted,
                fontSize: 20,
                fontFamily: ci === 0 ? fontSans : fontMono,
              }}
            >
              {cell}
            </div>
          )),
        )}
      </div>
    );
  }

  // agent
  return (
    <div
      style={{
        alignSelf: "flex-start",
        backgroundColor: theme.agentBubble,
        color: theme.text,
        fontSize: 22,
        lineHeight: 1.5,
        borderRadius: 14,
        padding: "14px 22px",
        maxWidth: "78%",
        whiteSpace: "pre-wrap",
        opacity: fade,
        translate: slide,
      }}
    >
      {msg.text}
    </div>
  );
};
