"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Plus,
  Mail,
  FileText,
  Sparkles,
  Scissors,
  SlidersHorizontal,
  Eye,
  Copy,
  Check,
  Save,
  RefreshCw,
  X,
  ExternalLink,
  Download,
  Braces,
} from "lucide-react";
import { useApp } from "@/lib/context";
import { api, post, put, errorText } from "@/lib/api";
import type {
  Draft,
  Contact,
  Preview,
  Generation,
  WritingModels,
} from "@/lib/types";
import { useDraft } from "@/lib/use-draft";
import { Heading, Field, Badge, Busy, Nav, Drawer, DateLabel } from "./ui";
import RichEditor from "./rich-editor";
import WritingPrompt from "./writing-prompt";
import WritingTemplateLibrary from "./writing-template-library";
import { SendDraft } from "./mail-send";
import "./email-writing.css";

export default function EmailStudio() {
  const { t, drafts, refresh, go, notify, guard } = useApp(),
    query = useSearchParams();
  const id = query.get("draft"),
    contact = query.get("contact"),
    persona = query.get("persona");
  const creating = useRef("");
  const [busy, setBusy] = useState(false);
  async function create(cid: string | null = null, pid: string | null = null) {
    setBusy(true);
    try {
      if (guard.current) await guard.current();
      const d = await post<Draft>("/drafts", {
        contact_id: cid,
        persona_id: pid,
      });
      await refresh();
      await go("/email?draft=" + d.id);
    } catch (e) {
      notify(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (contact && !id && creating.current !== `${contact}:${persona || ""}`) {
      creating.current = `${contact}:${persona || ""}`;
      void create(contact, persona);
    }
  }, [contact, id, persona]);
  return (
    <>
      <Heading
        title={t("Email Studio", "邮件工作室")}
        detail={t(
          "Each draft keeps its own brief, context, and AI suggestions.",
          "每封草稿独立保存写作要求、背景与 AI 建议。 ",
        )}
      >
        <button
          className="button primary"
          disabled={busy}
          onClick={() => void create()}
        >
          {busy ? <Busy /> : <Plus size={16} />} {t("New draft", "新建草稿")}
        </button>
      </Heading>
      <div className="studio-layout">
        <aside className="draft-list panel">
          <div className="section-head">
            <h2>{t("Drafts", "草稿")}</h2>
            <Badge>{drafts.length}</Badge>
          </div>
          {drafts.length ? (
            drafts.map((d) => (
              <Nav
                key={d.id}
                className={`draft-tile ${id === d.id ? "selected" : ""}`}
                href={"/email?draft=" + d.id}
              >
                <div>
                  <FileText size={15} />
                  <span>
                    {d.status === "ready"
                      ? t("Reviewed", "已审核")
                      : t("Draft", "草稿")}
                  </span>
                  <small>{d.language.toUpperCase()}</small>
                </div>
                <strong>
                  {d.subject || t("Untitled draft", "未命名草稿")}
                </strong>
                <p>{d.purpose || t("A new conversation", "一次新的交流")}</p>
                <small>
                  <DateLabel value={d.updated_at} />
                </small>
              </Nav>
            ))
          ) : (
            <div className="muted draft-empty">
              {t(
                "Your saved drafts will appear here.",
                "保存后的草稿将在此显示。",
              )}
            </div>
          )}
          <div className="draft-list-note">
            <Mail size={17} />
            {t(
              "Write, review, then send or schedule with your connected Gmail mailbox.",
              "撰写并审核后，使用已连接的 Gmail 邮箱发送或预约发送。",
            )}
          </div>
        </aside>
        {id ? (
          <DraftEditor key={id} id={id} />
        ) : (
          <section className="panel editor-welcome">
            <span className="welcome-icon" aria-hidden="true">
              <Mail size={35} />
            </span>
            <h2>{t("No draft selected", "尚未选择草稿")}</h2>
            <p>
              {t(
                "Choose a saved draft, or open a blank page. Add a contact and persona when you want a personalized starting point.",
                "打开已有草稿或创建空白邮件。选择联系人和画像，即可获得个性化写作起点。",
              )}
            </p>
            <button
              className="button primary"
              disabled={busy}
              onClick={() => void create()}
            >
              <Plus size={16} />
              {t("Create a draft", "创建草稿")}
            </button>
            <div className="writing-points">
              <span>Networking</span>
              <span>Informational Interview</span>
              <span>Recruiting</span>
            </div>
          </section>
        )}
      </div>
    </>
  );
}

export function DraftEditor({
  id,
  replySubject,
  loadPreview,
  disabled = false,
  replyMessageId,
  mailboxId,
  onSent,
  contextLocked = false,
  hideDelivery = false,
}: {
  id: string;
  replySubject?: string;
  loadPreview?: () => Promise<Preview>;
  disabled?: boolean;
  replyMessageId?: string;
  mailboxId?: string;
  onSent?: () => void;
  contextLocked?: boolean;
  hideDelivery?: boolean;
}) {
  const { t, personas, contacts, refresh, notify, config } = useApp();
  const {
    draft,
    saveState,
    error,
    recovered,
    edit,
    flush,
    accept,
    loadLatest,
    setError,
  } = useDraft(id);
  const [working, setBusy] = useState(false),
    [preview, setPreview] = useState<Preview | null>(null),
    [extra, setExtra] = useState<Contact | null>(null),
    [showVariables, setShowVariables] = useState(false),
    [models, setModels] = useState<WritingModels | null>(null),
    [modelError, setModelError] = useState(""),
    [jobs, setJobs] = useState<Generation[]>([]),
    [jobsError, setJobsError] = useState(""),
    [jobsVersion, setJobsVersion] = useState(0),
    [showHistory, setShowHistory] = useState(false);
  const busy = working || disabled;
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  useEffect(() => {
    let cancelled = false;
    setExtra(null);
    if (draft?.contact_id && !contacts.some((c) => c.id === draft.contact_id))
      api<Contact>("/contacts/" + draft.contact_id)
        .then((c) => {
          if (!cancelled) setExtra(c);
        })
        .catch((e) => {
          if (!cancelled) setError(errorText(e));
        });
    return () => {
      cancelled = true;
    };
  }, [draft?.contact_id, contacts, setError]);
  useEffect(() => {
    let cancelled = false;
    api<WritingModels>("/ai/models")
      .then((m) => {
        if (!cancelled) {
          setModels(m);
          setModelError("");
        }
      })
      .catch((e) => {
        if (!cancelled) setModelError(errorText(e));
      });
    return () => {
      cancelled = true;
    };
  }, [config?.ai_mode, jobsVersion]);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function readJobs() {
      try {
        const latest = await api<Generation[]>(
          "/drafts/" + id + "/generations",
          { signal: controller.signal },
        );
        if (cancelled) return;
        setJobs(latest);
        setJobsError("");
        if (latest.some((j) => j.status === "queued" || j.status === "running"))
          timer = setTimeout(() => void readJobs(), 1800);
      } catch (e) {
        if (!cancelled) {
          setJobsError(errorText(e));
          timer = setTimeout(() => void readJobs(), 5000);
        }
      }
    }
    void readJobs();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, [id, jobsVersion]);
  async function generate(action = "generate") {
    setBusy(true);
    setError("");
    try {
      const saved = await flush();
      if (!saved || !active.current) return;
      const job = await post<Generation>("/drafts/" + id + "/generations", {
        action,
        revision: saved.revision,
      });
      if (!active.current) return;
      setJobs((previous) => [job, ...previous.filter((j) => j.id !== job.id)]);
      setJobsVersion((v) => v + 1);
      notify(
        t(
          "AI is working. You can edit or leave this page; the suggestion is saved with this draft.",
          "AI 正在生成。可继续编辑或离开页面，建议将保存在这封草稿中。",
        ),
      );
      await refresh();
    } catch (e) {
      if (active.current) {
        setError(errorText(e));
        setJobsVersion((v) => v + 1);
      }
    } finally {
      if (active.current) setBusy(false);
    }
  }
  async function useSuggestion(job: Generation) {
    setBusy(true);
    setError("");
    try {
      const saved = await flush();
      if (!saved || !active.current) return;
      const updated = await post<Draft>(
        `/drafts/${id}/generations/${job.id}/accept`,
        { revision: saved.revision },
      );
      if (!active.current) return;
      accept(updated);
      setJobsVersion((v) => v + 1);
      await refresh();
      notify(
        t(
          "Suggestion inserted. Review the facts and edit before use.",
          "建议已插入，请检查事实并按需修改。",
        ),
      );
    } catch (e) {
      if (active.current) setError(errorText(e));
    } finally {
      if (active.current) setBusy(false);
    }
  }
  async function discardSuggestion(job: Generation) {
    setBusy(true);
    try {
      const updated = await post<Generation>(
        `/drafts/${id}/generations/${job.id}/discard`,
      );
      if (active.current)
        setJobs((previous) =>
          previous.map((j) => (j.id === job.id ? updated : j)),
        );
    } catch (e) {
      if (active.current) setError(errorText(e));
    } finally {
      if (active.current) setBusy(false);
    }
  }
  async function reloadDraft() {
    setBusy(true);
    try {
      await loadLatest();
    } catch (e) {
      if (active.current) setError(errorText(e));
    } finally {
      if (active.current) setBusy(false);
    }
  }
  async function showPreview() {
    setBusy(true);
    try {
      await flush();
      setPreview(
        await (loadPreview
          ? loadPreview()
          : api<Preview>("/drafts/" + id + "/preview")),
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function applyTemplate(content: Pick<Draft, "subject" | "body_html">) {
    setBusy(true);
    try {
      // Preserve this tab's save/conflict rules before replacing email content.
      await flush();
      if (!active.current) return;
      edit({
        ...(replySubject === undefined
          ? content
          : { body_html: content.body_html }),
        writing_mode: "template",
      });
      await flush();
      await refresh();
    } finally {
      if (active.current) setBusy(false);
    }
  }
  async function save() {
    try {
      await flush();
      await refresh();
      notify(t("Draft saved on the server.", "草稿已保存到服务端。"));
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function ready() {
    setBusy(true);
    try {
      const latest = await flush();
      if (!latest) return;
      accept(await put<Draft>("/drafts/" + id, { ...latest, status: "ready" }));
      await refresh();
      notify(
        t(
          "Marked as reviewed. No email was sent.",
          "已标记为审核完成，未发送邮件。",
        ),
      );
      setPreview(null);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function copy(kind: "subject" | "body" | "both", p: Preview) {
    const text =
      kind === "subject"
        ? p.subject
        : kind === "body"
          ? p.body_text
          : `Subject: ${p.subject}\n\n${p.body_text}`;
    try {
      await navigator.clipboard.writeText(text);
      notify(t("Copied to clipboard.", "已复制到剪贴板。"));
    } catch {
      setError(
        t(
          "Clipboard access was denied. Select the preview text and copy it manually.",
          "剪贴板访问被拒绝，请选择预览文字后手动复制。",
        ),
      );
    }
  }
  if (!draft)
    return (
      <div className="panel">
        <div className="empty">
          {error || t("Opening draft…", "正在打开草稿…")}
        </div>
      </div>
    );
  const allContacts =
    extra && !contacts.some((c) => c.id === extra.id)
      ? [extra, ...contacts]
      : contacts;
  const recipient = allContacts.find((c) => c.id === draft.contact_id);
  const pending = jobs.some(
    (j) => j.status === "queued" || j.status === "running",
  );
  const visibleJobs = jobs.filter(
    (j) => showHistory || (j.status !== "accepted" && j.status !== "discarded"),
  );
  const modelOptions = models?.models || [];
  const selectedModel = modelOptions.find(
    (m) => m.id === (draft.model || models?.default_model),
  );
  const selectedModelAvailable =
    !!selectedModel && (selectedModel.available ?? !!models?.configured);
  const modelGroups = Array.from(
    new Set(
      modelOptions.map((m) => m.provider_label || models?.provider || "AI"),
    ),
  );
  const canGenerate =
    (draft.writing_mode === "prompt"
      ? !!draft.custom_instructions?.trim()
      : draft.writing_mode === "template"
        ? !!draft.body_html.replace(/<[^>]*>/g, "").trim()
        : !!draft.purpose.trim()) &&
    selectedModelAvailable &&
    !busy &&
    !pending;
  return (
    <section className="editor-main">
      <div className="panel editor-context writing-brief">
        <div className="section-head">
          <h2>
            <Sparkles size={17} />
            {t("Writing brief", "写作要求")}
          </h2>
          <Badge tone={config?.ai_mode === "mock" ? "amber" : "gray"}>
            {config?.ai_mode === "mock"
              ? t("DEMO AI", "模拟 AI")
              : selectedModel?.provider_label || models?.provider || "AI"}
          </Badge>
        </div>
        <div
          className="writing-mode-tabs"
          role="group"
          aria-label={t("Writing mode", "写作方式")}
        >
          {(["assisted", "prompt", "template"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              aria-pressed={(draft.writing_mode || "assisted") === mode}
              disabled={busy}
              onClick={() => edit({ writing_mode: mode })}
            >
              {mode === "assisted"
                ? t("Assisted", "引导写作")
                : mode === "prompt"
                  ? t("Prompt", "自定义 Prompt")
                  : t("Template", "邮件模板")}
            </button>
          ))}
        </div>
        <p className="writing-mode-hint">
          {draft.writing_mode === "prompt"
            ? t(
                "Control the message with your own prompt, then review the AI suggestion before inserting it.",
                "用自定义 Prompt 控制邮件内容，审核 AI 建议后再插入。",
              )
            : draft.writing_mode === "template"
              ? t(
                  "Use a saved template or create your own. Edit it directly or ask AI to personalize it.",
                  "使用已保存模板或创建自定义模板，可直接编辑或请 AI 生成个性化内容。",
                )
              : t(
                  "Describe your context and goal. Add a contact and persona whenever useful, then review the generated preview.",
                  "描述背景与目标，可随时添加联系人和画像，再审核生成预览。",
                )}
        </p>
        <fieldset disabled={busy}>
          {draft.writing_mode === "prompt" && (
            <WritingPrompt draft={draft} edit={edit} />
          )}
          {draft.writing_mode === "template" && (
            <WritingTemplateLibrary
              draft={
                replySubject === undefined
                  ? draft
                  : { ...draft, subject: replySubject }
              }
              disabled={busy}
              flush={async () => {
                const saved = await flush();
                return saved && replySubject !== undefined
                  ? { ...saved, subject: replySubject }
                  : saved;
              }}
              bodyOnly={replySubject !== undefined}
              onApply={applyTemplate}
            />
          )}
          {(draft.writing_mode || "assisted") === "assisted" && (
            <div
              className="email-mode-intro"
              aria-label={t("Assisted writing", "引导写作")}
            >
              <strong>
                {t("Build a brief, one detail at a time", "逐项填写写作要求")}
              </strong>
              <p>
                {t(
                  "Set the purpose and next step, choose your style, and select evidence to make the message relevant.",
                  "设置联系目的与下一步，选择写作风格及证据，让邮件贴合收件人。",
                )}
              </p>
            </div>
          )}
          {draft.writing_mode !== "assisted" && (
            <p className="email-shared-context-label">
              {t("Personalization & AI settings", "个性化与 AI 设置")}
            </p>
          )}
          <div className="form-grid">
            <Field label={t("To · Contact", "收件人 · 联系人")}>
              <select
                value={draft.contact_id || ""}
                disabled={!!replyMessageId || contextLocked}
                onChange={(e) =>
                  edit({ contact_id: e.target.value || null, evidence_ids: [] })
                }
              >
                <option value="">
                  {t(
                    "No contact · independent draft",
                    "不绑定联系人 · 独立草稿",
                  )}
                </option>
                {allContacts.map((c) => (
                  <option value={c.id} key={c.id}>
                    {c.name} · {c.company}
                  </option>
                ))}
              </select>
            </Field>
            <Field
              label={t("Writing context · Persona", "写作背景 · 职业画像")}
            >
              <select
                value={draft.persona_id || ""}
                disabled={contextLocked}
                onChange={(e) => edit({ persona_id: e.target.value || null })}
              >
                <option value="">
                  {t("No persona · use the brief", "不绑定画像 · 使用写作要求")}
                </option>
                {personas.map((p) => (
                  <option value={p.id} key={p.id}>
                    {p.label} · v{p.version}
                  </option>
                ))}
              </select>
            </Field>
            {(draft.writing_mode || "assisted") === "assisted" && (
              <Field label={t("Writing starting point", "写作场景")}>
                <select
                  value={draft.starting_point}
                  onChange={(e) => edit({ starting_point: e.target.value })}
                >
                  <option>Networking</option>
                  <option>Informational Interview</option>
                  <option>Recruiting</option>
                  <option>Follow-up</option>
                  <option>Introduction</option>
                </select>
              </Field>
            )}
            <Field label={t("Email language", "邮件语言")}>
              <select
                aria-label="Email language"
                value={draft.language}
                onChange={(e) =>
                  edit({ language: e.target.value as "en" | "zh" })
                }
              >
                <option value="en">English</option>
                <option value="zh">简体中文</option>
              </select>
            </Field>
            {(draft.writing_mode || "assisted") === "assisted" && (
              <Field
                label={t(
                  "What would you like to connect about?",
                  "您希望就什么目的联系？",
                )}
                className="full"
              >
                <textarea
                  rows={3}
                  maxLength={4000}
                  value={draft.purpose}
                  onChange={(e) => edit({ purpose: e.target.value })}
                  placeholder={t(
                    "Describe your background, what you offer or want to learn, and why this conversation matters.",
                    "说明您的背景、可提供的价值或希望了解的问题，以及联系的原因。 ",
                  )}
                />
              </Field>
            )}
            {(draft.writing_mode || "assisted") === "assisted" && (
              <Field
                label={t("Call to action", "期望对方采取的行动")}
                className="full"
              >
                <input
                  maxLength={2000}
                  value={draft.cta || ""}
                  onChange={(e) => edit({ cta: e.target.value })}
                  placeholder={t(
                    "e.g. A 15-minute conversation next week",
                    "例如：下周安排 15 分钟交流",
                  )}
                />
              </Field>
            )}
            <Field label={t("Writing tone", "写作语气")}>
              <select
                aria-label="Writing tone"
                value={draft.tone}
                onChange={(e) => edit({ tone: e.target.value })}
              >
                <option value="professional">
                  {t("Professional", "专业")}
                </option>
                <option value="warm">{t("Warm", "友好")}</option>
                <option value="concise">{t("Concise", "简洁")}</option>
              </select>
            </Field>
            <Field label={t("Email length", "邮件长度")}>
              <select
                value={draft.length || "medium"}
                onChange={(e) =>
                  edit({ length: e.target.value as Draft["length"] })
                }
              >
                <option value="short">{t("Short", "短")}</option>
                <option value="medium">{t("Medium", "中")}</option>
                <option value="long">{t("Long", "长")}</option>
              </select>
            </Field>
            <Field label={t("AI model", "AI 模型")} className="full">
              <select
                value={draft.model || ""}
                onChange={(e) => edit({ model: e.target.value })}
                disabled={!models}
              >
                <option value="">
                  {t("Workspace default", "工作区默认")}
                  {models?.default_model ? " · " + models.default_model : ""}
                </option>
                {draft.model &&
                  !modelOptions.some((m) => m.id === draft.model) && (
                    <option value={draft.model}>
                      {draft.model} · {t("unavailable", "不可用")}
                    </option>
                  )}
                {modelGroups.map((group) => (
                  <optgroup label={group} key={group}>
                    {modelOptions
                      .filter(
                        (m) =>
                          (m.provider_label || models?.provider || "AI") ===
                          group,
                      )
                      .map((m) => (
                        <option
                          value={m.id}
                          key={m.id}
                          disabled={m.available === false}
                        >
                          {m.label}
                          {m.available === false
                            ? " · " + t("Not configured", "未配置")
                            : ""}
                        </option>
                      ))}
                  </optgroup>
                ))}
              </select>
            </Field>
            {draft.writing_mode !== "prompt" && (
              <Field
                label={t("Additional instructions", "补充要求")}
                className="full"
              >
                <textarea
                  rows={2}
                  maxLength={6000}
                  value={draft.custom_instructions || ""}
                  onChange={(e) =>
                    edit({ custom_instructions: e.target.value })
                  }
                  placeholder={t(
                    "e.g. Avoid clichés. Refer to a shared school only when supported by evidence.",
                    "例如：避免套话，仅在证据支持时提及共同学校。 ",
                  )}
                />
              </Field>
            )}
          </div>
          <details
            className="writing-evidence"
            open={!!recipient?.sources.length}
          >
            <summary>
              {t("Personalization evidence", "个性化证据")}{" "}
              <Badge>{(draft.evidence_ids || []).length}</Badge>
            </summary>
            <p>
              {t(
                "Select sources the AI may cite, alongside the linked contact’s basic fields and your persona. Sources can be incomplete; verify every claim.",
                "选择允许 AI 使用的来源，同时参考所绑定联系人的基础字段及您的画像。来源可能不完整，请逐项核对事实。 ",
              )}
            </p>
            {recipient?.sources.length ? (
              recipient.sources.map((source) => (
                <div className="writing-evidence-row" key={source.id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={(draft.evidence_ids || []).includes(source.id)}
                      onChange={(e) =>
                        edit({
                          evidence_ids: e.target.checked
                            ? [...(draft.evidence_ids || []), source.id]
                            : (draft.evidence_ids || []).filter(
                                (value) => value !== source.id,
                              ),
                        })
                      }
                    />
                    <span>
                      <strong>{source.title || source.provider}</strong>
                      <small>
                        {source.provider} ·{" "}
                        <DateLabel value={source.retrieved_at} />
                      </small>
                      <p>
                        {source.snippet ||
                          t("No source excerpt available.", "暂无来源摘要。")}
                      </p>
                    </span>
                  </label>
                  {/^(https?:)\/\//i.test(source.url) && (
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label={t("Open evidence source", "打开证据来源")}
                    >
                      <ExternalLink size={14} />
                    </a>
                  )}
                </div>
              ))
            ) : (
              <p>
                {t(
                  "Link a contact with sources to select evidence. You can generate from your brief alone.",
                  "绑定带有来源的联系人后可选择证据。也可只根据写作要求生成。",
                )}
              </p>
            )}
          </details>
          {modelError && (
            <div className="notice small" role="alert">
              {modelError}
              <button
                className="text-button"
                onClick={() => setJobsVersion((v) => v + 1)}
              >
                {t("Retry models", "重试模型列表")}
              </button>
            </div>
          )}
          {models?.mode === "mock" && (
            <div className="notice small">
              {t(
                "Demo mode: all model choices use simulated output.",
                "模拟模式：所有模型选项均使用模拟输出。",
              )}
            </div>
          )}
          {models && !selectedModelAvailable && (
            <div className="notice small">
              {t(
                "The selected model is unavailable or missing its provider API key. Choose a configured model. Your draft and brief can still be saved.",
                "所选模型不可用或尚未配置对应厂商的 API Key，请选择已配置的模型。草稿和写作要求仍可保存。",
              )}
            </div>
          )}
          <div className="generate-row">
            <span>
              {t(
                "Saved with this draft. Contacts and personas are optional and can be changed at any time.",
                "随草稿保存。联系人和画像均可选，可随时更换。",
              )}
            </span>
            <button
              className="button primary"
              disabled={!canGenerate}
              onClick={() => void generate()}
            >
              {busy || pending ? <Busy /> : <Sparkles size={16} />}
              {pending
                ? t("Generating…", "生成中…")
                : t("Generate email", "生成邮件")}
            </button>
          </div>
        </fieldset>
      </div>
      {recovered && (
        <div className="notice writing-recovery" role="status">
          {t(
            "Unsaved work recovered from this tab. Review it and save to the server.",
            "已恢复此标签页中未保存的内容，请检查后保存至服务端。",
          )}
        </div>
      )}
      {error && (
        <div className="error-panel" role="alert">
          {error}
          <button
            className="button small-button"
            disabled={busy}
            onClick={() => void save()}
          >
            {t("Retry save", "重试保存")}
          </button>
          <button
            className="button small-button"
            disabled={busy}
            onClick={() => void reloadDraft()}
          >
            {t(
              "Load latest (discard local edits)",
              "加载最新版本（放弃本地修改）",
            )}
          </button>
        </div>
      )}
      <section
        className="panel writing-suggestions"
        aria-label={t("AI suggestions", "AI 建议")}
      >
        <div className="section-head">
          <h2>
            <Sparkles size={17} />
            {t("AI suggestions", "AI 建议")}
          </h2>
          <button
            className="text-button"
            onClick={() => setJobsVersion((v) => v + 1)}
            aria-label={t("Refresh suggestions", "刷新建议")}
          >
            <RefreshCw size={15} />
          </button>
        </div>
        {jobsError && (
          <div className="notice" role="alert">
            {t("Suggestions could not be refreshed: ", "暂时无法刷新建议：")}
            {jobsError}
          </div>
        )}
        {!visibleJobs.length && (
          <p className="writing-empty">
            {t(
              "Generate a suggestion, review it here, then insert it into your email. Your current text stays editable.",
              "生成的建议会先在此预览，审核后再插入邮件。当前正文可继续编辑。",
            )}
          </p>
        )}
        {visibleJobs.map((job) => {
          const stale =
            job.draft_revision !== draft.revision || saveState !== "saved";
          const working = job.status === "queued" || job.status === "running";
          return (
            <article
              className="writing-suggestion"
              key={job.id}
              data-testid="writing-suggestion"
              data-status={job.status}
            >
              <div className="writing-suggestion-meta">
                <Badge tone={job.status === "failed" ? "amber" : "gray"}>
                  {working
                    ? t("IN PROGRESS", "生成中")
                    : job.status === "succeeded"
                      ? t("READY TO REVIEW", "待审核")
                      : job.status === "accepted"
                        ? t("INSERTED", "已插入")
                        : job.status === "discarded"
                          ? t("DISCARDED", "已放弃")
                          : t("FAILED", "失败")}
                </Badge>
                <span>
                  {job.model} · {t("Revision", "版本")} {job.draft_revision} ·{" "}
                  <DateLabel value={job.created_at} />
                </span>
              </div>
              {working && (
                <p className="writing-pending">
                  <Busy />
                  {t(
                    "Working in the background. You can leave this page and return to this draft later.",
                    "正在后台生成，可离开页面，稍后返回此草稿查看。",
                  )}
                </p>
              )}
              {job.status === "failed" && (
                <p className="writing-job-error">
                  {job.error ||
                    t(
                      "Generation failed. Review the brief and retry.",
                      "生成失败，请检查写作要求后重试。",
                    )}
                </p>
              )}
              {job.result && (
                <div className="writing-result">
                  <h3>{job.result.subject}</h3>
                  <div
                    dangerouslySetInnerHTML={{ __html: job.result.body_html }}
                  />
                </div>
              )}
              {job.status === "succeeded" && stale && (
                <p className="writing-stale">
                  {t(
                    "This draft changed after generation started. Generate a new suggestion to use the latest version; this result will not overwrite your edits.",
                    "开始生成后草稿已变更，请基于最新版本重新生成。此建议不会覆盖您的修改。",
                  )}
                </p>
              )}
              {(job.status === "succeeded" || job.status === "failed") && (
                <div className="writing-suggestion-actions">
                  {job.status === "succeeded" && (
                    <>
                      <button
                        className="button primary"
                        disabled={busy || stale}
                        onClick={() => void useSuggestion(job)}
                      >
                        <Check size={15} />
                        {t("Insert suggestion", "插入建议")}
                      </button>
                      <button
                        className="button"
                        disabled={busy || !job.result}
                        onClick={() =>
                          job.result &&
                          void navigator.clipboard
                            .writeText(
                              `Subject: ${job.result.subject}\n\n${new DOMParser().parseFromString(job.result.body_html.replace(/<br\s*\/?>/gi, "\n").replace(/<\/(p|div|li|h[1-6])>/gi, "</$1>\n\n"), "text/html").body.textContent?.trim() || ""}`,
                            )
                            .then(() =>
                              notify(t("Suggestion copied.", "建议已复制。")),
                            )
                            .catch((e) => setError(errorText(e)))
                        }
                      >
                        <Copy size={15} />
                        {t("Copy suggestion", "复制建议")}
                      </button>
                    </>
                  )}
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() => void discardSuggestion(job)}
                  >
                    <X size={15} />
                    {t("Discard", "放弃")}
                  </button>
                  {(stale || job.status === "failed") && (
                    <button
                      className="text-button"
                      disabled={!canGenerate}
                      onClick={() => void generate(job.action)}
                    >
                      <RefreshCw size={15} />
                      {t(
                        "Regenerate from current draft",
                        "基于当前草稿重新生成",
                      )}
                    </button>
                  )}
                </div>
              )}
            </article>
          );
        })}
        {jobs.some(
          (j) => j.status === "accepted" || j.status === "discarded",
        ) && (
          <button
            className="text-button writing-history"
            onClick={() => setShowHistory(!showHistory)}
          >
            {showHistory
              ? t("Hide history", "隐藏历史")
              : t("Show suggestion history", "查看建议历史")}
          </button>
        )}
      </section>
      <div className="panel composer">
        <div className="composer-head">
          <span>
            <FileText size={16} />
            {t("Your email", "邮件内容")}
          </span>
          <span
            className={`save-status ${saveState === "error" ? "bad" : ""}`}
            role="status"
          >
            {saveState === "saved" ? (
              <Check size={14} />
            ) : saveState === "saving" ? (
              <Busy />
            ) : (
              <span className="status-dot" />
            )}
            {saveState === "saved"
              ? t("All changes saved", "所有修改已保存")
              : saveState === "saving"
                ? t("Saving…", "保存中…")
                : saveState === "error"
                  ? t("Save failed", "保存失败")
                  : t("Unsaved changes", "尚未保存")}
          </span>
        </div>
        <div className="subject-line">
          <label htmlFor="subject">{t("Subject", "主题")}</label>
          <input
            id="subject"
            value={replySubject === undefined ? draft.subject : replySubject}
            placeholder={t("A subject worth opening", "输入邮件主题")}
            disabled={busy || replySubject !== undefined}
            onChange={(e) => edit({ subject: e.target.value })}
          />
        </div>
        {replySubject !== undefined && (
          <p className="email-reply-subject-note">
            {t(
              replyMessageId
                ? "The reply keeps the original Gmail conversation's subject and saved contact as its recipient."
                : "Reply step: the subject follows the earlier email in this thread. Change it on the step that starts this thread.",
              replyMessageId
                ? "回复保留原 Gmail 会话的主题，收件人仅为原已保存联系人。"
                : "回复步骤的主题继承此会话中的上一封邮件，请在开启此会话的步骤中修改。",
            )}
          </p>
        )}
        <RichEditor
          value={draft.body_html}
          disabled={busy}
          onChange={(body_html) => edit({ body_html })}
        />
        <div className="refine-bar">
          <button
            className="text-button"
            disabled={!canGenerate || !draft.body_html}
            onClick={() => void generate("shorten")}
          >
            <Scissors size={15} />
            {t("Shorten", "缩短")}
          </button>
          <button
            className="text-button"
            disabled={!canGenerate || !draft.body_html}
            onClick={() => void generate("tone")}
          >
            <SlidersHorizontal size={15} />
            {t("Rewrite with brief", "按写作要求改写")}
          </button>
          <button
            className="text-button variables-toggle"
            onClick={() => setShowVariables(!showVariables)}
          >
            <Braces size={15} />
            {t("Variables", "变量")}
          </button>
        </div>
        {showVariables && (
          <div className="variable-help">
            <p>
              {t(
                "Type or paste these variables into the subject or body. School refers to the contact’s school. Preview resolves them using saved records.",
                "在主题或正文中输入以下变量。学校指联系人学校。预览使用已保存数据替换。",
              )}
            </p>
            <div>
              {["name", "company", "title", "school", "sender_name"].map(
                (v) => (
                  <code key={v}>{"{{" + v + "}}"}</code>
                ),
              )}
            </div>
          </div>
        )}
        <div className="composer-footer">
          <span>
            <Badge tone={draft.status === "ready" ? "green" : "gray"}>
              {draft.status === "ready"
                ? t("Reviewed", "已审核")
                : t("Draft", "草稿")}
            </Badge>
          </span>
          <div>
            <button
              className="button"
              disabled={busy}
              onClick={() => void save()}
            >
              <Save size={15} />
              {t("Save draft", "保存草稿")}
            </button>
            <button
              className="button dark"
              disabled={busy}
              onClick={() => void showPreview()}
            >
              <Eye size={16} />
              {t("Preview & copy", "预览与复制")}
            </button>
          </div>
        </div>
      </div>
      {!hideDelivery &&
        ((!loadPreview && replySubject === undefined) || !!replyMessageId) && (
          <SendDraft
            draft={draft}
            flush={flush}
            accept={accept}
            disabled={busy}
            replyMessageId={replyMessageId}
            mailboxId={mailboxId}
            onSent={onSent}
          />
        )}
      <div className="studio-footnote">
        <Check size={14} />
        {t(
          "Drafts, briefs, and suggestions are saved to this workspace. Preview and copy when ready.",
          "草稿、写作要求与建议均保存至当前工作区，完成后可预览与复制。",
        )}
      </div>
      {preview && (
        <Drawer
          title={t("Final preview", "最终预览")}
          onClose={() => setPreview(null)}
        >
          <div className="preview-content">
            <div className="preview-label">
              <Badge tone="green">
                {t("RESOLVED PREVIEW", "真实数据预览")}
              </Badge>
              <span>{draft.language === "en" ? "English" : "简体中文"}</span>
            </div>
            {preview.missing_variables.length > 0 && (
              <div className="error-panel" role="alert">
                <strong>{t("Missing variables", "缺失变量")}</strong>
                <p>{preview.missing_variables.join(", ")}</p>
                <p>
                  {t(
                    "Complete the contact or persona before marking ready.",
                    "请先补齐联系人或画像字段，再标记为可用。",
                  )}
                </p>
              </div>
            )}
            {preview.persona_changed && (
              <div className="notice">
                {t(
                  "This persona changed. Review the new background and save the draft again.",
                  "画像已更新，请检查新背景并重新保存草稿。",
                )}
              </div>
            )}
            <div className="preview-recipient">
              <span>{t("To", "收件人")}</span>
              <strong>
                {preview.variables.name ||
                  t("No recipient selected", "尚未选择收件人")}
              </strong>
              <small>
                {preview.recipient_email ||
                  t("No email address · draft only", "暂无邮箱 · 可保存草稿")}
              </small>
            </div>
            <h2>{preview.subject || t("No subject", "暂无主题")}</h2>
            <div
              className="preview-body"
              dangerouslySetInnerHTML={{ __html: preview.body_html }}
            />
            <div className="copy-actions">
              <button
                className="button"
                onClick={() => void copy("subject", preview)}
              >
                <Copy size={15} />
                {t("Copy subject", "复制主题")}
              </button>
              <button
                className="button"
                onClick={() => void copy("body", preview)}
              >
                <Copy size={15} />
                {t("Copy body", "复制正文")}
              </button>
              {replySubject === undefined && (
                <a
                  className="button"
                  href={
                    preview.can_mark_ready && preview.recipient_email
                      ? `/api/drafts/${id}/export.eml`
                      : undefined
                  }
                  aria-disabled={
                    !preview.can_mark_ready || !preview.recipient_email || busy
                  }
                  onClick={(event) => {
                    event.preventDefault();
                    if (
                      !preview.can_mark_ready ||
                      !preview.recipient_email ||
                      busy
                    )
                      return;
                    void flush()
                      .then(() => {
                        window.location.assign(`/api/drafts/${id}/export.eml`);
                      })
                      .catch((e) => setError(errorText(e)));
                  }}
                >
                  <Download size={15} />
                  {t("Download email (.eml)", "下载邮件（.eml）")}
                </a>
              )}
              <button
                className="button dark"
                onClick={() => void copy("both", preview)}
              >
                <Copy size={15} />
                {t("Copy all", "复制全部")}
              </button>
            </div>
            <div className="ready-section">
              {replySubject === undefined && (
                <button
                  className="button primary"
                  disabled={!preview.can_mark_ready || busy}
                  onClick={() => void ready()}
                >
                  <Check size={16} />
                  {t("Mark as reviewed & ready", "标记已审核且可用")}
                </button>
              )}
              <p>
                {replySubject !== undefined
                  ? t(
                      "Review this reply with the full sequence in Preview & review. Copy uses the inherited subject shown here.",
                      "请在序列的预览与审核中审核此回复。复制内容使用此处显示的继承主题。",
                    )
                  : t(
                      "Requires a recipient, subject, body and resolved variables. This marks the content only; no email is sent.",
                      "需选择收件人并补齐主题、正文和变量。这只标记内容状态，不会发送邮件。",
                    )}
              </p>
            </div>
          </div>
        </Drawer>
      )}
    </section>
  );
}
