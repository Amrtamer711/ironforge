import React from "react";

export function LoadingEllipsis({ text = "Loading", className = "" }) {
  return (
    <span className={["inline-flex items-center gap-2", className].filter(Boolean).join(" ")}>
      <span>{text}</span>
      <span className="mmg-ellipsis" aria-hidden="true">
        <span className="mmg-ellipsis-dot" style={{ animationDelay: "0ms" }} />
        <span className="mmg-ellipsis-dot" style={{ animationDelay: "120ms" }} />
        <span className="mmg-ellipsis-dot" style={{ animationDelay: "240ms" }} />
      </span>
    </span>
  );
}
