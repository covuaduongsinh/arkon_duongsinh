"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { NotificationBell } from "@/components/notifications/notification-bell";

/* ─── Types ─── */

type NavItem = {
  label: string;
  href: string;
  icon: string;
  requiredPermissions?: string[];
};

type NavSection = {
  id: string;
  label: string;
  requiredPermissions?: string[];
  items: NavItem[];
};



/* ─── Navigation Config ─── */

const navSections: NavSection[] = [
  {
    id: "org-knowledge",
    label: "Org Knowledge",
    items: [
      { label: "Documents", href: "/knowledge", icon: "description", requiredPermissions: ["doc:read:own_dept", "doc:read:all"] },
      { label: "Wiki", href: "/wiki", icon: "auto_stories", requiredPermissions: ["wiki:read:own_dept", "wiki:read:all"] },
      { label: "Reviews", href: "/wiki/review", icon: "fact_check", requiredPermissions: ["wiki:read:own_dept", "wiki:read:all"] },
      { label: "AI Skills", href: "/skills", icon: "bolt", requiredPermissions: ["skill:read:own_dept", "skill:read:all"] },
    ],
  },
  {
    id: "organization",
    label: "Organization",
    requiredPermissions: ["org:departments:read", "org:employees:read"],
    items: [
      { label: "Departments", href: "/departments", icon: "domain", requiredPermissions: ["org:departments:read"] },
      { label: "Employees", href: "/employees", icon: "group", requiredPermissions: ["org:employees:read"] },
    ],
  },
  {
    id: "system",
    label: "System",
    requiredPermissions: ["org:audit:read", "org:settings:read", "org:settings:manage", "org:backup:manage"],
    items: [
      { label: "Audit Log", href: "/audit", icon: "policy", requiredPermissions: ["org:audit:read"] },
      { label: "Settings", href: "/settings", icon: "settings", requiredPermissions: ["org:settings:read"] },
      { label: "Backup & Restore", href: "/admin/backup", icon: "backup", requiredPermissions: ["org:backup:manage"] },
    ],
  },
];

/* ─── Hooks ─── */

function useGroupToggle(groupId: string, defaultOpen: boolean) {
  const key = `sidebar-group-${groupId}`;
  const [open, setOpen] = React.useState(() => {
    if (typeof window === "undefined") return defaultOpen;
    const stored = localStorage.getItem(key);
    return stored === null ? defaultOpen : stored === "true";
  });

  const toggle = () =>
    setOpen((v) => {
      const next = !v;
      localStorage.setItem(key, String(next));
      return next;
    });

  return [open, toggle] as const;
}

/* ─── Helpers ─── */

/** All static nav hrefs — used by isActive to pick the longest prefix match
 *  so nested links (e.g. /wiki/review) don't also activate their parent (/wiki). */
const ALL_NAV_HREFS = navSections.flatMap((s) => s.items.map((i) => i.href));

function isActive(href: string, pathname: string) {
  if (href === "/") return pathname === "/";
  if (!(pathname === href || pathname.startsWith(href + "/"))) return false;
  // A more specific sibling matched — defer to it.
  return !ALL_NAV_HREFS.some(
    (other) =>
      other !== href &&
      other.startsWith(href + "/") &&
      (pathname === other || pathname.startsWith(other + "/")),
  );
}



/* ─── Sub-components ─── */

function SidebarNavItem({
  item,
  pathname,
  indented = false,
  collapsed = false,
}: {
  item: NavItem;
  pathname: string;
  indented?: boolean;
  collapsed?: boolean;
}) {
  const { user } = useAuth();
  const active = isActive(item.href, pathname) || (item.href === "/wiki" && pathname === "/" && user?.role !== "admin");

  return (
    <Link
      href={item.href}
      title={collapsed ? item.label : undefined}
      className={cn(
        "group relative flex items-center gap-2 rounded-md px-2 py-[5px] text-[13px] transition-colors duration-100",
        collapsed ? "justify-center" : indented && "ml-3",
        active
          ? "bg-black/[0.04] font-semibold text-foreground"
          : "text-muted-foreground hover:bg-black/[0.03] hover:text-foreground"
      )}
    >
      <span
        className={cn(
          "material-symbols-outlined text-[18px] shrink-0",
          active ? "filled text-foreground" : "text-muted-foreground/70 group-hover:text-muted-foreground"
        )}
        style={{ fontVariationSettings: active ? "'FILL' 1, 'wght' 300, 'GRAD' 0, 'opsz' 20" : "'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 20" }}
      >
        {item.icon}
      </span>
      {!collapsed && <span className="truncate">{item.label}</span>}
    </Link>
  );
}

/** Static section — always expanded, no toggle */
function SidebarStaticSection({
  section,
  hasPermission,
  pathname,
  collapsed = false,
}: {
  section: NavSection;
  hasPermission: (perm: string) => boolean;
  pathname: string;
  collapsed?: boolean;
}) {
  const visibleItems = section.items.filter((i) => {
    if (!i.requiredPermissions) return true;
    return i.requiredPermissions.some((p) => hasPermission(p));
  });
  if (visibleItems.length === 0) return null;

  return (
    <div className="mt-4 first:mt-0">
      {/* Section label — hidden when collapsed (spacing separates groups) */}
      {!collapsed && (
        <div className="px-2 py-[3px] text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">
          {section.label}
        </div>
      )}

      {/* Items — always visible */}
      <div className="mt-[2px] space-y-[1px]">
        {visibleItems.map((item) => (
          <SidebarNavItem key={item.href} item={item} pathname={pathname} indented collapsed={collapsed} />
        ))}
      </div>
    </div>
  );
}



function OrgHeader({
  user,
  collapsed,
  onToggle,
}: {
  user: { name: string; role: string } | null;
  collapsed: boolean;
  onToggle: () => void;
}) {
  const router = useRouter();
  const { logout } = useAuth();

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  const dropdown = (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "flex items-center gap-2.5 rounded-md px-1.5 py-1.5 hover:bg-black/[0.03] transition-colors cursor-pointer min-w-0",
          collapsed ? "justify-center" : "flex-1"
        )}
        title={collapsed ? "Arkon — account menu" : undefined}
      >
        <Image
          src="/logo.png"
          alt="Arkon"
          width={24}
          height={24}
          className="shrink-0 rounded-[4px]"
        />
        {!collapsed && (
          <>
            <div className="flex flex-col items-start min-w-0">
              <span className="text-[15px] font-semibold text-primary truncate leading-tight font-heading">
                Arkon
              </span>
              {user && (
                <span className="text-[10px] text-muted-foreground/70 truncate leading-tight">
                  {user.name} · {user.role}
                </span>
              )}
            </div>
            <span className="material-symbols-outlined text-[14px] text-muted-foreground/50 ml-auto shrink-0">
              arrow_drop_down
            </span>
          </>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        {user && (
          <>
            <div className="px-3 py-2">
              <p className="text-sm font-medium">{user.name}</p>
              <p className="text-xs text-muted-foreground capitalize">{user.role}</p>
            </div>
            <DropdownMenuSeparator />
          </>
        )}
        <DropdownMenuItem onClick={() => router.push("/profile")}>
          <span className="material-symbols-outlined mr-2 text-base">person</span>
          Profile
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleLogout} className="text-destructive">
          <span className="material-symbols-outlined mr-2 text-base">logout</span>
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );

  const toggleBtn = (
    <button
      onClick={onToggle}
      title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      className="flex items-center justify-center rounded-md p-1 text-muted-foreground/60 hover:bg-black/[0.03] hover:text-foreground transition-colors shrink-0"
    >
      <span className="material-symbols-outlined text-[18px]">
        {collapsed ? "left_panel_open" : "left_panel_close"}
      </span>
    </button>
  );

  // Notification bell + account menu sit in the sidebar header because the
  // portal layout has no top header bar.
  if (collapsed) {
    return (
      <div className="px-2 py-1 mb-1 flex flex-col items-center gap-1">
        {dropdown}
        <NotificationBell />
        {toggleBtn}
      </div>
    );
  }

  return (
    <div className="px-2 py-1 mb-1 flex items-center gap-1">
      {dropdown}
      <NotificationBell />
      {toggleBtn}
    </div>
  );
}

/* ─── Main Sidebar ─── */

const COLLAPSED_W = 64;
const MIN_W = 200;
const MAX_W = 360;
const DEFAULT_W = 240;

export function Sidebar() {
  const pathname = usePathname();
  const { user, hasPermission } = useAuth();

  // Collapse-to-icon-rail + drag-resize, both persisted to localStorage.
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem("sidebar-collapsed") === "true";
  });
  const [width, setWidth] = useState<number>(() => {
    if (typeof window === "undefined") return DEFAULT_W;
    const stored = Number(localStorage.getItem("sidebar-width"));
    return stored >= MIN_W && stored <= MAX_W ? stored : DEFAULT_W;
  });
  const [dragging, setDragging] = useState(false);
  const widthRef = React.useRef(width);

  const toggleCollapsed = () =>
    setCollapsed((v) => {
      const next = !v;
      localStorage.setItem("sidebar-collapsed", String(next));
      return next;
    });

  const startDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    setDragging(true);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    const onMove = (ev: MouseEvent) => {
      // Sidebar is the left-most element, so clientX == desired width.
      const w = Math.min(MAX_W, Math.max(MIN_W, ev.clientX));
      widthRef.current = w;
      setWidth(w);
    };
    const onUp = () => {
      setDragging(false);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      localStorage.setItem("sidebar-width", String(widthRef.current));
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const visibleSections = navSections.filter((s) => {
    if (!s.requiredPermissions) return true;
    return s.requiredPermissions.some((p) => hasPermission(p));
  });

  return (
    <nav
      style={{ width: collapsed ? COLLAPSED_W : width }}
      className={cn(
        "hidden md:flex flex-col h-full shrink-0 bg-[#f7f5f2] border-r border-black/[0.04] relative",
        !dragging && "transition-[width] duration-200"
      )}
    >
      {/* Org Header + User */}
      <div className="pt-2">
        <OrgHeader user={user} collapsed={collapsed} onToggle={toggleCollapsed} />
      </div>

      {/* Divider */}
      <div className="mx-3 border-t border-black/[0.04] my-1" />

      {/* Navigation */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden px-2 py-1 sidebar-scrollbar">
        {/* Dashboard */}
        {user?.role === "admin" && (
          <SidebarNavItem
            item={{ label: "Dashboard", href: "/", icon: "dashboard" }}
            pathname={pathname}
            collapsed={collapsed}
          />
        )}

        {/* Static sections — no collapse */}
        {visibleSections.map((section) => (
          <SidebarStaticSection
            key={section.id}
            section={section}
            hasPermission={hasPermission}
            pathname={pathname}
            collapsed={collapsed}
          />
        ))}
      </div>

      {/* Bottom meta */}
      <div className="px-3 py-2 border-t border-black/[0.04]">
        {!collapsed && (
          <span className="text-[10px] text-muted-foreground/40 font-medium">
            On-Premise · Internal
          </span>
        )}
      </div>

      {/* Drag handle to resize width — only when expanded */}
      {!collapsed && (
        <div
          onMouseDown={startDrag}
          className="group absolute top-0 right-0 h-full w-1.5 cursor-col-resize"
          title="Drag to resize"
        >
          <div className="absolute inset-y-0 right-0 w-px bg-transparent group-hover:bg-primary/40 transition-colors" />
        </div>
      )}
    </nav>
  );
}
