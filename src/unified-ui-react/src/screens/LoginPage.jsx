import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Eye, EyeOff, Grid2X2 } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Logo } from "../components/Logo";
import { useAuth } from "../state/auth";

export function LoginPage() {
  const { signInWithPassword, signInWithMicrosoft, signUpWithInvite } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();

  const from = useMemo(() => loc.state?.from || "/app/chat", [loc.state]);

  const [tab, setTab] = useState("signin");
  const [email, setEmail] = useState("admin@mmg.com");
  const [password, setPassword] = useState("admin123");
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState("");

  const [inviteToken, setInviteToken] = useState("");
  const [fullName, setFullName] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const { user, authReady } = useAuth();

  useEffect(() => {
    if (authReady && user) nav(from, { replace: true });
  }, [authReady, user, from, nav]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      await signInWithPassword({ email, password });
      nav(from, { replace: true });
    } catch (err) {
      setError(err?.message || "Login failed");
    }
  }

  async function onMicrosoft() {
    setError("");
    try {
      sessionStorage.setItem("postAuthRedirect", from || "/app/chat");
      await signInWithMicrosoft();
      nav(from, { replace: true });
    } catch (err) {
      setError(err?.message || "SSO failed");
    }
  }

  return (
    <div className="min-h-screen grid place-items-center px-4">
      <div className="mmg-particle one" />
      <div className="mmg-particle two" />
      <div className="mmg-particle three" />

      <div className="w-full max-w-[440px] space-y-3">
        
        <Card>
          <CardHeader className="text-center">
          <div className="flex items-center justify-center mb-5">
            <Logo size={96} />
          </div>
            <p className="text-sm text-black/60 dark:text-white/65">Sign in to continue to your workspace</p>

            {/* <div className="mt-4 grid grid-cols-2 rounded-xl overflow-hidden ring-1 ring-black/5 dark:ring-white/10">
              <button
                className={[
                  "py-2 text-sm font-semibold transition-colors",
                  tab === "signin" ? "bg-black/5 dark:bg-white/10" : "bg-transparent opacity-70 hover:opacity-100",
                ].join(" ")}
                onClick={() => setTab("signin")}
                type="button"
              >
                Sign In
              </button>
              <button
                className={[
                  "py-2 text-sm font-semibold transition-colors",
                  tab === "signup" ? "bg-black/5 dark:bg-white/10" : "bg-transparent opacity-70 hover:opacity-100",
                ].join(" ")}
                onClick={() => setTab("signup")}
                type="button"
              >
                Sign Up
              </button>
            </div> */}
          </CardHeader>

          <CardContent>
            <div className="space-y-3">
              
                <form className="space-y-3" onSubmit={onSubmit}>
                  <Field label="Email">
                    <input
                      className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-4 py-2 text-sm outline-none focus:ring-2 focus:ring-black/10 dark:focus:ring-white/15"
                      type="email"
                      autoComplete="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@email.com"
                      required
                    />
                  </Field>

                  <Field label="Password">
                    <div className="relative">
                      <input
                        className="w-full rounded-xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-4 py-2 pr-12 text-sm outline-none focus:ring-2 focus:ring-black/10 dark:focus:ring-white/15"
                        type={showPass ? "text" : "password"}
                        autoComplete="current-password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="Enter your password"
                        required
                      />
                      <button
                        type="button"
                        className="absolute right-3 top-1/2 -translate-y-1/2 opacity-70 hover:opacity-100"
                        onClick={() => setShowPass(v => !v)}
                        aria-label="Toggle password"
                      >
                        {showPass ? <EyeOff size={18} /> : <Eye size={18} />}
                      </button>
                    </div>
                  </Field>

                  {error ? (
                    <div className="text-sm text-red-700 rounded-2xl px-4 py-2 bg-black/5 dark:bg-white/10">{error}</div>
                  ) : null}

                  <Button className="w-full" size="lg" type="submit">
                    Sign In
                  </Button>

                  <p className="text-xs text-black/55 dark:text-white/60">
                    Dev mode: <code className="font-mono">admin@mmg.com</code> /{" "}
                    <code className="font-mono">admin123</code>
                  </p>
                </form>


              <div className="h-px bg-black/5 dark:bg-white/10" />

              <Button variant="secondary" size="lg" className="w-full justify-center gap-2" onClick={onMicrosoft}>
                <Grid2X2 size={18} />
                Sign in with Microsoft
              </Button>



              <Button variant="ghost" className="w-full" onClick={() => nav("/")}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <div className="text-xs font-semibold text-black/60 dark:text-white/65 mb-1">{label}</div>
      {children}
    </label>
  );
}
