import React, { useState } from "react";

import { Button } from "../../../components/ui/button";
import { VideoCritiqueChatPanel } from "./VideoCritiqueChatPanel";
import { VideoCritiqueDashboard } from "./VideoCritiqueDashboard";

export function VideoCritiqueAssistantPage() {
  const [tab, setTab] = useState("chat");

  return (
    <div className="h-full min-h-0 flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Button
          variant={tab === "chat" ? "default" : "ghost"}
          className="rounded-2xl"
          onClick={() => setTab("chat")}
        >
          Chat
        </Button>
        <Button
          variant={tab === "dashboard" ? "default" : "ghost"}
          className="rounded-2xl"
          onClick={() => setTab("dashboard")}
        >
          Dashboard
        </Button>
      </div>

      <div className="flex-1 min-h-0">
        <div className={tab === "chat" ? "h-full min-h-0" : "hidden"} aria-hidden={tab !== "chat"}>
          <VideoCritiqueChatPanel />
        </div>
        <div
          className={tab === "dashboard" ? "h-full min-h-0 overflow-y-auto" : "hidden"}
          aria-hidden={tab !== "dashboard"}
        >
          <VideoCritiqueDashboard />
        </div>
      </div>
    </div>
  );
}
