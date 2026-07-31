"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useApp } from "@/store/AppContext";
import { cn } from "@/lib/cn";
import { getApiBase } from "@/lib/api";
import {
  IconHome,
  IconMoon,
  IconPlus,
  IconSettings,
  IconSun,
} from "@/components/ui/icons";

const NAV = [
  { href: "/", label: "Projects", icon: IconHome },
  { href: "/generate", label: "New project", icon: IconPlus },
  { href: "/settings", label: "Settings", icon: IconSettings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { theme, toggleTheme } = useApp();

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-surface">
      <Link href="/" className="flex items-center gap-2.5 px-5 py-5">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent text-sm font-bold text-on-accent">
          A
        </span>
        <span className="text-sm font-semibold tracking-tight">
          ACCE <span className="text-muted">Studio</span>
        </span>
      </Link>

      <nav className="flex flex-col gap-1 px-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-surface-2 font-medium text-foreground"
                  : "text-muted hover:bg-surface-2/60 hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto flex flex-col gap-3 border-t border-border px-5 py-4">
        <button
          onClick={toggleTheme}
          className="flex items-center gap-2 text-xs text-muted transition-colors hover:text-foreground"
        >
          {theme === "dark" ? <IconSun className="h-4 w-4" /> : <IconMoon className="h-4 w-4" />}
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
        <p className="text-[11px] leading-relaxed text-muted/70">
          API <span className="font-mono text-muted">{getApiBase()}</span>
        </p>
      </div>
    </aside>
  );
}
