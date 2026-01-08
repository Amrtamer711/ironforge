import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Grid2X2 } from "lucide-react";

import { Card, CardContent, CardHeader } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { LoadingEllipsis } from "../components/ui/loading-ellipsis";
import { Logo } from "../components/Logo";
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
    <div className="min-h-screen px-4 py-8 flex items-center justify-center">
      <div className="mmg-particle one" />
      <div className="mmg-particle two" />
      <div className="mmg-particle three" />

      <div className="w-full max-w-5xl grid grid-cols-1 lg:grid-cols-[420px_1fr] gap-6 items-stretch">
        <Card className="self-center">
          <CardHeader className="text-center">
            <div className="flex items-center justify-center mb-5">
              <Logo size={96} />
            </div>
            <p className="text-sm text-black/60 dark:text-white/65">Sign in to continue to your workspace</p>
          </CardHeader>

          <CardContent>
            <div className="space-y-3">
              {error ? (
                <div className="text-sm text-red-700 rounded-2xl px-4 py-2 bg-black/5 dark:bg-white/10">
                  {error}
                </div>
              ) : null}

              <Button
                variant="secondary"
                size="lg"
                className="w-full justify-center gap-2"
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
          </CardContent>
        </Card>

        <div className="rounded-3xl min-h-[240px] lg:min-h-[520px]" aria-hidden="true" />
      </div>
    </div>
  );
}
