import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Grid2X2 } from "lucide-react";

import { Button } from "../components/ui/button";
import { LoadingEllipsis } from "../components/ui/loading-ellipsis";
import { useAuth } from "../state/auth";

export function LoginPage() {
  const { signInWithMicrosoft } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();

  const from = useMemo(() => loc.state?.from || "/app/chat", [loc.state]);

  const [error, setError] = useState("");
  const [msLoading, setMsLoading] = useState(false);

  const { user, authReady } = useAuth();

  useEffect(() => {
    if (authReady && user) nav(from, { replace: true });
  }, [authReady, user, from, nav]);

  async function onMicrosoft() {
    if (msLoading) return;
    setError("");
    try {
      setMsLoading(true);
      sessionStorage.setItem("postAuthRedirect", from || "/app/chat");
      await new Promise((resolve) => requestAnimationFrame(resolve));
      await signInWithMicrosoft();
    } catch (err) {
      setError(err?.message || "SSO failed");
      setMsLoading(false);
    }
  }

  return (
    <div className="relative min-h-screen px-4 py-8 flex items-center justify-center overflow-hidden">
      <div className="absolute inset-0 mmg-login-bg" />
      <div className="mmg-particle one" />
      <div className="mmg-particle two" />
      <div className="mmg-particle three" />

      <div className="relative z-10 w-full max-w-6xl grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-12 items-center">
        <div className="flex flex-col items-center text-center gap-4 min-h-[260px] lg:min-h-[520px] lg:pr-12 lg:border-r lg:border-black/10 dark:lg:border-white/10">
          <div className="flex flex-col items-center gap-4 pt-6">
            <img
              src="/MMG_Logo_Blk.png"
              alt="MMG"
              className="h-24 sm:h-36 lg:h-40 w-auto ml-4 dark:hidden"
            />
            <img
              src="/MMG_Logo.png"
              alt="MMG"
              className="hidden h-24 sm:h-36 lg:h-40 w-auto ml-4 dark:block"
            />
            <div className="text-2xl sm:text-3xl lg:text-4xl font-semibold tracking-[0.32em] sm:tracking-[0.35em] text-[#ca9e2c]">
              NOVA AI
            </div>
          </div>
          <div className="mt-auto pb-6 hidden lg:flex flex-nowrap items-center justify-center gap-4 text-black/40 dark:text-white/35">
            <img src="/backlite.png" alt="Backlite" className="h-8 sm:h-9 w-auto" />
            <span aria-hidden="true" className="h-6 w-px bg-black/20 dark:bg-white/20" />
            <img src="/viola.png" alt="Viola" className="h-8 sm:h-9 w-auto" />
            <span aria-hidden="true" className="h-6 w-px bg-black/20 dark:bg-white/20" />
            <img src="/media.png" alt="Media" className="h-8 sm:h-9 w-auto" />
            <span aria-hidden="true" className="h-6 w-px bg-black/20 dark:bg-white/20" />
            <img src="/purple.png" alt="Purple" className="h-8 sm:h-9 w-auto" />
          </div>
        </div>

        <div className="w-full max-w-md justify-self-center lg:pl-12">
          <div className="space-y-3 flex flex-col items-center sm:items-stretch">
            {error ? (
              <div className="text-sm text-red-700 rounded-2xl px-4 py-2 bg-black/5 dark:bg-white/10 w-full max-w-xs sm:max-w-none">
                {error}
              </div>
            ) : null}

            <Button
              variant="secondary"
              size="lg"
              className="w-full max-w-xs sm:max-w-none justify-center gap-2"
              onClick={onMicrosoft}
              disabled={msLoading}
            >
              {msLoading ? (
                <LoadingEllipsis text="Signing you in" />
              ) : (
                <>
                  <Grid2X2 size={18} />
                  Sign in with Microsoft
                </>
              )}
            </Button>
          </div>
        </div>
        <div className="flex lg:hidden flex-nowrap items-center justify-center gap-2 text-black/40 dark:text-white/35">
          <img src="/backlite.png" alt="Backlite" className="h-6 w-auto" />
          <span aria-hidden="true" className="h-4 w-px bg-black/20 dark:bg-white/20" />
          <img src="/viola.png" alt="Viola" className="h-6 w-auto" />
          <span aria-hidden="true" className="h-4 w-px bg-black/20 dark:bg-white/20" />
          <img src="/media.png" alt="Media" className="h-6 w-auto" />
          <span aria-hidden="true" className="h-4 w-px bg-black/20 dark:bg-white/20" />
          <img src="/purple.png" alt="Purple" className="h-6 w-auto" />
        </div>
      </div>
    </div>
  );
}
