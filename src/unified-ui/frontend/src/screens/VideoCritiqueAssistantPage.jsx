import React, { useState } from "react";

import { Button } from "../components/ui/button";
import { VideoCritiqueChatPanel } from "./critique/VideoCritiqueChatPanel";
import { VideoCritiqueDashboard } from "./critique/VideoCritiqueDashboard";

export function VideoCritiqueAssistantPage() {
  const [tab, setTab] = useState("chat");

  return (
    <div className="h-full min-h-0 flex flex-col gap-4">
      <div className="flex items-center gap-2 py-1">
        <Button
          variant={tab === "chat" ? "default" : "ghost"}
          className={`rounded-2xl mmg-tab-btn ${tab === "chat" ? "mmg-tab-btn-active" : ""}`}
          onClick={() => setTab("chat")}
        >
          Chat
        </Button>
        <Button
          variant={tab === "dashboard" ? "default" : "ghost"}
          className={`rounded-2xl mmg-tab-btn ${tab === "dashboard" ? "mmg-tab-btn-active" : ""}`}
          onClick={() => setTab("dashboard")}
        >
          Dashboard
        </Button>
      </div>

      <div className="flex-1 min-h-0">
        <div className={tab === "chat" ? "h-full" : "hidden"} aria-hidden={tab !== "chat"}>
          <VideoCritiqueChatPanel />
        </div>
        <div
          className={tab === "dashboard" ? "h-full overflow-y-auto px-2 py-1" : "hidden"}
          aria-hidden={tab !== "dashboard"}
        >
          <VideoCritiqueDashboard />
        </div>
      </div>
    </div>
  );
}
