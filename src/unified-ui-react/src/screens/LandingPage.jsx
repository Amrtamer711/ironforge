import React from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Play } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Logo } from "../components/Logo";

export function LandingPage() {
  const nav = useNavigate();

  return (
    <div className="min-h-screen">
      {/* <div className="mmg-particle one" />
      <div className="mmg-particle two" />
      <div className="mmg-particle three" />
      <div className="cursor-glow" id="cursorGlow" /> */}

      <header className="w-full px-6 lg:px-10 py-5 flex items-center justify-between">
        <Logo size={64} />
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => nav("/login")}>Sign In</Button>
        </div>
      </header>

      <main className="w-full px-6 lg:px-10 pb-12">
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-center">
          <div className="space-y-4">
            <div className="inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs bg-black/5 dark:bg-white/10">
              <span className="h-2 w-2 rounded-full bg-black/30 dark:bg-white/40" />
              Enterprise AI Platform
            </div>
            <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight">
              The Future of{" "}
              <span className="bg-gradient-to-r from-blue-500 via-cyan-500 to-purple-500 bg-clip-text text-transparent">
                Business Intelligence
              </span>
            </h1>
            <p className="text-base sm:text-lg text-black/60 dark:text-white/65 max-w-xl">
              Unified AI-powered platform for sales proposals, mockup generation, and intelligent automation —
              with a clean, subtle, glassy UI.
            </p>

            <div className="flex flex-wrap gap-2">
              <Button size="lg" onClick={() => nav("/login")}>
                Get Started <ArrowRight className="ml-2" size={18} />
              </Button>
              <Button variant="secondary" size="lg" >
                Watch Demo <Play className="ml-2" size={18} />
              </Button>
            </div>

            <div className="flex items-center gap-4 pt-2 text-sm text-black/55 dark:text-white/60">
              <Stat value="500+" label="Enterprise Clients" />
              <Divider />
              <Stat value="10M+" label="AI Interactions" />
              <Divider />
              <Stat value="99.9%" label="Uptime" />
            </div>
          </div>

          <Card className="overflow-hidden">
            <CardHeader>
              <CardTitle>AI Assistant</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <Msg role="assistant" text="How can I help you with your sales proposal today?" />
                <Msg role="user" text="Generate a proposal for ABC Corp" />
                <Msg role="assistant" text="Thinking…" typing />
              </div>
            </CardContent>
          </Card>
        </section>

        <section className="mt-10 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          <Feature title="AI Chat Assistant" desc="Chat interface for natural language workflows." />
          <Feature title="Mockup Generator" desc="AI creative generation with compositing." />
          <Feature title="Sales Proposals" desc="Generate professional proposals quickly." />
          <Feature title="Role-Based Access" desc="Multi-role authentication and routing." />
        </section>

        <footer className="mt-10 text-xs text-black/45 dark:text-white/55">
          MMG Unified UI
        </footer>
      </main>

      {/* <script
        dangerouslySetInnerHTML={{
          __html: `
          (function(){
            const glow = document.getElementById('cursorGlow');
            if(!glow) return;
            let mouseX=0, mouseY=0, gx=0, gy=0;
            document.addEventListener('mousemove', (e)=>{ mouseX=e.clientX; mouseY=e.clientY; glow.classList.add('active'); });
            document.addEventListener('mouseleave', ()=> glow.classList.remove('active'));
            function tick(){ gx += (mouseX-gx)*0.1; gy += (mouseY-gy)*0.1; glow.style.left=gx+'px'; glow.style.top=gy+'px'; requestAnimationFrame(tick); }
            tick();
          })();
        `,
        }}
      /> */}
    </div>
  );
}

function Stat({ value, label }) {
  return (
    <div className="flex flex-col">
      <span className="font-semibold text-black/80 dark:text-white/85">{value}</span>
      <span className="text-[12px]">{label}</span>
    </div>
  );
}
function Divider() {
  return <div className="h-8 w-px bg-black/5 dark:bg-white/10" />;
}

function Msg({ role, text, typing }) {
  const isUser = role === "user";
  return (
    <div className={"flex " + (isUser ? "justify-end" : "justify-start")}>
      <div
        className={[
          "max-w-[85%] rounded-2xl px-3 py-2 text-sm shadow-soft",
          isUser
            ? "bg-black text-white dark:bg-white dark:text-black"
            : "bg-white/70 dark:bg-white/10",
          "ring-1 ring-black/5 dark:ring-white/10 backdrop-blur-xs",
        ].join(" ")}
      >
        {typing ? (
          <span className="inline-flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-current opacity-40 animate-pulse" />
            <span className="h-1.5 w-1.5 rounded-full bg-current opacity-40 animate-pulse [animation-delay:120ms]" />
            <span className="h-1.5 w-1.5 rounded-full bg-current opacity-40 animate-pulse [animation-delay:240ms]" />
          </span>
        ) : (
          text
        )}
      </div>
    </div>
  );
}

function Feature({ title, desc }) {
  return (
    <div className="rounded-2xl bg-white/55 dark:bg-white/5 backdrop-blur-md shadow-soft ring-1 ring-black/5 dark:ring-white/10 p-5">
      <div className="text-sm font-semibold">{title}</div>
      <div className="mt-1 text-sm text-black/60 dark:text-white/65">{desc}</div>
    </div>
  );
}
