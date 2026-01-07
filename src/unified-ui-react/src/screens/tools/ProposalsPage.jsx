import React, { useState } from "react";
import { Button } from "../../components/ui/button";
import * as GenerateTabModule from "./proposals/GenerateTab";
import * as HistoryTabModule from "./proposals/HistoryTab";

export function ProposalsPage() {
  const [tab, setTab] = useState("generate");

  return (
    <div className="h-full min-h-0 flex flex-col gap-3">
      <div className="flex items-center gap-3 overflow-x-auto">
        <Button
          variant={tab === "generate" ? "default" : "ghost"}
          onClick={() => setTab("generate")}
          className="rounded-2xl shrink-0"
        >
          Generate
        </Button>
        <Button
          variant={tab === "history" ? "default" : "ghost"}
          onClick={() => setTab("history")}
          className="rounded-2xl shrink-0"
        >
          History
        </Button>
      </div>
      <div className="flex-1 min-h-0">
        <div className={tab === "generate" ? "h-full min-h-0" : "hidden"} aria-hidden={tab !== "generate"}>
          <GenerateTabModule.GeneratePanel />
        </div>
        <div className={tab === "history" ? "h-full min-h-0" : "hidden"} aria-hidden={tab !== "history"}>
          <HistoryTabModule.HistoryPanel />
        </div>
      </div>
    </div>
  );
}
