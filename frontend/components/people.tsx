"use client";
import { useEffect, useState, useRef } from "react";
import { useSearchParams } from "next/navigation";
import {
  Search,
  Plus,
  MapPin,
  Sparkles,
  Bookmark,
  Check,
  Mail,
  ArrowRight,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  SlidersHorizontal,
  Link2,
  Save,
  PencilLine,
} from "lucide-react";
import { useApp } from "@/lib/context";
import { api, post, put, errorText } from "@/lib/api";
import type { Contact, Assessment, Draft, PeopleJob } from "@/lib/types";
import {
  Heading,
  Field,
  Avatar,
  Badge,
  Busy,
  Drawer,
  External,
  Empty,
  DateLabel,
  Nav,
} from "./ui";
const sectors = [
  "Investment Banking",
  "Private Equity",
  "Asset Management",
  "Venture Capital",
  "Risk Management",
];
type PeopleFilters = {
  title: string;
  company: string;
  location: string;
  keywords: string;
  sector: string;
};
const peoplePageSize = 10;
function searchHasMore(result: PeopleJob["result"], size = peoplePageSize) {
  return (
    result.has_more ??
    (result.total_is_estimate
      ? (result.items?.length || 0) === size
      : (result.page || 1) * size < (result.total || 0))
  );
}
export function PeopleSearch({
  selectedPersonaId,
  onSelectContact,
  selectedContactId,
  initialFilters,
  initialJobId,
  onJobChange,
}: {
  selectedPersonaId?: string;
  onSelectContact?: (contact: Contact) => void;
  selectedContactId?: string;
  initialFilters?: Partial<PeopleFilters>;
  initialJobId?: string;
  onJobChange?: (id: string) => void;
} = {}) {
  const { t, locale, personas, refresh, notify, config } = useApp();
  // Filters can arrive from the dashboard composer, already parsed into fields.
  const entry = useSearchParams();
  const entryFilters = {
    title: entry.get("title") || "",
    company: entry.get("company") || "",
    location: entry.get("location") || "",
    keywords: entry.get("keywords") || "",
    sector: (entry.get("sector") || "") as PeopleFilters["sector"],
  };
  const pageSize = Math.min(
    Math.max(Number(entry.get("per_page")) || peoplePageSize, 1),
    peoplePageSize,
  );
  const autoRun = entry.get("run") === "1";
  const [filters, setFilters] = useState<PeopleFilters>({
      ...entryFilters,
      ...initialFilters,
    }),
    [localPersonaId, setPersonaId] = useState(personas[0]?.id || ""),
    [results, setResults] = useState<Contact[]>([]),
    [total, setTotal] = useState(0),
    [hasMore, setHasMore] = useState(false),
    [totalIsEstimate, setTotalIsEstimate] = useState(false),
    [page, setPage] = useState(1),
    [searched, setSearched] = useState(false),
    [busy, setBusy] = useState(false),
    [recommending, setRecommending] = useState(false),
    [error, setError] = useState(""),
    [detail, setDetail] = useState<Contact | null>(null);
  const [applied, setApplied] = useState(filters);
  const personaId = selectedPersonaId ?? localPersonaId;
  const [jobId, setJobId] = useState(initialJobId || "");
  const [history, setHistory] = useState<PeopleJob[]>([]);
  const [searchJob, setSearchJob] = useState<PeopleJob | null>(null);
  const [restoring, setRestoring] = useState(true);
  const searchRequest = useRef(0);
  const onJobChangeRef = useRef(onJobChange);
  useEffect(() => {
    onJobChangeRef.current = onJobChange;
  }, [onJobChange]);
  useEffect(() => {
    if (jobId) onJobChangeRef.current?.(jobId);
  }, [jobId]);
  useEffect(
    () => () => {
      searchRequest.current += 1;
    },
    [],
  );
  useEffect(() => {
    let alive = true;
    api<PeopleJob[]>("/finance/search/jobs")
      .then((jobs) => {
        if (!alive) return;
        setHistory((old) => [
          ...jobs,
          ...old.filter((job) => !jobs.some((saved) => saved.id === job.id)),
        ]);
        // Restoring the last job would overwrite filters the composer just sent.
        if (!autoRun && !initialJobId && !onSelectContact && jobs[0])
          setJobId(jobs[0].id);
      })
      .catch((e) => {
        if (alive) setError(errorText(e));
      })
      .finally(() => {
        if (alive) setRestoring(false);
      });
    return () => {
      alive = false;
    };
  }, []);
  useEffect(() => {
    if (!jobId) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    let first = true;
    async function poll() {
      try {
        const job = await api<PeopleJob>("/people/jobs/" + jobId);
        if (!alive) return;
        setSearchJob(job);
        setHistory((old) =>
          old.some((saved) => saved.id === job.id)
            ? old.map((saved) => (saved.id === job.id ? job : saved))
            : [job, ...old],
        );
        const submitted = Object.fromEntries(
          Object.keys(filters).map((key) => [
            key,
            String(job.input[key] || ""),
          ]),
        ) as typeof filters;
        if (first) {
          setFilters(submitted);
          first = false;
        }
        if (job.status === "succeeded") {
          setApplied(submitted);
          setResults(job.result.items || []);
          setTotal(job.result.total || 0);
          setHasMore(searchHasMore(job.result, pageSize));
          setTotalIsEstimate(!!job.result.total_is_estimate);
          setPage(job.result.page || 1);
          setSearched(true);
          setBusy(false);
        } else if (job.status === "failed") {
          setError(job.error);
          setBusy(false);
        } else {
          setBusy(true);
          timer = setTimeout(poll, 1600);
        }
      } catch (e) {
        if (alive) {
          setError(errorText(e));
          setBusy(false);
        }
      }
    }
    void poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [jobId]);
  async function recommend(rows = results) {
    if (!personaId || !rows.length) return;
    setRecommending(true);
    try {
      const assessments = await post<Assessment[]>("/finance/assess", {
        contact_ids: rows.slice(0, 5).map((c) => c.id),
        persona_id: personaId,
        language: locale,
      });
      setResults((prev) =>
        prev.map((c) => ({
          ...c,
          assessments: [
            ...c.assessments,
            ...assessments.filter((a) => a.contact_id === c.id),
          ],
        })),
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setRecommending(false);
    }
  }
  async function search(n = 1, useFilters = filters) {
    const request = ++searchRequest.current;
    setBusy(true);
    setError("");
    setJobId("");
    try {
      const r = await post<{ job: PeopleJob; cached: boolean }>(
        "/finance/search/jobs",
        { ...useFilters, page: n, per_page: pageSize },
      );
      if (request !== searchRequest.current) return;
      setJobId(r.job.id);
      setSearchJob(r.job);
      setHistory((old) => [r.job, ...old.filter((j) => j.id !== r.job.id)]);
      if (r.job.status === "succeeded") {
        setResults(r.job.result.items || []);
        setTotal(r.job.result.total || 0);
        setHasMore(searchHasMore(r.job.result, pageSize));
        setTotalIsEstimate(!!r.job.result.total_is_estimate);
        setPage(r.job.result.page || n);
        setSearched(true);
        setApplied(useFilters);
        setBusy(false);
      }
    } catch (e) {
      if (request !== searchRequest.current) return;
      setError(errorText(e));
      setBusy(false);
    }
  }
  const autoRan = useRef(false);
  useEffect(() => {
    if (!autoRun || restoring || autoRan.current) return;
    autoRan.current = true;
    void search(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRun, restoring]);
  const update = (contact: Contact) => {
    setResults((old) => old.map((c) => (c.id === contact.id ? contact : c)));
    setDetail(contact);
    void refresh();
  };
  const pagination = (position: string) =>
    searched && (
      <nav
        className="pagination"
        aria-label={t(
          `Search pagination ${position}`,
          `搜索结果翻页${position === "top" ? "上方" : "下方"}`,
        )}
      >
        <span aria-live="polite">
          {totalIsEstimate
            ? t(
                `${results.length} profiles on this page · up to 10 per page`,
                `本页 ${results.length} 位人员 · 每页最多 10 位`,
              )
            : results.length
              ? t(
                  `${(page - 1) * pageSize + 1}–${(page - 1) * pageSize + results.length} of ${total} people`,
                  `第 ${(page - 1) * pageSize + 1}–${(page - 1) * pageSize + results.length} 位，共 ${total} 位`,
                )
              : t("No profiles on this page", "本页没有人员")}
          {!hasMore && !busy && ` · ${t("End of results", "已到最后一页")}`}
        </span>
        <div>
          <button
            type="button"
            aria-label={t("Previous page", "上一页")}
            className="button small-button"
            disabled={page === 1 || busy}
            onClick={() => void search(page - 1, applied)}
          >
            <ChevronLeft size={17} />
            {t("Previous 10", "前 10 位")}
          </button>
          <span>
            {totalIsEstimate
              ? t(`Page ${page}`, `第 ${page} 页`)
              : t(
                  `Page ${page} of ${Math.max(1, Math.ceil(total / pageSize))}`,
                  `第 ${page} / ${Math.max(1, Math.ceil(total / pageSize))} 页`,
                )}
          </span>
          <button
            type="button"
            aria-label={t("Next page", "下一页")}
            className="button small-button"
            disabled={!hasMore || page >= 500 || busy}
            onClick={() => void search(page + 1, applied)}
          >
            {t("Next 10", "后 10 位")}
            <ChevronRight size={17} />
          </button>
        </div>
      </nav>
    );
  return (
    <>
      <Heading title={t("People Search", "人员搜索")} />
      <section className="panel search-panel">
        <div className="section-head">
          <h2>
            <SlidersHorizontal size={17} />
            {t("Find your people", "筛选人员")}
          </h2>
          <Badge tone={config?.people_mode === "mock" ? "amber" : "green"}>
            {config?.people_mode === "mock" ? "MOCK DATA" : "GOOGLE · SERPAPI"}
          </Badge>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void search();
          }}
        >
          <div className="search-grid">
            {[
              [
                "title",
                "Job title",
                "职位",
                "e.g. Investment Banking Associate",
              ],
              [
                "company",
                "Company / institution",
                "公司或机构",
                "Name or domain",
              ],
              ["location", "Location", "地区", "e.g. New York"],
              ["keywords", "Keywords", "关键词", "e.g. M&A"],
            ].map(([key, en, zh, ph]) => (
              <Field key={key} label={t(en, zh)}>
                <input
                  value={filters[key as keyof typeof filters]}
                  placeholder={ph}
                  onChange={(e) =>
                    setFilters({ ...filters, [key]: e.target.value })
                  }
                />
              </Field>
            ))}
          </div>
          <div className="search-bottom">
            <Field label={t("Finance focus", "金融领域")}>
              <select
                value={filters.sector}
                onChange={(e) =>
                  setFilters({ ...filters, sector: e.target.value })
                }
              >
                <option value="">
                  {t("All finance areas", "全部金融领域")}
                </option>
                {sectors.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
            <Field label={t("Recommend for persona", "推荐所用画像")}>
              <select
                value={personaId}
                disabled={selectedPersonaId !== undefined}
                onChange={(e) => setPersonaId(e.target.value)}
              >
                <option value="">
                  {t("No persona · search freely", "无画像 · 自由搜索")}
                </option>
                {personas.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </Field>
            <button
              className="button primary"
              disabled={restoring || busy || recommending}
            >
              {busy ? <Busy /> : <Search size={16} />}{" "}
              {t("Search people", "搜索人员")}
            </button>
          </div>
        </form>
        <p className="filter-note">
          {config?.people_mode === "live"
            ? t(
                "Each search prepares public work and education details for this page through Apify before showing results. Cached profiles are reused; new retrievals may use credits. Filters are search keywords, not verified facts.",
                "每页搜索会先通过 Apify 自动准备公开履历与教育信息，再展示结果。已有资料会复用缓存，新查询可能消耗额度。筛选项是搜索关键词，并非已核实的人物信息。",
              )
            : t(
                "16 fictional profiles for testing. All filters work on this demo dataset.",
                "16 位虚构专业人士用于测试，所有筛选均对演示数据实际生效。",
              )}
        </p>
      </section>
      {error && (
        <div className="error-panel" role="alert">
          {error}
        </div>
      )}
      {history.length > 0 && (
        <div className="contacts-toolbar">
          <Field label={t("Saved searches", "已保存搜索")}>
            <select
              aria-label="Saved searches"
              value={jobId}
              disabled={busy}
              onChange={(e) => {
                setError("");
                setJobId(e.target.value);
              }}
            >
              <option value="" disabled>
                {t("Choose a saved search", "选择已保存搜索")}
              </option>
              {history.map((j) => (
                <option value={j.id} key={j.id}>
                  {String(
                    j.input.company ||
                      j.input.title ||
                      j.input.keywords ||
                      t("All people", "全部人员"),
                  )}{" "}
                  · {t("Page", "第")} {String(j.input.page || 1)} ·{" "}
                  {new Date(j.created_at).toLocaleString()} · {j.status}
                </option>
              ))}
            </select>
          </Field>
          {busy && (
            <span className="muted">
              <Busy />{" "}
              {searchJob?.result.profile_progress
                ? t(
                    `Preparing profile details: ${searchJob.result.profile_progress.total - searchJob.result.profile_progress.pending}/${searchJob.result.profile_progress.total}. You can leave and return.`,
                    `正在准备人员详情：${searchJob.result.profile_progress.total - searchJob.result.profile_progress.pending}/${searchJob.result.profile_progress.total}。可离开后返回。`,
                  )
                : t(
                    "Searching in background. You can switch pages and return.",
                    "后台搜索中，可切换页面后返回。",
                  )}
            </span>
          )}
          {searchJob?.status === "failed" && searchJob.retryable && (
            <button
              className="button small-button"
              onClick={async () => {
                try {
                  setError("");
                  await post("/people/jobs/" + searchJob.id + "/retry");
                  setJobId("");
                  setTimeout(() => setJobId(searchJob.id), 0);
                } catch (e) {
                  setError(errorText(e));
                }
              }}
            >
              {t("Retry search", "重试搜索")}
            </button>
          )}
        </div>
      )}
      <div className="results-header">
        <div>
          <h2>
            {searched
              ? t("Search results", "搜索结果")
              : t("Ready to explore", "开始探索")}
          </h2>
          {searched && (
            <span className="muted">
              {totalIsEstimate ? (
                t(
                  `${results.length} profiles on this page · Google estimate: ${total}`,
                  `本页 ${results.length} 位人员 · Google 估计约 ${total} 条结果`,
                )
              ) : (
                <>
                  {total} {t("people found", "位符合条件的人员")}
                </>
              )}
            </span>
          )}
        </div>
        {searched && results.length > 0 && (
          <button
            className="button"
            disabled={!personaId || recommending || busy}
            onClick={() => void recommend()}
          >
            {recommending ? <Busy /> : <Sparkles size={15} />}{" "}
            {t("Recommend first 5", "推荐当前前 5 位")}
          </button>
        )}
      </div>
      {pagination("top")}
      {!personaId && (
        <div className="notice">
          <Sparkles size={15} />
          {t(
            "Search freely. Select or create a persona when you want personalized recommendations.",
            "可以直接搜索。需要个性化推荐时，再选择或创建画像。",
          )}
          <Nav href="/personas">{t("Add background", "补充背景")}</Nav>
        </div>
      )}
      {busy ? (
        <div className="notice" role="status">
          <Busy />
          {t(
            "Preparing this page and its profile details…",
            "正在准备本页人员及其详情…",
          )}
        </div>
      ) : !searched ? (
        <Empty
          title={t("Who would you like to meet?", "您想认识什么样的人？")}
          detail={t(
            "Set a few filters or search all finance professionals to get started.",
            "设置筛选条件，或直接搜索全部金融领域专业人士。",
          )}
        />
      ) : results.length ? (
        <>
          <PeopleTable
            items={results}
            personaId={personaId}
            onSelectContact={onSelectContact}
            selectedContactId={selectedContactId}
            onDetail={setDetail}
            onSaved={(c) =>
              setResults((old) => old.map((x) => (x.id === c.id ? c : x)))
            }
          />
        </>
      ) : (
        <Empty
          title={t("No people found", "没有找到符合条件的人员")}
          detail={t(
            "Try a broader title, location, or finance area.",
            "请尝试更宽泛的职位、地区或领域条件。",
          )}
        />
      )}
      {pagination("bottom")}
      <div className="source-footnote">
        <Link2 size={14} />
        {t(
          "Open a person to read the prepared public profile. Unavailable details are marked; email lookup remains a separate action.",
          "点击人员即可阅读已准备的公开详情；无法取得的信息会明确标记，查找邮箱仍需单独操作。",
        )}
      </div>
      {detail && (
        <ContactDrawer
          key={detail.id}
          contact={detail}
          personaId={personaId}
          allowProfileFetch={false}
          selectedContactId={selectedContactId}
          onSelectContact={
            onSelectContact
              ? (contact) => {
                  onSelectContact(contact);
                  setDetail(null);
                }
              : undefined
          }
          onClose={() => setDetail(null)}
          onUpdate={update}
        />
      )}
    </>
  );
}

export function PeopleTable({
  items,
  personaId,
  onDetail,
  onSaved,
  onSelectContact,
  selectedContactId,
}: {
  items: Contact[];
  personaId?: string;
  onDetail: (c: Contact) => void;
  onSaved?: (c: Contact) => void;
  onSelectContact?: (c: Contact) => void;
  selectedContactId?: string;
}) {
  const { t, personas, refresh, notify, go } = useApp();
  const [busy, setBusy] = useState("");
  async function save(c: Contact) {
    setBusy(c.id);
    try {
      const r = await post<{ contact: Contact; already_saved: boolean }>(
        "/contacts/" + c.id + "/save",
      );
      onSaved?.(r.contact);
      await refresh();
      notify(
        r.already_saved
          ? t(
              "Already saved. No duplicate created.",
              "已保存过该联系人，未创建重复记录。",
            )
          : t("Contact saved to your network.", "联系人已保存。"),
      );
    } catch (e) {
      notify(errorText(e));
    } finally {
      setBusy("");
    }
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{t("PERSON", "人员")}</th>
            <th>{t("COMPANY", "机构")}</th>
            <th>{t("LOCATION", "地区")}</th>
            <th>{t("EMAIL STATUS", "邮箱状态")}</th>
            <th className="match-column">
              <Sparkles size={13} />
              {t("WHY CONNECT", "推荐依据")}
            </th>
            <th>{t("ACTIONS", "操作")}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => {
            const p = personas.find((p) => p.id === personaId);
            const a = [...c.assessments]
              .reverse()
              .find(
                (a) =>
                  (!personaId || a.persona_id === personaId) &&
                  (!p || a.persona_version === p.version),
              );
            return (
              <tr key={c.id}>
                <td>
                  <button className="person-cell" onClick={() => onDetail(c)}>
                    <Avatar name={c.name} />
                    <span>
                      <strong>{c.name}</strong>
                      <small>
                        {c.title || t("Title unavailable", "职位未知")}
                      </small>
                      <span className="source-label">
                        {c.provider === "mock"
                          ? "MOCK · FICTIONAL"
                          : c.provider.toUpperCase()}
                      </span>
                      {c.profile_prefetch &&
                        c.profile_prefetch.status !== "skipped" && (
                          <small title={c.profile_prefetch.error || undefined}>
                            {c.profile_prefetch.status === "succeeded"
                              ? t("Profile ready", "详情已准备")
                              : c.profile_prefetch.status === "failed"
                                ? t(
                                    "Some details unavailable",
                                    "部分详情未取得",
                                  )
                                : t("Preparing details…", "详情准备中…")}
                          </small>
                        )}
                    </span>
                  </button>
                </td>
                <td>
                  <strong className="company-name">{c.company || "—"}</strong>
                  <small>
                    {c.domains.finance?.sector || t("Finance", "金融")}
                  </small>
                </td>
                <td>
                  <span className="location">
                    <MapPin size={13} />
                    {c.location || t("Not provided", "未提供")}
                  </span>
                  {c.profile_url && (
                    <External url={c.profile_url}>
                      {t("Profile", "资料链接")}
                    </External>
                  )}
                </td>
                <td>
                  <EmailStatus contact={c} />
                </td>
                <td className="match-column">
                  {a ? (
                    <div className="match-reason">
                      <span className="match-marker">
                        <Sparkles size={12} />
                        {a.provider === "mock"
                          ? t("Mock recommendation", "模拟推荐")
                          : t("AI recommendation", "AI 推荐")}
                      </span>
                      <p>{a.reason}</p>
                      <small>
                        {t("Persona", "画像")} v{a.persona_version} ·{" "}
                        {a.source_ids.length} {t("sources", "条来源")}
                      </small>
                    </div>
                  ) : (
                    <span className="muted small">
                      {t(
                        "Select a persona and request a recommendation.",
                        "选择画像并请求推荐。",
                      )}
                    </span>
                  )}
                </td>
                <td>
                  <div className="row-actions">
                    <button
                      aria-label={(c.saved ? "Saved " : "Save ") + c.name}
                      title={t("Save contact", "保存联系人")}
                      className={`icon-button ${c.saved ? "saved" : ""}`}
                      disabled={busy === c.id}
                      onClick={() => void save(c)}
                    >
                      {busy === c.id ? (
                        <Busy />
                      ) : c.saved ? (
                        <Check size={16} />
                      ) : (
                        <Bookmark size={16} />
                      )}
                    </button>
                    {onSelectContact ? (
                      <button
                        type="button"
                        className={`button small-button ${selectedContactId === c.id ? "primary" : ""}`}
                        aria-pressed={selectedContactId === c.id}
                        onClick={() => onSelectContact(c)}
                      >
                        {selectedContactId === c.id ? (
                          <Check size={15} />
                        ) : (
                          <ArrowRight size={15} />
                        )}
                        {selectedContactId === c.id
                          ? t("Selected", "已选择")
                          : t("Use this contact", "选择此人")}
                      </button>
                    ) : (
                      <button
                        aria-label={"Write to " + c.name}
                        title={t("Write email", "撰写邮件")}
                        className="icon-button"
                        onClick={() =>
                          void go(
                            "/email?contact=" +
                              c.id +
                              (personaId ? "&persona=" + personaId : ""),
                          )
                        }
                      >
                        <Mail size={16} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
function EmailStatus({ contact: c }: { contact: Contact }) {
  const { t } = useApp();
  const label = c.email
    ? c.provider === "mock"
      ? t("Mock address", "模拟邮箱")
      : c.email_status === "verified"
        ? t("Provider reports verified", "服务商标记已验证")
        : t("Address found · unverified", "已取得邮箱 · 未验证")
    : ["available", "mock_available"].includes(c.email_status)
      ? t("Available to enrich", "可尝试补充")
      : c.email_status === "not_found"
        ? t("No Apollo match", "Apollo 未匹配到此人")
        : c.email_status === "unavailable"
          ? t("Unavailable", "暂无邮箱")
          : t("Not requested", "尚未补充");
  return (
    <Badge
      tone={
        c.email ? "green" : c.email_status === "available" ? "blue" : "gray"
      }
    >
      {label}
    </Badge>
  );
}

export function Contacts() {
  const { t, contacts } = useApp();
  const query = useSearchParams();
  const [term, setTerm] = useState(""),
    [tag, setTag] = useState(""),
    [detail, setDetail] = useState<Contact | null>(null),
    [manual, setManual] = useState(false);
  useEffect(() => {
    if (query.get("contact")) {
      const c = contacts.find((c) => c.id === query.get("contact"));
      if (c) setDetail(c);
    }
  }, [query, contacts]);
  const items = contacts.filter(
    (c) =>
      (!tag || c.tags.includes(tag)) &&
      [c.name, c.company, c.title, c.notes, ...c.tags]
        .join(" ")
        .toLowerCase()
        .includes(term.toLowerCase()),
  );
  return (
    <>
      <Heading title={t("Contacts", "联系人")}>
        <button className="button primary" onClick={() => setManual(true)}>
          <Plus size={16} />
          {t("Add contact", "添加联系人")}
        </button>
      </Heading>
      <div className="contacts-toolbar">
        <div className="search-input">
          <Search size={17} />
          <input
            aria-label="Search saved contacts"
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            placeholder={t(
              "Search names, companies or notes…",
              "搜索姓名、机构或备注…",
            )}
          />
        </div>
        <select
          aria-label="Filter by tag"
          value={tag}
          onChange={(e) => setTag(e.target.value)}
        >
          <option value="">{t("All tags", "全部标签")}</option>
          {[...new Set(contacts.flatMap((c) => c.tags))].map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
        <span className="muted">
          {items.length} {t("contacts", "位联系人")}
        </span>
      </div>
      {items.length ? (
        <PeopleTable items={items} onDetail={setDetail} />
      ) : (
        <Empty
          title={
            contacts.length
              ? t("No matching contacts", "没有匹配的联系人")
              : t("Your network starts here", "从这里建立人脉")
          }
          detail={t(
            "Save someone from People Search or add a contact manually.",
            "从人员搜索保存联系人，或手动添加。",
          )}
        >
          <Nav href="/people" className="button">
            <Search size={16} />
            {t("Find people", "搜索人员")}
          </Nav>
        </Empty>
      )}
      {detail && (
        <ContactDrawer
          key={detail.id}
          contact={detail}
          onClose={() => setDetail(null)}
          onUpdate={setDetail}
        />
      )}{" "}
      {manual && (
        <ContactForm
          onClose={() => setManual(false)}
          onDone={(c) => {
            setManual(false);
            setDetail(c);
          }}
        />
      )}
    </>
  );
}

export function ContactDrawer({
  contact,
  personaId = "",
  onClose,
  onUpdate,
  allowProfileFetch = true,
  onSelectContact,
  selectedContactId,
}: {
  contact: Contact;
  personaId?: string;
  onClose: () => void;
  onUpdate: (c: Contact) => void;
  allowProfileFetch?: boolean;
  onSelectContact?: (c: Contact) => void;
  selectedContactId?: string;
}) {
  const { t, locale, personas, refresh, notify, go, config } = useApp();
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  const close = () => {
    active.current = false;
    onClose();
  };
  const [c, setC] = useState(contact),
    [editing, setEditing] = useState(false),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [pid, setPid] = useState(personaId || personas[0]?.id || ""),
    [emailProvider, setEmailProvider] = useState<"email" | "email_apify">(
      "email_apify",
    );
  useEffect(() => {
    let active = true;
    api<Contact>("/contacts/" + contact.id)
      .then((c) => {
        if (active) setC({ ...c, profile_prefetch: contact.profile_prefetch });
      })
      .catch((e) => {
        if (active) setError(errorText(e));
      });
    return () => {
      active = false;
    };
  }, [contact.id]);
  const pendingJobs = (c.jobs || []).filter((j) =>
    ["queued", "running", "waiting"].includes(j.status),
  );
  const pendingKey = pendingJobs.map((j) => j.id).join(",");
  useEffect(() => {
    if (!pendingKey) return;
    let alive = true;
    const timer = setInterval(() => {
      api<Contact>("/contacts/" + contact.id)
        .then((updated) => {
          if (!alive || !active.current) return;
          setC(updated);
          onUpdate(updated);
          if (
            !(updated.jobs || []).some((j) =>
              ["queued", "running", "waiting"].includes(j.status),
            )
          )
            void refresh();
        })
        .catch((e) => {
          if (alive) setError(errorText(e));
        });
    }, 1800);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [contact.id, pendingKey]);
  async function startJob(
    kind: "profile" | "email" | "email_apify",
    force = false,
  ) {
    setBusy(kind);
    setError("");
    try {
      const r = await post<{ cached: boolean }>("/contacts/" + c.id + "/jobs", {
        kind,
        force,
      });
      if (!active.current) return;
      if (r.cached)
        notify(
          t(
            "Using the saved result or existing background task.",
            "已复用保存的结果或现有后台任务。",
          ),
        );
      const updated = await api<Contact>("/contacts/" + c.id);
      if (!active.current) return;
      setC(updated);
      onUpdate(updated);
      await refresh();
    } catch (e) {
      if (active.current) setError(errorText(e));
    } finally {
      if (active.current) setBusy("");
    }
  }
  async function action(name: string) {
    setBusy(name);
    setError("");
    try {
      if (name === "assess") {
        await post("/finance/assess", {
          contact_ids: [c.id],
          persona_id: pid,
          language: locale,
        });
      } else if (name === "save") {
        const r = await post<{ already_saved: boolean }>(
          "/contacts/" + c.id + "/save",
        );
        if (!active.current) return;
        notify(
          r.already_saved
            ? t("Already saved. No duplicate created.", "已存在，未重复保存。")
            : t("Contact saved.", "联系人已保存。"),
        );
      } else await post("/contacts/" + c.id + "/" + name);
      const updated = await api<Contact>("/contacts/" + c.id);
      if (!active.current) return;
      setC(updated);
      onUpdate(updated);
      await refresh();
    } catch (e) {
      if (active.current) setError(errorText(e));
    } finally {
      if (active.current) setBusy("");
    }
  }
  const selectedPersona = personas.find((p) => p.id === pid);
  const assessment = [...c.assessments]
    .reverse()
    .find(
      (a) =>
        a.persona_id === pid && a.persona_version === selectedPersona?.version,
    );
  if (editing)
    return (
      <ContactForm
        contact={c}
        onClose={() => setEditing(false)}
        onDone={(updated) => {
          if (!active.current) return;
          setC(updated);
          onUpdate(updated);
          setEditing(false);
        }}
      />
    );
  return (
    <Drawer title={t("Contact details", "联系人详情")} onClose={close}>
      <div className="drawer-profile">
        <Avatar name={c.name} large />
        <Badge tone={c.provider === "mock" ? "amber" : "blue"}>
          {c.provider === "mock"
            ? t("Mock · Fictional person", "模拟 · 虚构人物")
            : c.provider}
        </Badge>
        <h2>{c.name}</h2>
        <p>{c.title}</p>
        <strong>{c.company}</strong>
        <span className="location">
          <MapPin size={14} />
          {c.location || t("Location not provided", "未提供地区")}
        </span>
      </div>
      <div className="drawer-actions">
        {onSelectContact ? (
          <button
            type="button"
            className="button primary"
            aria-pressed={selectedContactId === c.id}
            onClick={() => onSelectContact(c)}
          >
            {selectedContactId === c.id ? (
              <Check size={16} />
            ) : (
              <ArrowRight size={16} />
            )}
            {selectedContactId === c.id
              ? t("Selected", "已选择")
              : t("Use this contact", "选择此人")}
          </button>
        ) : (
          <button
            className="button primary"
            onClick={() =>
              void go("/email?contact=" + c.id + (pid ? "&persona=" + pid : ""))
            }
          >
            <Mail size={16} />
            {t("Write email", "撰写邮件")}
          </button>
        )}
        <button
          className="button"
          disabled={!!busy}
          onClick={() => void action("save")}
        >
          {c.saved ? <Check size={15} /> : <Bookmark size={15} />}{" "}
          {c.saved ? t("Saved", "已保存") : t("Save", "保存")}
        </button>
        <button
          className="icon-button"
          aria-label="Edit contact"
          onClick={() => setEditing(true)}
        >
          <PencilLine size={16} />
        </button>
      </div>
      {error && (
        <div className="error-panel" role="alert">
          {error}
        </div>
      )}
      <section className="drawer-section">
        <h3>{t("Contact information", "联系信息")}</h3>
        <dl>
          <dt>{t("Email", "邮箱")}</dt>
          <dd>
            {c.email || "—"} <EmailStatus contact={c} />
          </dd>
          <dt>{t("Phone", "电话")}</dt>
          <dd>
            {t(
              "Not requested · phone lookup is not enabled",
              "未请求 · 暂未启用电话号码获取",
            )}
          </dd>
          <dt>{t("School", "学校")}</dt>
          <dd>{c.school || t("Not provided", "未提供")}</dd>
          <dt>{t("Profile", "资料链接")}</dt>
          <dd>
            {c.profile_url ? (
              <External url={c.profile_url}>
                {t("View public profile", "查看公开资料")}
              </External>
            ) : (
              t("No profile link provided", "暂无资料链接")
            )}
          </dd>
        </dl>
        {c.provider !== "mock" && (
          <Field label={t("Email provider", "邮箱查找服务商")}>
            <select
              aria-label="Email provider"
              value={emailProvider}
              onChange={(e) =>
                setEmailProvider(e.target.value as "email" | "email_apify")
              }
            >
              <option value="email_apify">
                Apify · {t("Independent email search", "独立查找邮箱")}
              </option>
              <option value="email">
                Apollo · {t("API access required", "需要 API 套餐权限")}
              </option>
            </select>
          </Field>
        )}
        {(c.provider !== "manual" ||
          c.profile_url.includes("linkedin.com/in/")) && (
          <button
            className="button small-button"
            disabled={
              !!busy ||
              pendingJobs.some(
                (j) => j.kind === "email" || j.kind === "email_apify",
              )
            }
            onClick={() =>
              void startJob(c.provider === "mock" ? "email" : emailProvider)
            }
          >
            {["email", "email_apify"].includes(busy) ||
            pendingJobs.some(
              (j) => j.kind === "email" || j.kind === "email_apify",
            ) ? (
              <Busy />
            ) : (
              <Plus size={14} />
            )}{" "}
            {c.provider === "mock"
              ? t("Enrich contact / email", "补充联系人或邮箱")
              : emailProvider === "email_apify"
                ? t("Find email with Apify", "使用 Apify 查找邮箱")
                : t("Match with Apollo & get email", "Apollo 匹配并获取邮箱")}
          </button>
        )}
        <p className="muted small">
          {t(
            "One person per request. Email search uses the selected provider and may use credits. Results are cached for 7 days; email coverage is not guaranteed. If Apollo denies API access, select Apify.",
            "每次一人，由所选服务商独立查找并可能消耗额度，结果缓存 7 天，不保证取得邮箱。Apollo 接口受限时可选择 Apify。",
          )}
        </p>
      </section>
      <section className="drawer-section">
        <h3>{t("Professional profile", "履历与教育")}</h3>
        {allowProfileFetch && c.provider !== "mock" && (
          <button
            className="button small-button"
            disabled={!!busy || pendingJobs.some((j) => j.kind === "profile")}
            onClick={() => void startJob("profile")}
          >
            {pendingJobs.some((j) => j.kind === "profile") ? (
              <Busy />
            ) : (
              <Plus size={14} />
            )}{" "}
            {t("Get profile details", "补全履历教育")} · Apify
          </button>
        )}
        {c.profile_prefetch?.status === "failed" && (
          <p className="error-panel" role="status">
            {t(
              "Some public details could not be prepared: ",
              "部分公开详情未能取得：",
            )}
            {c.profile_prefetch.error}
          </p>
        )}
        {c.professional?.retrieved_at && (
          <p className="muted small">
            Apify · <DateLabel value={c.professional.retrieved_at} /> ·{" "}
            {t("Public profile, may be incomplete", "公开资料，可能不完整")}
          </p>
        )}
        {c.professional?.summary && (
          <p style={{ whiteSpace: "pre-wrap" }}>{c.professional.summary}</p>
        )}
        <h4>{t("Experience", "工作履历")}</h4>
        {c.professional?.experience?.length ? (
          c.professional.experience.map((x, i) => (
            <div className="evidence" key={i}>
              <strong>{x.title || t("Title unavailable", "未提供职位")}</strong>
              <p>{x.company}</p>
              <small>
                {[x.start_date, x.end_date].filter(Boolean).join(" – ")}{" "}
                {x.location}
              </small>
              {x.description && (
                <details>
                  <summary>{t("Details", "详情")}</summary>
                  <p style={{ whiteSpace: "pre-wrap" }}>{x.description}</p>
                </details>
              )}
            </div>
          ))
        ) : (
          <p className="muted">
            {t(
              "Experience not retrieved or not publicly available.",
              "尚未取得履历或公开资料未提供。",
            )}
          </p>
        )}
        <h4>{t("Education", "教育经历")}</h4>
        {c.professional?.education?.length ? (
          c.professional.education.map((x, i) => (
            <div className="evidence" key={i}>
              <strong>{x.school}</strong>
              <p>{[x.degree, x.field_of_study].filter(Boolean).join(" · ")}</p>
              <small>
                {[x.start_date, x.end_date].filter(Boolean).join(" – ")}
              </small>
            </div>
          ))
        ) : (
          <p className="muted">
            {t(
              "Education not retrieved or not publicly available.",
              "尚未取得教育经历或公开资料未提供。",
            )}
          </p>
        )}
        {!!c.professional?.skills?.length && (
          <>
            <h4>{t("Skills", "技能")}</h4>
            <div className="tags">
              {c.professional.skills.map((skill) => (
                <Badge key={skill}>{skill}</Badge>
              ))}
            </div>
          </>
        )}
        {!!c.missing_fields?.length && (
          <p className="muted small">
            {t("Missing information", "缺失信息")}：
            {c.missing_fields
              .map(
                (key) =>
                  ({
                    title: t("title", "职位"),
                    company: t("company", "机构"),
                    location: t("location", "地区"),
                    school: t("school", "学校"),
                    email: t("email", "邮箱"),
                    phone: t("phone", "电话"),
                    experience: t("experience", "履历"),
                    education: t("education", "教育"),
                    skills: t("skills", "技能"),
                  })[key] || key,
              )
              .join("、")}
          </p>
        )}
      </section>
      {!!c.jobs?.length && (
        <section className="drawer-section">
          <h3>{t("Background tasks", "后台任务")}</h3>
          <p className="muted small">
            {t(
              "Tasks and results are saved. You can leave this page.",
              "任务和结果自动保存，可以离开此页面。",
            )}
          </p>
          {c.jobs.slice(0, 5).map((j) => (
            <div className="evidence" key={j.id}>
              <strong>
                {j.kind === "profile"
                  ? t("Apify profile", "Apify 履历教育")
                  : j.kind === "email_apify"
                    ? t("Apify email", "Apify 邮箱")
                    : t("Apollo email", "Apollo 邮箱")}
              </strong>{" "}
              ·{" "}
              <Badge>
                {
                  {
                    queued: t("Queued", "排队中"),
                    running: t("Running", "执行中"),
                    waiting: t("Fetching profile", "获取资料中"),
                    succeeded: t("Complete", "已完成"),
                    failed: t("Failed", "失败"),
                  }[j.status]
                }
              </Badge>
              {j.error && <p role="alert">{j.error}</p>}
              {j.status === "failed" && j.retryable && (
                <button
                  className="button small-button"
                  onClick={async () => {
                    try {
                      await post("/people/jobs/" + j.id + "/retry");
                      const updated = await api<Contact>("/contacts/" + c.id);
                      if (active.current) setC(updated);
                    } catch (e) {
                      setError(errorText(e));
                    }
                  }}
                >
                  {t("Retry task", "重试任务")}
                </button>
              )}
            </div>
          ))}
        </section>
      )}
      <section className="drawer-section">
        <h3>
          <Sparkles size={16} />
          {t("Why connect", "推荐依据")}
        </h3>
        <div className="row">
          <select
            aria-label="Recommendation persona"
            value={pid}
            disabled={!!onSelectContact}
            onChange={(e) => setPid(e.target.value)}
          >
            <option value="">{t("Select persona", "选择画像")}</option>
            {personas.map((p) => (
              <option value={p.id} key={p.id}>
                {p.label}
              </option>
            ))}
          </select>
          <button
            className="button small-button"
            disabled={!pid || !!busy}
            onClick={() => void action("assess")}
          >
            {busy === "assess" ? <Busy /> : <Sparkles size={14} />}
          </button>
        </div>
        {assessment ? (
          <div className="recommendation-box">
            <Badge>
              {assessment.provider === "mock" ? "MOCK AI" : "AI"} · v
              {assessment.persona_version}
            </Badge>
            <p>{assessment.reason}</p>
            <small>
              {assessment.source_ids.length}{" "}
              {t("cited sources below", "条引用来源见下方")}
            </small>
          </div>
        ) : (
          <p className="muted">
            {t(
              "Choose a persona and request an assessment. Older persona versions are not reused.",
              "选择画像后获取推荐，不会复用旧版本画像的推荐。",
            )}
          </p>
        )}
      </section>
      <section className="drawer-section">
        <h3>{t("Sources & evidence", "来源与证据")}</h3>
        {c.sources.map((s) => (
          <div className="evidence" key={s.id}>
            <External url={s.url}>{s.title}</External>
            <p>{s.snippet}</p>
            <small>
              {s.provider.toUpperCase()} · <DateLabel value={s.retrieved_at} />{" "}
              ·{" "}
              {["unverified_lead", "discovery"].includes(s.kind)
                ? t("Unverified lead", "待核实线索")
                : t("Profile evidence", "资料依据")}
            </small>
          </div>
        ))}
        <button
          className="button small-button"
          disabled={!!busy}
          onClick={() => void action("public-sources")}
        >
          {busy === "public-sources" ? <Busy /> : <Search size={14} />}{" "}
          {t("Find public sources", "补充公开来源")} ·{" "}
          {config?.public_search_mode === "mock" ? "Mock" : "SerpAPI"}
        </button>
      </section>
      <section className="drawer-section">
        <h3>{t("Tags & notes", "标签与备注")}</h3>
        <div className="tags">
          {c.tags.map((s) => (
            <Badge key={s}>{s}</Badge>
          ))}
        </div>
        <p>
          {c.notes ||
            t(
              "No notes yet. Use Edit to add context.",
              "暂无备注。点击编辑补充背景。",
            )}
        </p>
      </section>
      <section className="drawer-section">
        <h3>{t("Related drafts", "关联草稿")}</h3>
        {c.drafts?.length ? (
          c.drafts.map((d) => (
            <Nav
              key={d.id}
              className="draft-link"
              href={"/email?draft=" + d.id}
            >
              {d.subject || t("Untitled draft", "未命名草稿")}
              <ArrowUpRight size={15} />
            </Nav>
          ))
        ) : (
          <p className="muted">
            {t("No drafts for this contact yet.", "尚未为该联系人建立草稿。")}
          </p>
        )}
      </section>
    </Drawer>
  );
}

function ContactForm({
  contact,
  onClose,
  onDone,
}: {
  contact?: Contact;
  onClose: () => void;
  onDone: (c: Contact) => void;
}) {
  const { t, refresh } = useApp();
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  const close = () => {
    active.current = false;
    onClose();
  };
  const [data, setData] = useState({
      name: contact?.name || "",
      title: contact?.title || "",
      company: contact?.company || "",
      location: contact?.location || "",
      school: contact?.school || "",
      profile_url: contact?.profile_url || "",
      email: contact?.email || "",
      notes: contact?.notes || "",
      sector: contact?.domains.finance?.sector || "",
      tags: contact?.tags.join(", ") || "",
    }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const body = {
        ...data,
        tags: data.tags
          .split(/[,，]/)
          .map((x) => x.trim())
          .filter(Boolean),
      };
      const c = contact
        ? await put<Contact>("/contacts/" + contact.id, body)
        : await post<Contact>("/contacts", body);
      await refresh();
      if (active.current) onDone(c);
    } catch (e) {
      if (active.current) setError(errorText(e));
    } finally {
      if (active.current) setBusy(false);
    }
  }
  return (
    <Drawer
      title={
        contact
          ? t("Edit contact", "编辑联系人")
          : t("Add a contact", "添加联系人")
      }
      onClose={close}
    >
      <form className="contact-form" onSubmit={save}>
        <p className="muted">
          {t(
            "Add only information you know. An email address is optional.",
            "仅填写已知资料。邮箱为可选项。",
          )}
        </p>
        {error && (
          <div className="error-panel" role="alert">
            {error}
          </div>
        )}
        <div className="form-grid">
          {[
            ["name", "Full name", "姓名"],
            ["title", "Job title", "职位"],
            ["company", "Company / institution", "公司或机构"],
            ["location", "Location", "地区"],
            ["school", "School", "学校"],
            ["email", "Email (optional)", "邮箱（可选）"],
            ["profile_url", "Profile URL", "资料链接"],
            ["sector", "Finance focus", "金融领域"],
            ["tags", "Tags (comma separated)", "标签（逗号分隔）"],
          ].map(([key, en, zh]) => (
            <Field key={key} label={t(en, zh)} className="full">
              <input
                required={key === "name"}
                type={
                  key === "email"
                    ? "email"
                    : key === "profile_url"
                      ? "url"
                      : "text"
                }
                value={data[key as keyof typeof data]}
                onChange={(e) => setData({ ...data, [key]: e.target.value })}
              />
            </Field>
          ))}
          <Field label={t("Notes", "备注")} className="full">
            <textarea
              rows={4}
              value={data.notes}
              onChange={(e) => setData({ ...data, notes: e.target.value })}
            />
          </Field>
        </div>
        <div className="form-footer">
          <button type="button" className="button" onClick={close}>
            {t("Cancel", "取消")}
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? <Busy /> : <Save size={16} />}{" "}
            {t("Save contact", "保存联系人")}
          </button>
        </div>
      </form>
    </Drawer>
  );
}
