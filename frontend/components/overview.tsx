"use client";
import { useEffect, useState } from "react";
import {
  ArrowUpRight,
  ArrowRight,
  ArrowUp,
  Search,
  Users,
  FileText,
  Sparkles,
  ContactRound,
  Landmark,
  GraduationCap,
  Check,
  ShieldCheck,
  Mail,
  Plus,
  BookOpen,
} from "lucide-react";
import { useApp } from "@/lib/context";
import { api, post, errorText } from "@/lib/api";
import { Heading, Nav, Avatar, Badge, DateLabel, Empty } from "./ui";
// Registration only collects an email, so fall back through the most
// human-meaningful name we actually hold before giving up on one.
function useGreetingName() {
  const { personas } = useApp();
  const [email, setEmail] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api<{ email: string | null }>("/auth/session")
      .then((s) => live && setEmail(s.email))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);
  const persona = personas[0]?.data.name?.trim();
  if (persona) return persona.split(/\s+/)[0];
  if (email) return email.split("@")[0];
  return "";
}
type SearchIntent = {
  title: string;
  company: string;
  location: string;
  keywords: string;
  sector: string;
  per_page: number;
};
function Composer() {
  const { t, locale, go, notify } = useApp();
  const name = useGreetingName();
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    const q = prompt.trim();
    if (!q || busy) return;
    setBusy(true);
    try {
      const intent = await post<SearchIntent>("/finance/search/intent", {
        prompt: q,
        language: locale === "zh" ? "zh" : "en",
      });
      const params = new URLSearchParams();
      for (const key of [
        "title",
        "company",
        "location",
        "keywords",
        "sector",
      ] as const)
        if (intent[key]) params.set(key, intent[key]);
      params.set("per_page", String(intent.per_page));
      params.set("run", "1");
      await go("/people?" + params);
    } catch (e) {
      notify(errorText(e));
      setBusy(false);
    }
  };
  return (
    <section className="hero">
      <h1 className="hero-greeting">
        <Sparkles size={27} aria-hidden="true" />
        {name ? t("Hi " + name, "你好，" + name) : t("Hi there", "你好")}
      </h1>
      <p className="hero-sub">
        {t(
          "Describe the people you want to reach and start from there.",
          "描述你想联系的人，从这里开始。",
        )}
      </p>
      <div className="hero-composer">
        <textarea
          rows={4}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void submit();
            }
          }}
          placeholder={t(
            "e.g. Investment banking associates in New York who moved over from consulting",
            "例如：从咨询转行、目前在纽约做投行的分析师",
          )}
          aria-label={t("Describe who you want to reach", "描述你想联系的人")}
        />
        <div className="hero-composer-bar">
          <span className="hero-hint">
            {busy
              ? t("Reading your request…", "正在理解你的需求…")
              : t(
                  "Enter to search · Shift + Enter for a new line",
                  "回车搜索 · Shift + 回车换行",
                )}
          </span>
          <button
            type="button"
            className="hero-send"
            onClick={() => void submit()}
            disabled={!prompt.trim() || busy}
            aria-label={t("Search people", "搜索人员")}
          >
            <ArrowUp size={18} />
          </button>
        </div>
      </div>
      <div className="hero-chips">
        {[
          [Search, "Find people", "搜索人员", "/people"],
          [Mail, "Write an email", "撰写邮件", "/email"],
          [ContactRound, "Refine persona", "完善画像", "/personas"],
          [BookOpen, "Browse templates", "浏览模板", "/templates"],
        ].map(([Icon, en, zh, href]) => {
          const I = Icon as typeof Users;
          return (
            <Nav key={String(en)} href={String(href)} className="hero-chip">
              <I size={15} />
              {t(String(en), String(zh))}
            </Nav>
          );
        })}
      </div>
    </section>
  );
}
export function Dashboard() {
  const { t, personas, contacts, drafts } = useApp();
  return (
    <>
      <Composer />
      <div className="section-divider">
        <h2>{t("Overview", "总览")}</h2>
        <Nav href="/people" className="button primary">
          <Search size={16} />
          {t("Find people", "搜索人员")}
          <ArrowUpRight size={16} />
        </Nav>
      </div>
      <div className="stats-grid">
        {[
          [
            ContactRound,
            t("Career personas", "职业画像"),
            personas.length,
            "/personas",
          ],
          [
            Users,
            t("Saved contacts", "已保存联系人"),
            contacts.length,
            "/contacts",
          ],
          [FileText, t("Email drafts", "邮件草稿"), drafts.length, "/email"],
        ].map(([Icon, label, value, href]) => {
          const I = Icon as typeof Users;
          return (
            <Nav key={String(label)} href={String(href)} className="stat-card">
              <div className="stat-label">
                <span>{String(label)}</span>
                <I size={19} />
              </div>
              <div className="stat-value">
                {String(value).padStart(2, "0")}
                <ArrowUpRight size={20} />
              </div>
            </Nav>
          );
        })}
      </div>
      <div className="dashboard-grid">
        <section className="panel">
          <div className="section-head">
            <h2>{t("Active persona", "当前画像")}</h2>
            <Nav href="/personas">
              {t("Manage personas", "管理画像")}
              <ArrowUpRight size={15} />
            </Nav>
          </div>
          {personas.length ? (
            <div className="persona-feature">
              <div className="row">
                <Avatar
                  name={personas[0].data.name || personas[0].label}
                  large
                />
                <div>
                  <h3>{personas[0].data.name || personas[0].label}</h3>
                  <p>{personas[0].label}</p>
                </div>
                <Badge tone="green">{t("Saved persona", "已保存画像")}</Badge>
              </div>
              <div className="focus-data">
                <div>
                  <span>{t("FOCUS AREA", "关注领域")}</span>
                  <strong>
                    {personas[0].data.sectors || t("Not specified", "未填写")}
                  </strong>
                </div>
                <div>
                  <span>{t("LOOKING TOWARD", "目标地区")}</span>
                  <strong>
                    {personas[0].data.target_regions ||
                      t("Not specified", "未填写")}
                  </strong>
                </div>
              </div>
              <div className="quote-line">
                <Sparkles size={16} />
                <p>
                  {personas[0].data.career_goals ||
                    t(
                      "Add your career goals to get more relevant recommendations.",
                      "补充职业目标，获取更相关的推荐。",
                    )}
                </p>
              </div>
              <Nav href="/personas" className="text-link">
                {t("Refine your story", "完善职业背景")}
                <ArrowRight size={15} />
              </Nav>
            </div>
          ) : (
            <Empty
              title={t("No persona yet", "尚未创建画像")}
              detail={t(
                "Upload a resume or start with a few details. You can search without one.",
                "上传简历或手动填写。没有画像也可以搜索。",
              )}
            >
              <Nav href="/personas" className="button">
                <Plus size={16} />
                {t("Create a persona", "创建画像")}
              </Nav>
            </Empty>
          )}
        </section>
        <section className="explore-card">
          <Landmark className="domain-card-icon" size={30} aria-hidden="true" />
          <h2>{t("Finance", "金融")}</h2>
          <div className="sector-chips">
            <span>Investment Banking</span>
            <span>Private Equity</span>
            <span>Asset Management</span>
          </div>
          <Nav href="/finance" className="button light">
            {t("Explore Finance", "探索金融领域")}
            <ArrowUpRight size={16} />
          </Nav>
        </section>
      </div>
      <div className="dashboard-grid bottom">
        <section className="panel">
          <div className="section-head">
            <h2>{t("Recent drafts", "近期草稿")}</h2>
            <Nav href="/email">
              {t("All drafts", "全部草稿")}
              <ArrowRight size={15} />
            </Nav>
          </div>
          {drafts.length ? (
            drafts.slice(0, 4).map((d) => (
              <Nav
                className="draft-row"
                key={d.id}
                href={"/email?draft=" + d.id}
              >
                <span className="draft-icon">
                  <FileText size={18} />
                </span>
                <div>
                  <strong>
                    {d.subject || t("Untitled draft", "未命名草稿")}
                  </strong>
                  <small>
                    {contacts.find((c) => c.id === d.contact_id)?.name ||
                      t("No recipient yet", "尚未选择收件人")}{" "}
                    · <DateLabel value={d.updated_at} />
                  </small>
                </div>
                <Badge>
                  {d.status === "ready"
                    ? t("Reviewed", "已审核")
                    : t("Draft", "草稿")}
                </Badge>
                <ArrowUpRight size={16} />
              </Nav>
            ))
          ) : (
            <Empty
              title={t("No drafts yet", "尚无草稿")}
              detail={t(
                "Draft an introduction whenever you are ready.",
                "随时开始撰写您的介绍邮件。",
              )}
            >
              <Nav href="/email" className="text-link">
                {t("Open Email Studio", "打开邮件工作室")}
                <ArrowRight size={15} />
              </Nav>
            </Empty>
          )}
        </section>
        <section className="panel">
          <div className="section-head">
            <h2>{t("Saved contacts", "已保存联系人")}</h2>
            <Nav href="/contacts">
              {t("View contacts", "查看联系人")}
              <ArrowRight size={15} />
            </Nav>
          </div>
          {contacts.length ? (
            contacts.slice(0, 3).map((c) => (
              <Nav
                key={c.id}
                href={"/contacts?contact=" + c.id}
                className="network-row"
              >
                <Avatar name={c.name} />
                <div>
                  <strong>{c.name}</strong>
                  <small>
                    {c.title} · {c.company}
                  </small>
                </div>
                <ArrowUpRight size={16} />
              </Nav>
            ))
          ) : (
            <Empty
              title={t("No saved contacts", "尚无已保存联系人")}
              detail={t(
                "Save people from search or add someone you already know.",
                "保存搜索结果，或手动添加已认识的人。",
              )}
            />
          )}
          <div className="panel-note">
            <ShieldCheck size={15} />
            {t(
              "Sources stay with every saved contact.",
              "每位已保存联系人都保留来源信息。",
            )}
          </div>
        </section>
      </div>
    </>
  );
}
export function Finance() {
  const { t } = useApp();
  return (
    <>
      <Heading title={t("Finance", "金融")} />
      <div className="finance-banner">
        <Landmark className="domain-banner-icon" size={34} aria-hidden="true" />
        <div>
          <h2>{t("Finance coverage", "金融领域")}</h2>
          <p>
            {t(
              "Investment Banking · Private Equity · Asset Management · Venture Capital · Risk Management",
              "投资银行 · 私募股权 · 资产管理 · 风险投资 · 风险管理",
            )}
          </p>
        </div>
      </div>
      <div className="module-grid">
        {[
          [
            "/personas",
            ContactRound,
            "01",
            "Personas",
            "职业画像",
            "Create and refine your professional background.",
            "建立并完善职业画像。",
          ],
          [
            "/people",
            Search,
            "02",
            "People Search",
            "人员搜索",
            "Explore professionals and evidence-based recommendations.",
            "搜索金融从业者，查看有资料依据的推荐。",
          ],
          [
            "/email",
            Mail,
            "03",
            "Email Studio",
            "邮件工作室",
            "Write, refine and save a personal introduction.",
            "生成、编辑并保存个性化介绍邮件。",
          ],
        ].map(([href, Icon, num, en, zh, desc, zdesc]) => {
          const I = Icon as typeof Users;
          return (
            <Nav href={String(href)} key={String(num)} className="module-card">
              <div className="module-top">
                <I size={24} />
                <span>{String(num)}</span>
              </div>
              <h2>{t(String(en), String(zh))}</h2>
              <p>{t(String(desc), String(zdesc))}</p>
              <ArrowUpRight size={23} />
            </Nav>
          );
        })}
      </div>
      <div className="notice">
        {t(
          "Start anywhere. A resume is helpful for personalization, but never required to search or write.",
          "可从任意模块开始。简历有助于个性化，但搜索和手动写信不需要先上传简历。",
        )}
      </div>
    </>
  );
}
const purposes: Record<string, [string, string]> = {
  academic: [
    "A future research networking workspace: build an academic profile, discover researchers from cited sources, and draft a tailored introduction. Researcher search is not available in this phase.",
    "未来的科研人脉工作区：建立学术画像、依据可引用来源寻找研究人员并撰写联系邮件。本阶段尚不支持导师搜索。",
  ],
  templates: [
    "A future library for creating, organizing and reusing writing templates. Three Finance writing starting points are already available in Email Studio.",
    "未来支持创建、整理和复用邮件模板。邮件工作室已提供三种金融写作起点。",
  ],
  campaigns: [
    "Organize outreach and follow-ups in a later phase, reusing your existing contacts and drafts.",
    "后续将支持管理外联和跟进，复用现有联系人与草稿。",
  ],
  analytics: [
    "Future reporting on outreach and engagement, once real sending and reply data are available.",
    "待接入真实发送与回复数据后，提供外联和互动分析。",
  ],
  settings: [
    "Workspace administration and account settings will be added in a later phase. This MVP uses one local personal workspace.",
    "后续将增加工作区管理和账户设置。本阶段使用固定本地个人工作区。",
  ],
};
export function ComingSoon({ path, title }: { path: string; title: string }) {
  const { t, config } = useApp();
  const key = path.split("/")[1],
    content = purposes[key];
  if (path === "/settings/integrations")
    return (
      <>
        <Heading
          title={t("Integrations", "集成")}
          detail={t(
            "Service availability for this workspace. Your administrator manages provider credentials.",
            "工作区服务配置。服务商密钥由管理员管理。",
          )}
        />
        <div className="panel integrations">
          {[
            [
              t("Apollo email matching", "Apollo 邮箱匹配"),
              config?.people_mode,
              config?.providers.apollo,
            ],
            [
              t("SerpAPI people search", "SerpAPI 人员搜索"),
              config?.people_mode,
              config?.providers.serpapi,
            ],
            [
              t("Public sources", "补充公开来源"),
              config?.public_search_mode,
              config?.providers.serpapi,
            ],
            [
              t(
                "Apify professional profiles & work email",
                "Apify 职业档案与工作邮箱",
              ),
              config?.people_mode,
              config?.providers.apify,
            ],
            ["AI provider", config?.ai_mode, config?.providers.ai],
          ].map(([name, mode, key]) => (
            <div className="integration-row" key={String(name)}>
              <span className="integration-icon">
                <LayersIcon />
              </span>
              <div>
                <h3>{String(name)}</h3>
                <p>
                  {mode === "mock"
                    ? t(
                        "Explicit Mock mode. No external requests.",
                        "明确启用 Mock 模式，不调用外部服务。",
                      )
                    : key
                      ? t(
                          "Configured. Access, credits and results are checked when you run a task.",
                          "已配置。执行任务时检查权限、额度和返回结果。",
                        )
                      : t(
                          "Live mode selected. API key is missing.",
                          "已选择真实模式，但缺少 API 密钥。",
                        )}
                </p>
              </div>
              <Badge tone={mode === "mock" ? "amber" : "green"}>
                {String(mode).toUpperCase()}
              </Badge>
            </div>
          ))}
          <div className="integration-row">
            <Mail />
            <div>
              <h3>Gmail</h3>
              <p>
                {t(
                  "Connect a Gmail mailbox to send email and sync saved platform contacts' replies. Google sign-in is separate.",
                  "连接 Gmail 以发送邮件并同步已保存平台联系人的回复。Google 登录与邮箱授权相互独立。",
                )}
              </p>
            </div>
            <Nav href="/mailboxes">{t("Manage Gmail", "管理 Gmail")}</Nav>
          </div>
        </div>
      </>
    );
  return (
    <>
      <Heading title={title} />
      <section className="coming-soon">
        <div className="coming-icon">
          {key === "academic" ? (
            <GraduationCap size={38} />
          ) : (
            <BookOpen size={38} />
          )}
        </div>
        <Badge tone="amber">Coming Soon</Badge>
        <h2>
          {content
            ? t("Room for what comes next.", "为下一阶段留出空间。")
            : t("This page does not exist.", "此页面不存在。")}
        </h2>
        <p>
          {content
            ? t(...content)
            : t(
                "Use the sidebar to return to your workspace.",
                "请使用侧栏返回工作区。",
              )}
        </p>
        {key === "academic" && (
          <div className="future-flow">
            <span>{t("Academic profile", "学术画像")}</span>
            <ArrowRight size={15} />
            <span>
              {t("Cited researcher discovery", "有来源的研究人员搜索")}
            </span>
            <ArrowRight size={15} />
            <span>{t("Personal introduction", "个性化介绍")}</span>
          </div>
        )}
        {key === "settings" && (
          <Nav href="/settings/integrations" className="button">
            {t("View current integrations", "查看当前集成配置")}
            <ArrowRight size={15} />
          </Nav>
        )}
      </section>
    </>
  );
}
function LayersIcon() {
  return <Landmark size={22} />;
}
