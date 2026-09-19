"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Landmark,
  GraduationCap,
  ContactRound,
  Search,
  Users,
  Mail,
  Inbox,
  Send,
  ChartNoAxesCombined,
  Settings2,
  ArrowUpRight,
  ChevronDown,
  PanelLeftClose,
  Globe2,
  Moon,
  Sun,
  ShieldCheck,
  GitBranch,
  Clock,
} from "lucide-react";
import { AppProvider, useApp } from "@/lib/context";
import { Nav } from "./ui";
import { Dashboard, ComingSoon } from "./overview";
import FinanceFlow from "./finance-flow";
import Personas from "./personas";
import { PeopleSearch, Contacts } from "./people";
import EmailStudio from "./email-studio";
import AuthGate from "./auth-gate";
import Admin from "./admin";
import Sequences from "./sequences";
import { Mailboxes, MailInbox, Outbox, Followups } from "./mail-center";
import { post } from "@/lib/api";

const main = [
  ["/", "Dashboard", "总览", LayoutDashboard],
  ["/personas", "Personas", "职业画像", ContactRound],
  ["/people", "People Search", "人员搜索", Search],
  ["/contacts", "Contacts", "联系人", Users],
  ["/email", "Email Studio", "邮件工作室", Mail],
  ["/sequences", "Sequences", "邮件序列", GitBranch],
] as const;
const later = [
  ["/mailboxes", "Mailboxes", "邮箱", Mail],
  ["/inbox", "Inbox", "收件箱", Inbox],
  ["/outbox", "Outbox", "发件箱", Send],
  ["/followups", "Follow-ups", "手动跟进", Clock],
  ["/campaigns", "Campaigns", "外联活动", Send],
  ["/analytics", "Analytics", "分析", ChartNoAxesCombined],
] as const;
function Shell() {
  const path = usePathname(),
    { t, locale, setLocale, config, error, loading, refresh, guard, notify } =
      useApp();
  const [theme, setTheme] = useState<"light" | "dark">("light");
  useEffect(() => {
    const active = document.documentElement.dataset.theme;
    if (active === "light" || active === "dark") setTheme(active);
  }, []);
  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    localStorage.setItem("connectai-theme", next);
  };
  const current = [
    ...main,
    ...later,
    ["/finance", "Finance", "金融", Landmark],
    ["/academic", "Academic", "学术", GraduationCap],
    ["/settings", "Settings", "设置", Settings2],
    ["/settings/integrations", "Integrations", "集成", Settings2],
    ["/admin", "Administration", "管理员后台", ShieldCheck],
  ].find((x) => x[0] === path);
  const title = current
    ? t(String(current[1]), String(current[2]))
    : t("Page not found", "页面不存在");
  return (
    <div className="workspace">
      <aside className="sidebar">
        <Nav href="/" className="brand" aria-label="Connact.ai home">
          <img
            className="brand-logo brand-logo-light"
            src="/connact-logo-dark.svg"
            alt="Connact.ai"
          />
          <img
            className="brand-logo brand-logo-dark"
            src="/connact-logo.svg"
            alt=""
          />
          <img
            className="brand-logo-compact"
            src="/connact-icon.svg"
            alt="Connact.ai"
          />
        </Nav>
        <div className="workspace-switch">
          <span className="workspace-monogram">P</span>
          <div>
            {t("Personal workspace", "个人工作区")}
            <small>
              {config?.auth_mode !== "local"
                ? t("Private workspace", "独立工作区")
                : t("Local workspace", "本地工作区")}
            </small>
          </div>
          <ChevronDown size={14} />
        </div>
        <div className="nav-label">{t("WORKSPACE", "工作台")}</div>
        <nav aria-label="Main navigation">
          {main.map(([href, en, zh, Icon]) => (
            <Nav
              key={href}
              href={href}
              className={`nav-item ${path === href ? "active" : ""}`}
            >
              <Icon size={18} />
              <span>{t(en, zh)}</span>
              {href === "/email" && <span className="tiny-new">AI</span>}
            </Nav>
          ))}
        </nav>
        <div className="nav-label">{t("DOMAINS", "业务领域")}</div>
        <nav>
          {[
            ["/finance", "Finance", "金融", Landmark],
            ["/academic", "Academic", "学术", GraduationCap],
          ].map(([href, en, zh, Icon]) => {
            const I = Icon as typeof Landmark;
            return (
              <Nav
                key={String(href)}
                href={String(href)}
                className={`nav-item ${path === href ? "active" : ""}`}
              >
                <I size={18} />
                <span>{t(String(en), String(zh))}</span>
                {href === "/academic" && <span className="soon-dot" />}
              </Nav>
            );
          })}
        </nav>
        <div className="nav-label">{t("OUTREACH", "外联管理")}</div>
        <nav>
          {later.map(([href, en, zh, Icon]) => (
            <Nav
              key={href}
              href={href}
              className={`nav-item ${["/campaigns", "/analytics"].includes(href) ? "future" : ""} ${path === href ? "active" : ""}`}
            >
              <Icon size={18} />
              <span>{t(en, zh)}</span>
            </Nav>
          ))}
        </nav>
        <div className="sidebar-bottom">
          {config?.is_admin && (
            <Nav
              href="/admin"
              className={`nav-item ${path === "/admin" ? "active" : ""}`}
            >
              <ShieldCheck size={18} />
              {t("Administration", "管理员后台")}
            </Nav>
          )}
          <Nav
            href="/settings"
            className={`nav-item ${path.startsWith("/settings") ? "active" : ""}`}
          >
            <Settings2 size={18} />
            {t("Settings & integrations", "设置与集成")}
          </Nav>
          <div className="account">
            <span className="workspace-monogram">P</span>
            <div>{t("Personal account", "个人账户")}</div>
            {config && config.auth_mode !== "local" && (
              <button
                onClick={async () => {
                  try {
                    if (guard.current) await guard.current();
                    await post("/auth/logout");
                    sessionStorage.clear();
                    window.location.assign("/");
                  } catch (e) {
                    notify(
                      e instanceof Error ? e.message : "Unable to sign out.",
                    );
                  }
                }}
              >
                {t("Sign out", "退出")}
              </button>
            )}
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <PanelLeftClose size={17} />
            <span>/</span>
            {title}
          </div>
          <div className="top-actions">
            <span className="domain-label">
              <Landmark size={14} />
              {path === "/academic" ? "Academic" : "Finance"}
            </span>
            <span className="top-divider" />
            <button
              className="theme-toggle"
              type="button"
              aria-label={t(
                theme === "dark" ? "Use light theme" : "Use dark theme",
                theme === "dark" ? "切换浅色主题" : "切换深色主题",
              )}
              title={t(
                theme === "dark" ? "Light theme" : "Dark theme",
                theme === "dark" ? "浅色主题" : "深色主题",
              )}
              onClick={toggleTheme}
            >
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <Globe2 size={15} />
            <select
              aria-label="Interface language"
              value={locale}
              onChange={(e) => setLocale(e.target.value)}
            >
              <option value="en">English</option>
              <option value="zh">简体中文</option>
            </select>
            <span className="top-avatar">P</span>
          </div>
        </header>
        {config && (
          <div
            className={`mode-strip ${config.people_mode === "mock" || config.ai_mode === "mock" ? "mock" : "live"}`}
          >
            <span className="mode-dot" />
            <b>
              {config.people_mode === "mock"
                ? t("Mock workspace", "模拟工作区")
                : t("Live people data", "真实人员数据")}
            </b>
            <span>
              {config.people_mode === "mock"
                ? t("Fictional demo contacts.", "联系人为虚构演示数据。")
                : t(
                    "Google discovery · public profiles · email enrichment.",
                    "Google 找人 · 公开档案补全 · 邮箱获取。",
                  )}{" "}
              {t("AI:", "AI：")}{" "}
              {config.ai_mode === "mock"
                ? t("Mock · rule-based", "模拟 · 规则生成")
                : t("Live", "真实 API")}{" "}
              · {t("Public sources:", "公开资料：")}
              {config.public_search_mode === "mock" ? "Mock" : "Live"}
            </span>
            <Nav href="/settings/integrations">
              {t("View configuration", "查看配置")}
              <ArrowUpRight size={13} />
            </Nav>
          </div>
        )}
        <main>
          {error ? (
            <div className="error-panel" role="alert">
              <h3>{t("Cannot load your workspace", "无法加载工作区")}</h3>
              <p>{error}</p>
              <button className="button" onClick={() => void refresh()}>
                {t("Retry", "重试")}
              </button>
            </div>
          ) : loading ? (
            <div className="boot">
              {t("Loading your workspace…", "正在加载工作区…")}
            </div>
          ) : path === "/" ? (
            <Dashboard />
          ) : path === "/finance" ? (
            <FinanceFlow />
          ) : path === "/personas" ? (
            <Personas />
          ) : path === "/people" ? (
            <PeopleSearch />
          ) : path === "/contacts" ? (
            <Contacts />
          ) : path === "/email" ? (
            <EmailStudio />
          ) : path === "/sequences" ? (
            <Sequences />
          ) : path === "/mailboxes" ? (
            <Mailboxes />
          ) : path === "/inbox" ? (
            <MailInbox />
          ) : path === "/outbox" ? (
            <Outbox />
          ) : path === "/followups" ? (
            <Followups />
          ) : path === "/admin" ? (
            <Admin />
          ) : (
            <ComingSoon path={path} title={title} />
          )}
        </main>
      </div>
    </div>
  );
}
export default function Workspace() {
  return (
    <AuthGate>
      <AppProvider>
        <Shell />
      </AppProvider>
    </AuthGate>
  );
}
