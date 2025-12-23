import React from "react";
import { Button } from "../components/ui/button";

export function AccessPending({ email, message, onSignOut }) {
  return (
    <div className="min-h-screen grid place-items-center px-4">
      <div className="w-full max-w-[520px] space-y-4 rounded-2xl bg-white/60 dark:bg-white/5 backdrop-blur-md shadow-soft ring-1 ring-black/5 dark:ring-white/10 p-6 text-center">
        <div className="text-2xl font-semibold">Access Pending</div>
        <div className="text-sm text-black/60 dark:text-white/65">
          {message || "Your account is pending administrator approval."}
        </div>
        {email ? (
          <div className="text-xs text-black/55 dark:text-white/60">
            Signed in as <strong>{email}</strong>
          </div>
        ) : null}
        <div className="flex justify-center pt-2">
          <Button variant="secondary" onClick={onSignOut}>
            Sign Out
          </Button>
        </div>
      </div>
    </div>
  );
}
