"use client";

import { useEffect, useState } from "react";
import {
  ArrowLeft,
  Download,
  RefreshCw,
  Search,
  ShieldCheck,
  Users,
  FileText,
  ContactRound,
  Mail,
} from "lucide-react";
import { api, errorText } from "@/lib/api";
import { useApp } from "@/lib/context";
import { Heading, Badge } from "./ui";
import AdminGoogleLink from "./admin-google-link";

type Account = {
  id: string;
  email: string;
  is_admin: boolean;
  created_at: string;
  last_login_at: string | null;
  counts: Record<string, number>;
};
type Page<T> = { items: T[]; total: number; offset: number; limit: number };
type RecordData = { id: string; [key: string]: unknown };
type Overview = {
  accounts: number;
  administrators: number;
  saved_contacts: number;
  drafts: number;
  documents: number;
  stored_bytes: number;
};
const categories = [
  ["personas", "Personas", "职业画像"],
  ["contacts", "Contacts", "联系人"],
  ["drafts", "Email drafts", "邮件草稿"],
  ["documents", "Files", "上传文件"],
  ["people_jobs", "People searches & tasks", "查人与搜索任务"],
  ["writing_jobs", "Writing tasks", "AI 写作任务"],
  ["persona_revisions", "Persona history", "画像历史版本"],
  ["contact_profiles", "Contact profiles", "联系人详细资料"],
  ["sources", "Sources", "来源资料"],
  ["assessments", "Match assessments", "匹配分析"],
] as const;
const labels: Record<string, string> = {
  label: "名称",
  data: "保存资料",
  name: "姓名",
  education: "教育经历",
  experience: "工作经历",
  skills: "技能",
  sectors: "领域",
  career_goals: "职业目标",
  target_regions: "目标地区",
  target_roles: "目标岗位",
  contact_purpose: "联系目的",
  version: "版本",
  created_at: "创建时间",
  updated_at: "更新时间",
  title: "职位 / 标题",
  company: "公司",
  location: "地区",
  school: "学校",
  profile_url: "个人主页",
  email: "邮箱",
  email_status: "邮箱状态",
  tags: "标签",
  notes: "备注",
  saved: "已保存联系人",
  provider: "提供商",
  provider_id: "来源标识",
  domain: "领域",
  subject: "主题",
  body_html: "邮件正文（HTML）",
  language: "语言",
  purpose: "目的",
  starting_point: "写作场景",
  tone: "语气",
  status: "状态",
  revision: "修订版本",
  writing_mode: "写作方式",
  length: "长度",
  cta: "行动请求",
  custom_instructions: "自定义要求",
  evidence_ids: "引用来源",
  model: "模型",
  generation_provider: "生成来源",
  original_name: "原始文件名",
  error: "错误信息",
  extracted_text: "提取的原文",
  parsed_data: "文件解析结果",
  parse_mode: "解析方式",
  parse_provider: "解析提供商",
  parse_model: "解析模型",
  parse_started_at: "解析开始",
  parse_completed_at: "解析完成",
  content_hash: "文件校验值",
  parse_prompt_version: "解析提示版本",
  byte_size: "文件字节数",
  file_available: "原件可下载",
  kind: "任务类型",
  input: "用户提交内容",
  result: "结果",
  upstream: "上游状态",
  attempts: "尝试次数",
  retryable: "可以重试",
  next_poll_at: "下次检查",
  action: "操作",
  mode: "模式",
  prompt_version: "提示版本",
  snapshot: "生成时的完整资料",
  started_at: "开始时间",
  completed_at: "完成时间",
  reason: "匹配理由",
  url: "来源链接",
  snippet: "来源内容",
  retrieved_at: "获取时间",
  source_ids: "来源编号",
  persona_version: "画像版本",
  contact_fingerprint: "联系人版本校验",
  contact_id: "关联联系人",
  persona_id: "关联画像",
  persona_revision_id: "画像历史版本",
  draft_id: "关联草稿",
  draft_revision: "草稿版本",
};
function date(value: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}
function size(bytes: number) {
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function Values({ value, zh }: { value: unknown; zh: boolean }) {
  if (value === null || value === undefined || value === "")
    return <span className="admin-muted">—</span>;
  if (typeof value === "boolean")
    return <span>{value ? (zh ? "是" : "Yes") : zh ? "否" : "No"}</span>;
  if (Array.isArray(value))
    return value.length ? (
      <ol className="admin-values-list">
        {value.map((item, index) => (
          <li key={index}>
            <Values value={item} zh={zh} />
          </li>
        ))}
      </ol>
    ) : (
      <span>—</span>
    );
  if (typeof value === "object")
    return (
      <dl className="admin-fields">
        {Object.entries(value)
          .filter(([key]) => key !== "download_url" && key !== "id")
          .map(([key, item]) => (
            <div key={key}>
              <dt>{zh ? labels[key] || key : key.replaceAll("_", " ")}</dt>
              <dd>
                <Values value={item} zh={zh} />
              </dd>
            </div>
          ))}
      </dl>
    );
  // Render untrusted saved content as text, including HTML drafts and provider output.
  return <span className="admin-value">{String(value)}</span>;
}

function Pager({
  offset,
  total,
  onChange,
  t,
}: {
  offset: number;
  total: number;
  onChange: (v: number) => void;
  t: (en: string, zh: string) => string;
}) {
  return (
    <div className="admin-pagination">
      <span>
        {total
          ? `${offset + 1}–${Math.min(offset + 25, total)} / ${total}`
          : t("No records", "暂无记录")}
      </span>
      <div>
        <button
          className="button ghost"
          disabled={!offset}
          onClick={() => onChange(offset - 25)}
        >
          {t("Previous", "上一页")}
        </button>
        <button
          className="button ghost"
          disabled={offset + 25 >= total}
          onClick={() => onChange(offset + 25)}
        >
          {t("Next", "下一页")}
        </button>
      </div>
    </div>
  );
}

export default function Admin() {
  const { t, locale, config } = useApp();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [accounts, setAccounts] = useState<Page<Account> | null>(null);
  const [selected, setSelected] = useState<Account | null>(null);
  const [section, setSection] = useState<string>("personas");
  const [records, setRecords] = useState<Page<RecordData> | null>(null);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [dataOffset, setDataOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const zh = locale === "zh";
  useEffect(() => {
    if (!config?.is_admin) return;
    let active = true;
    setAccounts(null);
    setError("");
    Promise.all([
      api<Overview>("/admin/overview"),
      api<Page<Account>>(
        `/admin/users?q=${encodeURIComponent(search)}&offset=${offset}`,
      ),
    ])
      .then(([summary, users]) => {
        if (active) {
          setOverview(summary);
          setAccounts(users);
        }
      })
      .catch((e) => {
        if (active) setError(errorText(e));
      });
    return () => {
      active = false;
    };
  }, [config?.is_admin, search, offset, revision]);
  useEffect(() => {
    if (!selected || !config?.is_admin) return;
    let active = true;
    setRecords(null);
    setError("");
    Promise.all([
      api<Page<RecordData>>(
        `/admin/users/${selected.id}/data/${section}?offset=${dataOffset}`,
      ),
      api<Account>(`/admin/users/${selected.id}`),
    ])
      .then(([data, user]) => {
        if (active) {
          setRecords(data);
          setSelected(user);
        }
      })
      .catch((e) => {
        if (active) setError(errorText(e));
      });
    return () => {
      active = false;
    };
  }, [selected?.id, config?.is_admin, section, dataOffset, revision]);
  if (!config?.is_admin)
    return (
      <div className="error-panel">
        <ShieldCheck />
        <h2>{t("Administrator access required", "仅管理员可访问")}</h2>
        <p>
          {t(
            "Sign in with an administrator account to view this page.",
            "请使用管理员账号登录后查看。",
          )}
        </p>
      </div>
    );
  return (
    <div className="admin-page">
      <Heading
        eyebrow="CONNACT.AI"
        title={t("Administration", "管理员后台")}
        detail={t(
          "Accounts, saved information and original uploads.",
          "查看所有账号、保存的信息和上传原件。",
        )}
      >
        <button className="button" onClick={() => setRevision((v) => v + 1)}>
          <RefreshCw size={16} />
          {t("Refresh", "刷新")}
        </button>
      </Heading>
      <AdminGoogleLink revision={revision} />
      {overview && (
        <div className="admin-stats">
          {[
            [t("Accounts", "账号总数"), overview.accounts, Users],
            [
              t("Saved contacts", "保存联系人"),
              overview.saved_contacts,
              ContactRound,
            ],
            [t("Email drafts", "邮件草稿"), overview.drafts, Mail],
            [t("Uploaded files", "上传文件"), overview.documents, FileText],
          ].map(([label, count, Icon]) => {
            const I = Icon as typeof Users;
            return (
              <div key={String(label)}>
                <I size={19} />
                <span>{String(label)}</span>
                <strong>{String(count)}</strong>
              </div>
            );
          })}
        </div>
      )}
      {overview && (
        <p className="admin-muted">
          {t("Stored original files", "已保存原件大小")}:{" "}
          {size(overview.stored_bytes)} · {overview.administrators}{" "}
          {t("administrator(s)", "个管理员")}
        </p>
      )}
      {error && (
        <div className="error-panel" role="alert">
          {error}
          <button className="button" onClick={() => setRevision((v) => v + 1)}>
            {t("Retry", "重试")}
          </button>
        </div>
      )}
      {selected ? (
        <section className="admin-card">
          <div className="admin-account-heading">
            <button
              className="button ghost"
              onClick={() => {
                setSelected(null);
                setRecords(null);
                setError("");
              }}
            >
              <ArrowLeft size={16} />
              {t("All accounts", "全部账号")}
            </button>
            <div>
              <h2>{selected.email}</h2>
              <p>
                {t("Joined", "注册时间")}: {date(selected.created_at)} ·{" "}
                {t("Last login", "最后登录")}: {date(selected.last_login_at)}
              </p>
            </div>
            <Badge tone={selected.is_admin ? "blue" : "gray"}>
              {selected.is_admin
                ? t("Administrator", "管理员")
                : t("Member", "普通用户")}
            </Badge>
          </div>
          <nav
            className="admin-tabs"
            aria-label={t("User data categories", "用户数据分类")}
          >
            {categories.map(([key, en, cn]) => (
              <button
                key={key}
                className={section === key ? "active" : ""}
                aria-pressed={section === key}
                onClick={() => {
                  setSection(key);
                  setDataOffset(0);
                }}
              >
                {t(en, cn)} <span>{selected.counts[key] || 0}</span>
              </button>
            ))}
          </nav>
          {!records && !error ? (
            <div className="admin-empty">
              {t("Loading account data…", "正在加载账号数据…")}
            </div>
          ) : (
            records && (
              <>
                {!records.items.length && (
                  <div className="admin-empty">
                    <FileText size={28} />
                    <p>
                      {t(
                        "This account has no saved records in this category.",
                        "此账号尚未保存这类内容。",
                      )}
                    </p>
                  </div>
                )}
                <div className="admin-records">
                  {records.items.map((record) => (
                    <details className="admin-record" key={record.id}>
                      <summary>
                        <span>
                          {String(
                            record.original_name ||
                              record.subject ||
                              record.label ||
                              record.name ||
                              record.kind ||
                              record.action ||
                              record.title ||
                              t("Saved record", "已保存记录"),
                          )}
                          <small>{date(String(record.created_at))}</small>
                        </span>
                        {record.status ? (
                          <Badge>{String(record.status)}</Badge>
                        ) : (
                          <span>{t("View details", "查看详情")}</span>
                        )}
                      </summary>
                      {section === "documents" && (
                        <div className="admin-download">
                          {record.download_url ? (
                            <a
                              className="button"
                              href={String(record.download_url)}
                            >
                              <Download size={16} />
                              {t("Download original", "下载原文件")}
                            </a>
                          ) : (
                            <p>
                              {t(
                                "Original file is unavailable; saved text and parsing results remain below.",
                                "原文件已不可用；已保存的原文和解析结果仍可在下方查看。",
                              )}
                            </p>
                          )}
                        </div>
                      )}
                      <Values value={record} zh={zh} />
                    </details>
                  ))}
                </div>
                <Pager
                  offset={dataOffset}
                  total={records.total}
                  onChange={setDataOffset}
                  t={t}
                />
              </>
            )
          )}
        </section>
      ) : (
        <section className="admin-card">
          <div className="admin-list-heading">
            <h2>{t("All accounts", "全部账号")}</h2>
            <form
              className="admin-search"
              onSubmit={(e) => {
                e.preventDefault();
                setSearch(query);
                setOffset(0);
              }}
            >
              <Search size={17} />
              <input
                aria-label={t("Search accounts", "搜索账号")}
                placeholder={t("Search email or account", "搜索邮箱或账号")}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <button className="button" type="submit">
                {t("Search", "搜索")}
              </button>
            </form>
          </div>
          {!accounts && !error ? (
            <div className="admin-empty">
              {t("Loading accounts…", "正在加载账号…")}
            </div>
          ) : (
            accounts && (
              <>
                <div className="admin-table-wrap">
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th>{t("Account", "账号")}</th>
                        <th>{t("Joined / last login", "注册 / 最后登录")}</th>
                        <th>{t("Saved content", "保存内容")}</th>
                        <th>{t("Details", "详情")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {accounts.items.map((user) => (
                        <tr key={user.id}>
                          <td>
                            <strong>{user.email}</strong>
                            <small>
                              {user.is_admin
                                ? t("Administrator", "管理员")
                                : t("Member", "普通用户")}
                            </small>
                          </td>
                          <td>
                            {date(user.created_at)}
                            <small>{date(user.last_login_at)}</small>
                          </td>
                          <td>
                            {user.counts.personas || 0} {t("personas", "画像")}{" "}
                            · {user.counts.contacts || 0}{" "}
                            {t("contacts", "联系人")}
                            <small>
                              {user.counts.drafts || 0} {t("drafts", "草稿")} ·{" "}
                              {user.counts.documents || 0} {t("files", "文件")}
                            </small>
                          </td>
                          <td>
                            <button
                              className="button"
                              aria-label={`${t("View account", "查看账号")} ${user.email}`}
                              onClick={() => {
                                setSelected(user);
                                setSection("personas");
                                setDataOffset(0);
                              }}
                            >
                              {t("View account", "查看账号")}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!accounts.items.length && (
                  <div className="admin-empty">
                    {t("No matching accounts.", "没有匹配的账号。")}
                  </div>
                )}
                <Pager
                  offset={offset}
                  total={accounts.total}
                  onChange={setOffset}
                  t={t}
                />
              </>
            )
          )}
        </section>
      )}
    </div>
  );
}
