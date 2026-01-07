import React, { useMemo, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { LayoutGrid, MessageSquare, PanelsTopLeft, Shield, Menu, LogOut, Settings, Video, Package } from "lucide-react";

import { Logo } from "../components/Logo";
import { ThemeToggle } from "../components/ThemeToggle";
import { Button } from "../components/ui/button";
import { NotificationsBell } from "../components/ui/notifications-bell";
import { NotificationsToastStack } from "../components/ui/notification-toast";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import { useAuth, canAccessAdmin, hasPermission } from "../state/auth";
import { cn } from "../lib/utils";
import { modulesApi } from "../api";

const TOOL_INFO = {
  chat: { to: "/app/chat", label: "AI Chat Assistant", icon: MessageSquare },
  video_critique: { to: "/app/video-critique", label: "Video Critique", icon: Video },
  mockup: { to: "/app/mockup", label: "Mockup Assistant", icon: LayoutGrid },
  proposals: { to: "/app/proposals", label: "Proposal Assistant", icon: PanelsTopLeft },
  // costs: { to: "/app/costs", label: "AI Costs", icon: BarChart3 },
  admin: { to: "/app/admin", label: "Admin", icon: Shield },
  asset_management: { to: "/app/asset-management", label: "Asset Management", icon: Package },
  settings: { to: "/app/settings", label: "Settings", icon: Settings },
};

const TOOL_ORDER = ["chat", "mockup", "proposals", "video_critique", "admin", "asset_management", "settings"];

function pageTitle(pathname) {
  if (pathname.includes("/app/video-critique")) return "Video Critique";
  if (pathname.includes("/app/chat")) return "AI Chat";
  if (pathname.includes("/app/mockup")) return "Mockup Studio";
  if (pathname.includes("/app/proposals")) return "Sales Proposals";
  if (pathname.includes("/app/notifications")) return "Notifications";
  // if (pathname.includes("/app/costs")) return "AI Costs";
  if (pathname.includes("/app/admin")) return "Admin Panel";
  if (pathname.includes("/app/asset-management")) return "Asset Management";
  if (pathname.includes("/app/settings")) return "Settings";
  return "Workspace";
}

function fallbackModules(user) {
  const modules = [
    {
      name: "sales",
      tools: ["chat", "video_critique", "mockup", "proposals"],
      sort_order: 1,
    },
  ];

  if (canAccessAdmin(user)) {
    modules.push({
      name: "core",
      tools: ["admin"],
      sort_order: 100,
    });
  }

  return modules;
}

function buildNavItems(modulesData, user) {
  const modules = modulesData?.modules?.length ? modulesData.modules : fallbackModules(user);
  const sorted = [...(modules || [])].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
  const allowed = new Set();

  sorted.forEach((mod) => {
    (mod.tools || []).forEach((tool) => {
      allowed.add(tool === "ai_costs" ? "costs" : tool);
    });
  });

  if (allowed.has("chat")) {
    allowed.add("video_critique");
  }

  if (canAccessAdmin(user)) {
    allowed.add("admin");
    allowed.add("asset_management");
  }

  // if (hasPermission(user, "core:ai_costs:read") || canAccessAdmin(user)) {
  //   allowed.add("costs");
  // }

  allowed.add("settings");

  const items = [];
  const seen = new Set();
  TOOL_ORDER.forEach((tool) => {
    if (!allowed.has(tool)) return;
    const info = TOOL_INFO[tool];
    if (info && !seen.has(info.to)) {
      seen.add(info.to);
      items.push(info);
    }
  });

  return items;
}

export function AppShell() {
  const { user, logout } = useAuth();
  const loc = useLocation();
  const nav = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const modulesQuery = useQuery({
    queryKey: ["modules", "accessible"],
    queryFn: modulesApi.getAccessibleModules,
  });

  const initials = useMemo(() => {
    const n = user?.name || "User";
    return n.split(" ").slice(0, 2).map(s => s[0]).join("").toUpperCase();
  }, [user]);

  const navItems = useMemo(() => buildNavItems(modulesQuery.data, user), [modulesQuery.data, user]);

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* ambient <div className="mmg-particle one" />
      <div className="mmg-particle two" />
      <div className="mmg-particle three" />
      <div className="cursor-glow" id="cursorGlow" /> */}
      

      <header className="sticky top-0 z-40">
        <div className="w-full px-6 lg:px-10">
          <div className="mmg-header-card mt-4 rounded-2xl bg-white/65 dark:bg-white/5 backdrop-blur-md shadow-soft ring-1 ring-black/5 dark:ring-white/10">
            <div className="flex items-center justify-between px-4 py-2 gap-3">
              <div className="flex items-center gap-3">
                <Logo size={64} />
                <div className="hidden sm:block text-sm text-black/50 dark:text-white/60">|</div>
                <div className="hidden sm:block text-sm font-medium text-black/70 dark:text-white/70">
                  {pageTitle(loc.pathname)}
                </div>
              </div>

              <div className="flex items-center gap-2">
                {/* Mobile sidebar toggle */}
                <Button
                  variant="ghost"
                  size="icon"
                  className="rounded-2xl lg:hidden"
                  onClick={() => setMobileOpen(true)}
                  title="Open sidebar"
                  aria-label="Open sidebar"
                >
                  <Menu size={18} />
                </Button>

                <NotificationsBell />

                <ThemeToggle />

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      className="flex items-center gap-2 rounded-2xl px-2.5 py-1.5 hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
                      aria-label="User menu"
                    >
                      <div className="h-9 w-9 rounded-2xl bg-black/5 dark:bg-white/10 flex items-center justify-center shadow-soft">
                        <span className="text-xs font-semibold">{initials}</span>
                      </div>
                      <div className="hidden sm:flex flex-col items-start leading-tight">
                        <span className="text-sm font-medium">{user?.name}</span>
                        <span className="text-xs text-black/50 dark:text-white/60">{user?.email}</span>
                      </div>
                    </button>
                  </DropdownMenuTrigger>

                  <DropdownMenuContent align="end">
                    <DropdownMenuLabel>
                      <div className="flex items-center justify-between gap-3">
                        <span className="truncate">{user?.email}</span>
                        <span className="text-xs rounded-full px-2 py-0.5 bg-black/5 dark:bg-white/10">
                          {(user?.roles || []).join(" | ")}
                        </span>
                      </div>
                    </DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onSelect={() => nav("/app/settings")}>
                      <Settings size={16} />
                      Settings
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={() => {
                        logout();
                        nav("/");
                      }}
                    >
                      <LogOut size={16} />
                      Logout
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          </div>
        </div>
      </header>

      <NotificationsToastStack />

      <div className="w-full px-6 lg:px-10 pb-4 flex-1 flex overflow-hidden min-w-0">
        <div
          className={cn(
            "mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr] flex-1 min-h-0 min-w-0",
            "transition-[grid-template-columns] duration-500",
            collapsed && "lg:grid-cols-[64px_1fr] 2xl:grid-cols-[72px_1fr]"
          )}
        >
          <aside
            className={cn(
              "hidden lg:block rounded-2xl bg-white/55 dark:bg-white/5 backdrop-blur-md shadow-soft ring-1 ring-black/5 dark:ring-white/10",
              "overflow-hidden"
            )}
          >
            <div className="flex items-center justify-between px-3 py-2">
              <div className={cn("text-s ms-3 font-semibold tracking-wide text-black/50 dark:text-white/60", collapsed && "hidden lg:block lg:sr-only")}>
                Tools
              </div>

              {/* Collapse must be icon (burger) */}
              <Button
                variant="ghost"
                size="icon"
                className="rounded-2xl"
                onClick={() => setCollapsed(v => !v)}
                title="Toggle sidebar"
                aria-label="Toggle sidebar"
              >
                <Menu size={18} />
              </Button>
            </div>

            <nav className="px-2 pb-2">
              {navItems.map((item) => {
                const active = loc.pathname === item.to || loc.pathname.startsWith(`${item.to}/`);
                const Icon = item.icon;
                return (
                  <button
                    key={item.to}
                    onClick={() => nav(item.to)}
                    className={cn(
                      "mmg-nav-btn w-full flex items-center gap-3 rounded-2xl p-2 text-sm transition-colors mb-1.5 shadow-soft",
                      active ? "mmg-nav-btn-active" : "",
                      "text-base",
                      collapsed && "lg:justify-center lg:gap-0"
                    )}
                  >
                    <span className="mmg-nav-icon h-8 w-8 shrink-0 rounded-2xl bg-black/4 dark:bg-white/8 flex items-center justify-center shadow-soft">
                      <Icon size={22} />
                    </span>
                    <span className={cn("min-w-0 truncate", collapsed && "hidden")}>{item.label}</span>
                  </button>
                );
              })}
            </nav>

            <div className="px-3 pb-3 pt-1">
              <div className={cn("h-px bg-black/5 dark:bg-white/10", collapsed && "lg:mx-auto lg:w-10")} />
            </div>
          </aside>

          <main className="min-h-0 min-w-0 h-full">
            <Outlet />
          </main>
        </div>
      </div>

      {/* Mobile slide-in sidebar */}
      <div
        className={cn(
          "fixed inset-0 z-50 lg:hidden",
          mobileOpen ? "pointer-events-auto" : "pointer-events-none"
        )}
      >
        <div
          className={cn(
            "absolute inset-0 bg-black/40 transition-opacity",
            mobileOpen ? "opacity-100" : "opacity-0"
          )}
          onClick={() => setMobileOpen(false)}
        />

        <aside
          className={cn(
            "absolute inset-y-0 left-0 w-72 max-w-full rounded-r-2xl bg-white/90 dark:bg-neutral-900/95",
            "backdrop-blur-xl shadow-2xl ring-1 ring-black/10 dark:ring-white/10",
            "transition-transform duration-200",
            mobileOpen ? "translate-x-0" : "-translate-x-full"
          )}
        >
          <div className="flex items-center justify-between px-3 py-2">
            <div className="text-sm font-semibold tracking-wide text-black/60 dark:text-white/70">
              Tools
            </div>

            <Button
              variant="ghost"
              size="icon"
              className="rounded-2xl"
              onClick={() => setMobileOpen(false)}
              title="Close sidebar"
              aria-label="Close sidebar"
            >
              <Menu size={18} />
            </Button>
          </div>

          <nav className="px-2 pb-3">
            {navItems.map((item) => {
              const active = loc.pathname === item.to || loc.pathname.startsWith(`${item.to}/`);
              const Icon = item.icon;
                return (
                  <button
                    key={item.to}
                    onClick={() => {
                      nav(item.to);
                      setMobileOpen(false);
                    }}
                    className={cn(
                      "mmg-nav-btn w-full flex items-center gap-2.5 rounded-2xl p-2.5 text-sm transition-colors mb-1.5 shadow-soft",
                      active ? "mmg-nav-btn-active" : "",
                      "text-sm"
                    )}
                  >
                  <span className="mmg-nav-icon h-9 w-9 shrink-0 rounded-2xl bg-black/4 dark:bg-white/8 flex items-center justify-center shadow-soft">
                    <Icon size={20} />
                  </span>
                  <span className="min-w-0 truncate">{item.label}</span>
                </button>
              );
            })}
          </nav>
        </aside>
      </div>

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
