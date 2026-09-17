"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Plus,
  GitBranch,
  Sparkles,
  Layers,
  FileText,
  Mail,
  Clock3,
  ArrowDown,
  ArrowUp,
  Trash2,
  Settings2,
  Eye,
  Users,
  Check,
  Download,
  Upload,
  Save,
  ArrowLeft,
  ChevronRight,
} from "lucide-react";
import { useApp } from "@/lib/context";
import { api, post, put, errorText } from "@/lib/api";
import type {
  Sequence,
  SequenceStep,
  SequenceTemplate,
  SequencePreview,
  SequenceJob,
} from "@/lib/sequence-types";
import type { WritingModels } from "@/lib/types";
import { Heading, Badge, Busy, Field, Drawer, Nav, DateLabel } from "./ui";
import { DraftEditor } from "./email-studio";
import "./sequences.css";

function downloadTemplate(template: SequenceTemplate) {
  const { schema_version, name, description, steps } = template;
  const url = URL.createObjectURL(
    new Blob(
      [JSON.stringify({ schema_version, name, description, steps }, null, 2)],
      { type: "application/json" },
    ),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name.replace(/[^a-z0-9\u4e00-\u9fff_-]/gi, "-") + ".json";
  link.click();
  URL.revokeObjectURL(url);
}

export default function Sequences() {
  const { t, go, notify, guard, refresh } = useApp();
  const id = useSearchParams().get("sequence");
  const [items, setItems] = useState<Sequence[]>([]);
  const [templates, setTemplates] = useState<SequenceTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [library, setLibrary] = useState(false);
  async function load() {
    try {
      const [sequences, saved] = await Promise.all([
        api<Sequence[]>("/sequences"),
        api<SequenceTemplate[]>("/sequence-templates"),
      ]);
      setItems(sequences);
      setTemplates(saved);
      setError("");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, [id]);
  return (
    <div className="sequences-page">
      <Heading
        title={t("Sequences", "邮件序列")}
        detail={t(
          "Shape a conversation, one thoughtful step at a time.",
          "逐步编排邮件，让每一次联系都有清晰的节奏。",
        )}
      >
        <button className="button" onClick={() => setLibrary(true)}>
          <Layers size={16} />
          {t("Step templates", "步骤模板")}
        </button>
        <button
          className="button primary"
          onClick={async () => {
            try {
              if (guard.current) await guard.current();
              setCreating(true);
            } catch (e) {
              notify(errorText(e));
            }
          }}
        >
          <Plus size={16} />
          {t("New sequence", "新建序列")}
        </button>
      </Heading>
      {error && (
        <div className="error-panel" role="alert">
          {error}
          <button className="button" onClick={() => void load()}>
            {t("Retry", "重试")}
          </button>
        </div>
      )}
      {id ? (
        <SequenceDetail
          key={id}
          id={id}
          templates={templates}
          onChange={load}
        />
      ) : loading ? (
        <div className="panel sequence-loading">
          <Busy />
          {t("Loading sequences…", "正在加载序列…")}
        </div>
      ) : (
        <>
          <div className="sequence-intro panel">
            <div className="sequence-symbol">
              <GitBranch size={27} />
            </div>
            <div>
              <h2>
                {t(
                  "A clear path from hello to follow-up",
                  "从初次联系到后续跟进",
                )}
              </h2>
              <p>
                {t(
                  "Start with AI, reuse a step template, or bring in emails from your draft box. Every step has its own writing workspace.",
                  "使用 AI 规划、复用步骤模板，或从草稿箱选择邮件。每一步都有独立的写作空间。",
                )}
              </p>
            </div>
            <Badge tone="blue">{t("Planning & review", "编排与审核")}</Badge>
          </div>
          <div className="sequence-grid">
            {items.map((s) => (
              <Nav
                key={s.id}
                href={"/sequences?sequence=" + s.id}
                className="panel sequence-tile"
              >
                <div className="sequence-tile-top">
                  <GitBranch size={20} />
                  <Badge tone={s.status === "ready" ? "green" : "gray"}>
                    {s.status === "ready"
                      ? t("Reviewed", "已审核")
                      : t("Draft", "草稿")}
                  </Badge>
                </div>
                <h2>{s.name}</h2>
                <p>
                  {s.description ||
                    t(
                      "An email conversation in progress.",
                      "正在编排的邮件对话。",
                    )}
                </p>
                <div className="sequence-tile-bottom">
                  <span>
                    {s.step_count ?? s.steps?.length ?? 0}{" "}
                    {t("steps", "个步骤")}
                  </span>
                  <DateLabel value={s.updated_at} />
                  <ChevronRight size={16} />
                </div>
              </Nav>
            ))}
          </div>
          {!items.length && (
            <div className="panel sequence-empty">
              <GitBranch size={34} />
              <h2>{t("Build your first sequence", "创建第一个邮件序列")}</h2>
              <p>
                {t(
                  "Your drafts and reusable templates are ready to become a connected workflow.",
                  "将草稿和可复用模板组织为连续的邮件流程。",
                )}
              </p>
              <button
                className="button primary"
                onClick={() => setCreating(true)}
              >
                <Plus size={16} />
                {t("Create a sequence", "创建序列")}
              </button>
            </div>
          )}
        </>
      )}
      {creating && (
        <CreateSequence
          templates={templates}
          onClose={() => setCreating(false)}
          onCreated={async (s) => {
            setCreating(false);
            await refresh();
            await load();
            await go("/sequences?sequence=" + s.id);
          }}
        />
      )}
      {library && (
        <TemplateLibrary
          templates={templates}
          onClose={() => setLibrary(false)}
          onChange={load}
          onUse={() => {
            setLibrary(false);
            setCreating(true);
          }}
        />
      )}
    </div>
  );
}

function ModelSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useApp();
  const [models, setModels] = useState<WritingModels | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<WritingModels>("/ai/models")
      .then((m) => {
        if (active) setModels(m);
      })
      .catch((e) => {
        if (active) setError(errorText(e));
      });
    return () => {
      active = false;
    };
  }, []);
  return (
    <Field label={t("Planning AI model", "步骤规划 AI 模型")}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={!models}
      >
        <option value="">
          {error || t("Workspace default", "工作区默认")}
          {models ? " · " + models.default_model : ""}
        </option>
        {models?.models.map((m) => (
          <option key={m.id} value={m.id} disabled={m.available === false}>
            {m.provider_label ? m.provider_label + " · " : ""}
            {m.label}
            {m.available === false ? t(" · Not configured", " · 未配置") : ""}
          </option>
        ))}
      </select>
    </Field>
  );
}

function CreateSequence({
  templates,
  onClose,
  onCreated,
}: {
  templates: SequenceTemplate[];
  onClose: () => void;
  onCreated: (s: Sequence) => Promise<void>;
}) {
  const { t, config } = useApp();
  const [mode, setMode] = useState("template");
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("en");
  const [templateId, setTemplateId] = useState(templates[0]?.id || "");
  const [selected, setSelected] = useState<string[]>([]);
  const [prompt, setPrompt] = useState("");
  const [count, setCount] = useState(3);
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<Sequence | null>(null);
  async function create() {
    setBusy(true);
    setError("");
    try {
      const s =
        created ||
        (await post<Sequence>("/sequences", {
          name,
          language,
          description: mode === "ai" ? prompt : "",
          ...(mode === "template" ? { template_id: templateId } : {}),
          ...(mode === "drafts" ? { draft_ids: selected } : {}),
        }));
      setCreated(s);
      if (mode === "ai")
        await post("/sequences/" + s.id + "/ai-plan", {
          revision: s.revision,
          prompt,
          step_count: count,
          model,
          language,
        });
      await onCreated(s);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Drawer
      title={t("Create a sequence", "创建邮件序列")}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <div className="sequence-form">
        <div className="sequence-section-label">
          01 · {t("Choose your starting point", "选择创建方式")}
        </div>
        <div className="sequence-source-options">
          {[
            ["ai", t("Plan with AI", "AI 规划"), Sparkles],
            ["template", t("Step template", "步骤模板"), Layers],
            ["drafts", t("From drafts", "从草稿箱选择"), FileText],
            ["blank", t("From scratch", "从空白开始"), Plus],
          ].map(([key, label, Icon]) => {
            const I = Icon as typeof Plus;
            return (
              <button
                key={String(key)}
                className={mode === key ? "selected" : ""}
                aria-pressed={mode === key}
                disabled={busy || !!created}
                onClick={() => setMode(String(key))}
              >
                <I size={19} />
                {String(label)}
              </button>
            );
          })}
        </div>
        <fieldset disabled={busy || !!created}>
          <Field label={t("Sequence name", "序列名称")}>
            <input
              maxLength={150}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t(
                "e.g. Finance networking · autumn",
                "例如：秋季金融人脉拓展",
              )}
            />
          </Field>
          <Field label={t("Sequence language", "序列语言")}>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="en">English</option>
              <option value="zh">简体中文</option>
            </select>
          </Field>
        </fieldset>
        {mode === "template" && (
          <div className="sequence-template-picker">
            {templates.map((item) => (
              <button
                disabled={busy || !!created}
                key={item.id}
                className={item.id === templateId ? "selected" : ""}
                onClick={() => setTemplateId(item.id)}
                aria-pressed={item.id === templateId}
              >
                <span>
                  <b>{item.name}</b>
                  <small>
                    {item.is_default
                      ? t("Default", "默认")
                      : t("Your template", "自定义模板")}{" "}
                    · {item.steps.length} {t("steps", "步")}
                  </small>
                </span>
                <p>{item.description}</p>
                <div className="sequence-mini-flow">
                  {item.steps.map((s, i) => (
                    <span key={i}>
                      {i > 0 && <ArrowDown size={12} />}
                      {s.delay_days ? `+${s.delay_days}d · ` : ""}
                      {s.title}
                    </span>
                  ))}
                </div>
              </button>
            ))}
          </div>
        )}
        {mode === "ai" && (
          <>
            <Field
              label={t(
                "What should this sequence achieve?",
                "这个序列希望达成什么目标？",
              )}
            >
              <textarea
                rows={5}
                maxLength={4000}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                disabled={busy}
                placeholder={t(
                  "Introduce myself to an investment banking professional, ask for a short conversation, then follow up twice over two weeks. Keep it warm and low-pressure.",
                  "向投行从业者介绍自己，邀请简短交流，两周内跟进两次。语气友好，不给对方压力。",
                )}
              />
            </Field>
            <div className="form-grid">
              <Field label={t("Number of steps", "步骤数量")}>
                <input
                  type="number"
                  min={1}
                  max={8}
                  value={count}
                  onChange={(e) => setCount(Number(e.target.value))}
                />
              </Field>
              <ModelSelect value={model} onChange={setModel} />
            </div>
            <p className="sequence-note">
              {config?.ai_mode === "mock"
                ? t(
                    "Mock AI: a deterministic sample plan will be clearly labeled.",
                    "模拟 AI：将生成明确标注的规则演示计划。",
                  )
                : t(
                    "AI will generate each step in the background. You can edit the completed plan before review.",
                    "AI 将在后台逐步生成。完成后可编辑计划并预览审核。",
                  )}
            </p>
          </>
        )}
        {mode === "drafts" && (
          <DraftPicker selected={selected} setSelected={setSelected} />
        )}
        {mode === "blank" && (
          <p className="sequence-note">
            {t(
              "Open a blank workflow, then add email steps and set their timing.",
              "打开空白流程，逐步添加邮件并设置时间间隔。",
            )}
          </p>
        )}
        {error && (
          <div className="error-panel" role="alert">
            {error}
            {created && (
              <p>
                {t(
                  "The sequence was saved. Retry AI planning or open it to continue manually.",
                  "序列已保存。可以重试 AI 规划或打开序列手动继续。",
                )}
              </p>
            )}
          </div>
        )}
        <div className="sequence-dialog-actions">
          {created && (
            <button
              className="button"
              disabled={busy}
              onClick={() => void onCreated(created)}
            >
              {t("Open saved sequence", "打开已保存序列")}
            </button>
          )}
          <button
            className="button primary"
            disabled={
              busy ||
              !name.trim() ||
              (mode === "template" && !templateId) ||
              (mode === "drafts" && !selected.length) ||
              (mode === "ai" && (!prompt.trim() || count < 1 || count > 8))
            }
            onClick={() => void create()}
          >
            {busy ? (
              <Busy />
            ) : mode === "ai" ? (
              <Sparkles size={16} />
            ) : (
              <Plus size={16} />
            )}
            {created
              ? t("Retry AI planning", "重试 AI 规划")
              : mode === "ai"
                ? t("Create & generate steps", "创建并生成步骤")
                : t("Create sequence", "创建序列")}
          </button>
        </div>
      </div>
    </Drawer>
  );
}

function DraftPicker({
  selected,
  setSelected,
  single = false,
}: {
  selected: string[];
  setSelected: (ids: string[]) => void;
  single?: boolean;
}) {
  const { t, drafts } = useApp();
  const [search, setSearch] = useState("");
  return (
    <div className="sequence-draft-picker">
      <Field label={t("Search draft emails", "搜索草稿邮件")}>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("Search by subject or purpose", "搜索主题或用途")}
        />
      </Field>
      <p className="sequence-note">
        {t(
          "Emails are copied into this sequence. Select them in the order you want to use them.",
          "邮件会复制到序列中。请按期望的步骤顺序选择。",
        )}
      </p>
      {drafts
        .filter((d) =>
          (d.subject + " " + d.purpose)
            .toLowerCase()
            .includes(search.toLowerCase()),
        )
        .map((d) => (
          <label
            key={d.id}
            className={selected.includes(d.id) ? "selected" : ""}
          >
            <input
              type={single ? "radio" : "checkbox"}
              checked={selected.includes(d.id)}
              onChange={() =>
                setSelected(
                  single
                    ? [d.id]
                    : selected.includes(d.id)
                      ? selected.filter((x) => x !== d.id)
                      : [...selected, d.id],
                )
              }
            />
            <span>
              <b>{d.subject || t("Untitled draft", "未命名草稿")}</b>
              <small>{d.purpose || d.writing_mode}</small>
            </span>
            {selected.includes(d.id) && (
              <Badge>{selected.indexOf(d.id) + 1}</Badge>
            )}
          </label>
        ))}
      {!drafts.length && (
        <p>
          {t(
            "Create an email in Email Studio first, or start with a template.",
            "请先在邮件工作室创建草稿，或使用模板开始。",
          )}
        </p>
      )}
    </div>
  );
}

function SequenceDetail({
  id,
  templates,
  onChange,
}: {
  id: string;
  templates: SequenceTemplate[];
  onChange: () => Promise<void>;
}) {
  const { t, guard, refresh, notify } = useApp();
  const [sequence, setSequence] = useState<Sequence | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState("steps");
  const [selected, setSelected] = useState<string | null>(null);
  const [stepEdit, setStepEdit] = useState<SequenceStep | "new" | null>(null);
  const [plan, setPlan] = useState(false);
  const [savingTemplate, setSavingTemplate] = useState(false);
  const [rename, setRename] = useState(false);
  const [preview, setPreview] = useState<SequencePreview | null>(null);
  const [job, setJob] = useState<SequenceJob | null>(null);
  async function load() {
    const s = await api<Sequence>("/sequences/" + id);
    setSequence(s);
    setJob(s.generation);
    return s;
  }
  useEffect(() => {
    let active = true;
    api<Sequence>("/sequences/" + id)
      .then((s) => {
        if (active) {
          setSequence(s);
          setJob(s.generation);
        }
      })
      .catch((e) => {
        if (active) setError(errorText(e));
      });
    return () => {
      active = false;
    };
  }, [id]);
  const running = job?.status === "queued" || job?.status === "running";
  useEffect(() => {
    if (!running || !job) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await api<SequenceJob>(
          "/sequences/" + id + "/jobs/" + job!.id,
        );
        if (cancelled) return;
        setJob(next);
        if (next.status === "queued" || next.status === "running")
          timer = setTimeout(() => void poll(), 1400);
        else {
          await load();
          await refresh();
          await onChange();
        }
      } catch (e) {
        if (!cancelled) {
          setError(errorText(e));
          timer = setTimeout(() => void poll(), 4000);
        }
      }
    }
    timer = setTimeout(() => void poll(), 500);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id, job?.id, running]);
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      if (guard.current) await guard.current();
      await fn();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function update(values: object) {
    if (!sequence) return;
    const s = await put<Sequence>("/sequences/" + id, {
      revision: sequence.revision,
      ...values,
    });
    setSequence(s);
    setPreview(null);
    await refresh();
    await onChange();
  }
  function stepPayload(s: SequenceStep) {
    return {
      id: s.id,
      draft_id: s.draft_id,
      title: s.title,
      purpose: s.purpose,
      delay_days: s.delay_days,
      thread_mode: s.thread_mode,
    };
  }
  async function reorder(index: number, change: number) {
    if (!sequence) return;
    const steps = sequence.steps.map(stepPayload);
    [steps[index], steps[index + change]] = [
      steps[index + change],
      steps[index],
    ];
    steps[0].thread_mode = "new_thread";
    steps[0].delay_days = 0;
    await update({ steps, status: "draft" });
  }
  async function chooseTab(next: string) {
    await action(async () => {
      await load();
      if (next === "review")
        setPreview(await api<SequencePreview>("/sequences/" + id + "/preview"));
      setTab(next);
      setSelected(null);
    });
  }
  if (!sequence)
    return error ? (
      <div className="error-panel" role="alert">
        {error}
        <button
          className="button"
          onClick={() =>
            void action(async () => {
              await load();
            })
          }
        >
          {t("Retry", "重试")}
        </button>
      </div>
    ) : (
      <div className="sequence-loading">
        <Busy />
        {t("Opening sequence…", "正在打开序列…")}
      </div>
    );
  let cumulative = 0;
  let threadSubject = "";
  return (
    <>
      <Nav href="/sequences" className="sequence-back">
        <ArrowLeft size={15} />
        {t("All sequences", "所有序列")}
      </Nav>
      <section className="panel sequence-detail-heading">
        <div>
          <div className="sequence-tile-top">
            <Badge tone={sequence.status === "ready" ? "green" : "gray"}>
              {sequence.status === "ready"
                ? t("Reviewed", "已审核")
                : t("Draft sequence", "序列草稿")}
            </Badge>
            <span>
              {sequence.steps.length} {t("steps", "步")} ·{" "}
              {sequence.language.toUpperCase()}
            </span>
          </div>
          <h2>{sequence.name}</h2>
          <p>
            {sequence.description ||
              t(
                "Set the pace and give every email a purpose.",
                "设置联系节奏，让每封邮件都有明确的目的。",
              )}
          </p>
        </div>
        <div className="sequence-actions">
          <button
            className="button"
            disabled={busy}
            onClick={() => setRename(true)}
          >
            <Settings2 size={15} />
            {t("Details", "序列信息")}
          </button>
          <button
            className="button"
            disabled={busy || running || !sequence.steps.length}
            onClick={() =>
              void action(async () => {
                setSavingTemplate(true);
              })
            }
          >
            <Save size={15} />
            {t("Save as template", "存为模板")}
          </button>
        </div>
      </section>
      <div
        className="sequence-stages"
        aria-label={t("Sequence setup stages", "序列设置步骤")}
      >
        {[
          ["steps", t("Build steps", "编排步骤"), GitBranch],
          ["context", t("People & context", "联系人与背景"), Users],
          ["review", t("Preview & review", "预览与审核"), Eye],
        ].map(([key, label, Icon], i) => {
          const I = Icon as typeof Plus;
          return (
            <button
              key={String(key)}
              className={tab === key ? "active" : ""}
              aria-pressed={tab === key}
              disabled={busy}
              onClick={() => void chooseTab(String(key))}
            >
              <span>{i + 1}</span>
              <I size={16} />
              {String(label)}
            </button>
          );
        })}
      </div>
      {error && (
        <div className="error-panel" role="alert">
          {error}
          <button
            className="button"
            onClick={() =>
              void action(async () => {
                await load();
                setSelected(null);
              })
            }
          >
            {t("Reload latest sequence", "重新加载最新序列")}
          </button>
        </div>
      )}
      {job && (
        <div
          className={"panel sequence-job " + job.status}
          role="status"
          data-testid="sequence-generation"
          data-status={job.status}
        >
          <div>
            <Sparkles size={20} />
            <strong>
              {running
                ? t("Building your sequence…", "正在生成邮件序列…")
                : job.status === "succeeded"
                  ? t("AI step plan complete", "AI 步骤规划已完成")
                  : t("AI planning needs attention", "AI 规划需要处理")}
            </strong>
            <Badge>{job.mode === "mock" ? "Mock AI" : "Live AI"}</Badge>
          </div>
          <p>
            {job.completed_steps} / {job.total_steps}{" "}
            {t("steps generated", "步已生成")} · {job.model}
          </p>
          {running && (
            <progress max={job.total_steps || 1} value={job.completed_steps} />
          )}
          {job.result_steps?.map((step, i) => (
            <div className="sequence-job-step" key={i}>
              <Check size={14} />
              {i + 1}. {step.title}
              <small>
                {step.delay_days ? `+${step.delay_days}d` : t("Start", "开始")}
              </small>
            </div>
          ))}
          {job.error && <p className="error-text">{job.error}</p>}
          {!running && job.status !== "succeeded" && (
            <button className="button" onClick={() => setPlan(true)}>
              {t("Retry AI planning", "重试 AI 规划")}
            </button>
          )}
        </div>
      )}
      {tab === "steps" && (
        <>
          <div className="sequence-toolbar">
            <div>
              <h3>{t("Conversation flow", "邮件流程")}</h3>
              <p>
                {t(
                  "Changes to step order and timing are saved immediately.",
                  "步骤顺序与时间设置会在确认操作后保存。",
                )}
              </p>
            </div>
            <button
              className="button"
              disabled={busy || running}
              onClick={() =>
                void action(async () => {
                  setPlan(true);
                })
              }
            >
              <Sparkles size={16} />
              {t("AI step settings", "AI 设置步骤")}
            </button>
          </div>
          <div className="sequence-flow">
            <div className="sequence-start">
              <span />
              <b>{t("Sequence begins", "序列开始")}</b>
            </div>
            {sequence.steps.map((step, index) => {
              cumulative += step.delay_days;
              const day = cumulative + 1;
              if (step.thread_mode === "new_thread")
                threadSubject = step.draft.subject;
              const inheritedSubject = threadSubject
                .toLowerCase()
                .startsWith("re:")
                ? threadSubject
                : "Re: " + threadSubject;
              return (
                <article
                  key={step.id}
                  className={
                    "sequence-step panel " +
                    (selected === step.id ? "expanded" : "")
                  }
                  data-testid="sequence-step"
                >
                  <div className="sequence-step-node">{index + 1}</div>
                  <div className="sequence-step-heading">
                    <div className="sequence-step-summary">
                      <span className="sequence-day">
                        <Clock3 size={13} />
                        {t("Day", "第")} {day}
                        {t("", " 天")}
                        {step.delay_days
                          ? ` · +${step.delay_days}${t(" days", " 天")}`
                          : ""}
                      </span>
                      <h3>
                        <Mail size={18} />
                        {step.title}
                      </h3>
                      <p>{step.purpose}</p>
                    </div>
                    <div className="sequence-step-actions">
                      <button
                        className="icon-button"
                        aria-label={t(
                          `Move step ${index + 1} up`,
                          `上移第 ${index + 1} 步`,
                        )}
                        disabled={busy || running || index === 0}
                        onClick={() => void action(() => reorder(index, -1))}
                      >
                        <ArrowUp size={15} />
                      </button>
                      <button
                        className="icon-button"
                        aria-label={t(
                          `Move step ${index + 1} down`,
                          `下移第 ${index + 1} 步`,
                        )}
                        disabled={
                          busy || running || index === sequence.steps.length - 1
                        }
                        onClick={() => void action(() => reorder(index, 1))}
                      >
                        <ArrowDown size={15} />
                      </button>
                      <button
                        className="icon-button"
                        aria-label={t(
                          `Step ${index + 1} settings`,
                          `第 ${index + 1} 步设置`,
                        )}
                        disabled={busy || running}
                        onClick={() =>
                          void action(async () => {
                            setStepEdit(step);
                          })
                        }
                      >
                        <Settings2 size={16} />
                      </button>
                      <button
                        className="icon-button"
                        aria-label={t(
                          `Remove step ${index + 1}`,
                          `移除第 ${index + 1} 步`,
                        )}
                        disabled={busy || running}
                        onClick={() =>
                          void action(async () => {
                            const steps = sequence.steps
                              .filter((s) => s.id !== step.id)
                              .map(stepPayload);
                            if (steps.length) {
                              steps[0].thread_mode = "new_thread";
                              steps[0].delay_days = 0;
                            }
                            await update({ steps, status: "draft" });
                            if (selected === step.id) setSelected(null);
                          })
                        }
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>
                  <div className="sequence-email-summary">
                    <Badge>
                      {step.thread_mode === "reply"
                        ? t("Reply in previous thread", "在上一封邮件中回复")
                        : t("New thread", "新邮件")}
                    </Badge>
                    <strong>
                      {step.thread_mode === "reply"
                        ? t("Inherits the previous subject", "继承上一封主题")
                        : step.draft.subject ||
                          t("Subject not written yet", "尚未填写主题")}
                    </strong>
                    <button
                      className="button small-button"
                      disabled={busy || running}
                      onClick={() =>
                        void action(async () => {
                          await load();
                          setSelected(selected === step.id ? null : step.id);
                        })
                      }
                    >
                      {selected === step.id
                        ? t("Close editor", "收起编辑器")
                        : t("Write email", "编辑邮件")}
                    </button>
                  </div>
                  {selected === step.id && (
                    <div className="sequence-inline-writer">
                      <DraftEditor
                        key={step.draft_id}
                        id={step.draft_id}
                        disabled={busy || running}
                        replySubject={
                          step.thread_mode === "reply"
                            ? inheritedSubject
                            : undefined
                        }
                        loadPreview={async () => {
                          const result = await api<SequencePreview>(
                            "/sequences/" + id + "/preview",
                          );
                          const item = result.steps.find(
                            (p) => p.step_id === step.id,
                          );
                          if (!item)
                            throw new Error(
                              t(
                                "This step changed. Reopen the latest sequence.",
                                "步骤已变化，请重新打开最新序列。",
                              ),
                            );
                          return item.preview;
                        }}
                      />
                    </div>
                  )}
                </article>
              );
            })}
            {!sequence.steps.length && (
              <div className="panel sequence-empty">
                <Mail size={27} />
                <h3>{t("Add the first email", "添加第一封邮件")}</h3>
                <p>
                  {t(
                    "Choose an existing draft, start writing, or let AI plan the steps.",
                    "从草稿选择、开始写作，或让 AI 规划步骤。",
                  )}
                </p>
              </div>
            )}
            <button
              className="button sequence-add"
              disabled={busy || running || sequence.steps.length >= 20}
              onClick={() =>
                void action(async () => {
                  setStepEdit("new");
                })
              }
            >
              <Plus size={17} />
              {t("Add a step", "添加步骤")}
            </button>
            <div className="sequence-finish">
              <Check size={16} />
              {t("Review the full conversation", "审核完整邮件对话")}
            </div>
          </div>
          <div className="sequence-next">
            <button
              className="button primary"
              disabled={busy || running}
              onClick={() => void chooseTab("context")}
            >
              {t("Next: people & context", "下一步：联系人与背景")}
              <ChevronRight size={16} />
            </button>
          </div>
        </>
      )}
      {tab === "context" && (
        <ContextSettings
          sequence={sequence}
          busy={busy}
          onSave={(values) =>
            action(async () => {
              await update(values);
              notify(t("Sequence context saved", "序列背景已保存"));
            })
          }
          onNext={() => void chooseTab("review")}
        />
      )}
      {tab === "review" && (
        <div className="sequence-review">
          <div className="panel sequence-review-heading">
            <h3>{t("Review every step together", "一起审核所有步骤")}</h3>
            <p>
              {t(
                "Preview uses your selected contact and persona. Complete the flagged fields before marking the sequence reviewed.",
                "预览使用所选联系人和画像。请先补全提示的内容，再标记序列为已审核。",
              )}
            </p>
            <div className="sequence-actions">
              <button
                className="button"
                disabled={busy}
                onClick={() => void chooseTab("review")}
              >
                <Eye size={16} />
                {t("Refresh preview", "刷新预览")}
              </button>
              <button
                className="button primary"
                disabled={busy || running || !preview?.can_mark_ready}
                onClick={() =>
                  void action(async () => {
                    await update({ status: "ready" });
                    setPreview(
                      await api<SequencePreview>(
                        "/sequences/" + id + "/preview",
                      ),
                    );
                    notify(t("Sequence marked reviewed", "序列已标记为已审核"));
                  })
                }
              >
                <Check size={16} />
                {t("Mark sequence reviewed", "标记序列已审核")}
              </button>
            </div>
            {preview?.issues?.length ? (
              <ul className="sequence-review-issues">
                {preview.issues.map((issue, i) => (
                  <li key={i}>{issue}</li>
                ))}
              </ul>
            ) : null}
          </div>
          {preview?.steps.map((item, i) => (
            <article className="panel sequence-preview" key={item.step_id}>
              <div>
                <Badge>
                  {t("Step", "步骤")} {i + 1}
                </Badge>
                <strong>{sequence.steps[i]?.title}</strong>
              </div>
              {item.issues.length > 0 && (
                <ul className="sequence-review-issues">
                  {item.issues.map((issue, j) => (
                    <li key={j}>{issue}</li>
                  ))}
                </ul>
              )}
              <h3>{item.preview.subject}</h3>
              <div
                className="sequence-preview-body"
                dangerouslySetInnerHTML={{ __html: item.preview.body_html }}
              />
              <button
                className="button small-button"
                onClick={() => {
                  setTab("steps");
                  setSelected(item.step_id);
                }}
              >
                {t("Edit this email", "编辑此邮件")}
              </button>
            </article>
          ))}
          <p className="sequence-note">
            {t(
              "Reviewed sequences stay in your workspace. Mailbox connection, scheduling, and sending are not enabled in this local release.",
              "已审核序列会保留在工作区。本地当前版本尚未启用邮箱连接、调度和发送。",
            )}
          </p>
        </div>
      )}
      {stepEdit && (
        <StepSettings
          sequence={sequence}
          step={stepEdit === "new" ? null : stepEdit}
          onClose={() => setStepEdit(null)}
          onSave={async (values) => {
            if (guard.current) await guard.current();
            if (stepEdit === "new") {
              const s = await post<Sequence>("/sequences/" + id + "/steps", {
                revision: sequence.revision,
                ...values,
              });
              setSequence(s);
            } else
              await update({
                steps: sequence.steps.map((s) =>
                  s.id === stepEdit.id
                    ? { ...stepPayload(s), ...values }
                    : stepPayload(s),
                ),
                status: "draft",
              });
            setStepEdit(null);
            setSelected(null);
            await load();
            await refresh();
            await onChange();
          }}
        />
      )}
      {plan && (
        <PlanSettings
          sequence={sequence}
          templates={templates}
          onClose={() => setPlan(false)}
          onGenerate={async (values) => {
            if (guard.current) await guard.current();
            const latest = await load();
            const next = await post<SequenceJob>(
              "/sequences/" + id + "/ai-plan",
              { revision: latest.revision, ...values },
            );
            setJob(next);
            setSelected(null);
            setPlan(false);
            setTab("steps");
          }}
        />
      )}
      {savingTemplate && (
        <SaveTemplate
          sequence={sequence}
          onClose={() => setSavingTemplate(false)}
          onSaved={async () => {
            setSavingTemplate(false);
            await onChange();
            notify(t("Reusable step template saved", "可复用步骤模板已保存"));
          }}
        />
      )}
      {rename && (
        <RenameSequence
          sequence={sequence}
          onClose={() => setRename(false)}
          onSave={async (values) => {
            if (guard.current) await guard.current();
            await update(values);
            setRename(false);
          }}
        />
      )}
    </>
  );
}

function ContextSettings({
  sequence,
  busy,
  onSave,
  onNext,
}: {
  sequence: Sequence;
  busy: boolean;
  onSave: (values: object) => Promise<void>;
  onNext: () => void;
}) {
  const { t, contacts, personas } = useApp();
  const [contact, setContact] = useState(sequence.contact_id || "");
  const [persona, setPersona] = useState(sequence.persona_id || "");
  const dirty =
    contact !== (sequence.contact_id || "") ||
    persona !== (sequence.persona_id || "");
  return (
    <section className="panel sequence-context">
      <div className="sequence-section-label">
        02 · {t("Personalize the conversation", "个性化邮件对话")}
      </div>
      <h3>
        {t("Choose a preview contact and sender", "选择预览联系人与发件人")}
      </h3>
      <p>
        {t(
          "Apply this context to every email. You can adjust an individual email later in its writing editor.",
          "将背景应用到每封邮件。也可以稍后在各步骤写作编辑器中单独调整。",
        )}
      </p>
      <div className="form-grid">
        <Field label={t("Sequence contact", "序列联系人")}>
          <select value={contact} onChange={(e) => setContact(e.target.value)}>
            <option value="">{t("Choose later", "稍后选择")}</option>
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} · {c.company}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("Sequence sender persona", "序列发件人画像")}>
          <select value={persona} onChange={(e) => setPersona(e.target.value)}>
            <option value="">{t("Choose later", "稍后选择")}</option>
            {personas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="sequence-actions">
        <button
          className="button"
          disabled={busy || !dirty}
          onClick={() =>
            void onSave({
              contact_id: contact || null,
              persona_id: persona || null,
              status: "draft",
            })
          }
        >
          <Save size={16} />
          {t("Apply to all emails", "应用到所有邮件")}
        </button>
        <button
          className="button primary"
          disabled={busy || dirty}
          onClick={onNext}
        >
          {t("Next: preview & review", "下一步：预览与审核")}
          <ChevronRight size={16} />
        </button>
      </div>
      {dirty && (
        <p className="sequence-note">
          {t(
            "Apply your selection before continuing.",
            "请先应用所选背景，再继续。",
          )}
        </p>
      )}
    </section>
  );
}

function StepSettings({
  sequence,
  step,
  onClose,
  onSave,
}: {
  sequence: Sequence;
  step: SequenceStep | null;
  onClose: () => void;
  onSave: (values: object) => Promise<void>;
}) {
  const { t } = useApp();
  const [title, setTitle] = useState(step?.title || "");
  const [purpose, setPurpose] = useState(step?.purpose || "");
  const first = step
    ? sequence.steps[0]?.id === step.id
    : sequence.steps.length === 0;
  const [delay, setDelay] = useState(step?.delay_days ?? (first ? 0 : 3));
  const [thread, setThread] = useState(
    step?.thread_mode || (first ? "new_thread" : "reply"),
  );
  const [source, setSource] = useState("blank");
  const [draft, setDraft] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Drawer
      title={
        step
          ? t("Step settings", "步骤设置")
          : t("Add an email step", "添加邮件步骤")
      }
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <div className="sequence-form">
        <Field label={t("Step title", "步骤标题")}>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={150}
            placeholder={t("e.g. A friendly follow-up", "例如：友好跟进")}
          />
        </Field>
        <Field label={t("Step purpose", "步骤目的")}>
          <textarea
            rows={3}
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
          />
        </Field>
        <div className="form-grid">
          <Field
            label={t("Wait days after previous step", "距离上一步等待天数")}
          >
            <input
              type="number"
              min={0}
              max={365}
              disabled={first}
              value={delay}
              onChange={(e) => setDelay(Number(e.target.value))}
            />
          </Field>
          <Field label={t("Email thread", "邮件会话")}>
            <select
              value={thread}
              disabled={first}
              onChange={(e) => setThread(e.target.value as typeof thread)}
            >
              <option value="new_thread">{t("New thread", "新邮件")}</option>
              <option value="reply">
                {t("Reply to previous email", "回复上一封邮件")}
              </option>
            </select>
          </Field>
        </div>
        <Field
          label={t(
            step ? "Email content" : "Email source",
            step ? "邮件内容" : "邮件来源",
          )}
        >
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="blank">
              {step
                ? t("Keep current email", "保留当前邮件")
                : t("Blank email", "空白邮件")}
            </option>
            <option value="draft">
              {t("Choose from drafts", "从草稿箱选择")}
            </option>
          </select>
        </Field>
        {source === "draft" && (
          <DraftPicker selected={draft} setSelected={setDraft} single />
        )}
        {error && (
          <div className="error-panel" role="alert">
            {error}
          </div>
        )}
        <button
          className="button primary"
          disabled={
            busy ||
            !title.trim() ||
            delay < 0 ||
            delay > 365 ||
            !Number.isInteger(delay) ||
            (source === "draft" && !draft.length)
          }
          onClick={async () => {
            setBusy(true);
            try {
              await onSave({
                title,
                purpose,
                delay_days: first ? 0 : delay,
                thread_mode: first ? "new_thread" : thread,
                ...(source === "draft" ? { draft_id: draft[0] } : {}),
              });
            } catch (e) {
              setError(errorText(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? <Busy /> : <Save size={16} />}
          {t("Save step", "保存步骤")}
        </button>
      </div>
    </Drawer>
  );
}

function PlanSettings({
  sequence,
  onClose,
  onGenerate,
}: {
  sequence: Sequence;
  templates: SequenceTemplate[];
  onClose: () => void;
  onGenerate: (values: object) => Promise<void>;
}) {
  const { t } = useApp();
  const [prompt, setPrompt] = useState(sequence.description);
  const [count, setCount] = useState(sequence.steps.length || 3);
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Drawer
      title={t("AI step settings", "AI 设置步骤")}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <div className="sequence-form">
        <p className="sequence-note">
          {t(
            "A completed AI plan replaces this sequence's steps. Your existing email drafts remain in Email Studio. Changes made while AI runs prevent automatic replacement.",
            "AI 完成后将替换序列步骤，已有邮件草稿仍保存在邮件工作室。生成期间若有新编辑，系统会停止自动替换。",
          )}
        </p>
        <Field label={t("Sequence planning prompt", "序列规划提示词")}>
          <textarea
            rows={6}
            maxLength={6000}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
        </Field>
        <Field label={t("Number of steps", "步骤数量")}>
          <input
            type="number"
            min={1}
            max={8}
            value={count}
            onChange={(e) => setCount(Number(e.target.value))}
          />
        </Field>
        <ModelSelect value={model} onChange={setModel} />
        {error && (
          <div className="error-panel" role="alert">
            {error}
          </div>
        )}
        <button
          className="button primary"
          disabled={
            busy ||
            !prompt.trim() ||
            count < 1 ||
            count > 8 ||
            !Number.isInteger(count)
          }
          onClick={async () => {
            setBusy(true);
            try {
              await onGenerate({
                prompt,
                step_count: count,
                model,
                language: sequence.language,
              });
            } catch (e) {
              setError(errorText(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? <Busy /> : <Sparkles size={16} />}
          {t("Generate step plan", "生成步骤计划")}
        </button>
      </div>
    </Drawer>
  );
}

function SaveTemplate({
  sequence,
  onClose,
  onSaved,
}: {
  sequence: Sequence;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { t } = useApp();
  const [name, setName] = useState(sequence.name + " template");
  const [description, setDescription] = useState(sequence.description);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Drawer
      title={t("Save reusable step template", "保存可复用步骤模板")}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <div className="sequence-form">
        <Field label={t("Template name", "模板名称")}>
          <input
            maxLength={150}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field label={t("Template description", "模板说明")}>
          <textarea
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <p className="sequence-note">
          {t(
            "Saves the step order, timing, thread settings, and email content. Recipient and sender assignments are left out so you can reuse it.",
            "保存步骤顺序、时间间隔、会话设置与邮件内容，不绑定收件人与发件人，便于重复使用。",
          )}
        </p>
        {error && (
          <div className="error-panel" role="alert">
            {error}
          </div>
        )}
        <button
          className="button primary"
          disabled={busy || !name.trim()}
          onClick={async () => {
            setBusy(true);
            try {
              await post("/sequences/" + sequence.id + "/save-template", {
                name,
                description,
              });
              await onSaved();
            } catch (e) {
              setError(errorText(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? <Busy /> : <Save size={16} />}
          {t("Save template", "保存模板")}
        </button>
      </div>
    </Drawer>
  );
}

function RenameSequence({
  sequence,
  onClose,
  onSave,
}: {
  sequence: Sequence;
  onClose: () => void;
  onSave: (values: object) => Promise<void>;
}) {
  const { t } = useApp();
  const [name, setName] = useState(sequence.name);
  const [description, setDescription] = useState(sequence.description);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Drawer
      title={t("Sequence details", "序列信息")}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <div className="sequence-form">
        <Field label={t("Sequence name", "序列名称")}>
          <input
            value={name}
            maxLength={150}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field label={t("Sequence description", "序列说明")}>
          <textarea
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        {error && (
          <div className="error-panel" role="alert">
            {error}
          </div>
        )}
        <button
          className="button primary"
          disabled={busy || !name.trim()}
          onClick={async () => {
            setBusy(true);
            try {
              await onSave({ name, description });
            } catch (e) {
              setError(errorText(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? <Busy /> : <Save size={16} />}
          {t("Save details", "保存信息")}
        </button>
      </div>
    </Drawer>
  );
}

function TemplateLibrary({
  templates,
  onClose,
  onChange,
  onUse,
}: {
  templates: SequenceTemplate[];
  onClose: () => void;
  onChange: () => Promise<void>;
  onUse: () => void;
}) {
  const { t } = useApp();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Drawer
      title={t("Reusable step templates", "可复用步骤模板")}
      onClose={onClose}
    >
      <div className="sequence-form">
        <p>
          {t(
            "Three default starting points, plus your own reusable workflows. Download a template to see the upload format, customize its steps, then upload it as a new template.",
            "提供三个默认模板，也支持自定义流程。下载模板查看上传格式，修改步骤后即可上传为新模板。",
          )}
        </p>
        <label className="button">
          <Upload size={16} />
          {t("Upload steps JSON", "上传步骤 JSON")}
          <input
            aria-label={t("Upload step template JSON", "上传步骤模板 JSON")}
            type="file"
            accept=".json,application/json"
            disabled={busy}
            className="sequence-file-input"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setBusy(true);
              setError("");
              try {
                if (file.size > 250000)
                  throw new Error(
                    t(
                      "Choose a JSON file smaller than 250 KB.",
                      "请选择小于 250 KB 的 JSON 文件。",
                    ),
                  );
                await post(
                  "/sequence-templates",
                  JSON.parse(await file.text()),
                );
                await onChange();
              } catch (e) {
                setError(errorText(e));
              } finally {
                setBusy(false);
              }
              e.target.value = "";
            }}
          />
        </label>
        {error && (
          <div className="error-panel" role="alert">
            {error}
          </div>
        )}
        {templates.map((template) => (
          <div className="sequence-library-item" key={template.id}>
            <div>
              <h3>{template.name}</h3>
              <Badge>
                {template.is_default
                  ? t("Default", "默认")
                  : t("Custom", "自定义")}
              </Badge>
            </div>
            <p>{template.description}</p>
            <ol>
              {template.steps.map((step, i) => (
                <li key={i}>
                  <b>{step.title}</b>
                  <small>
                    {step.delay_days
                      ? `+${step.delay_days} ${t("days", "天")}`
                      : t("Start", "开始")}{" "}
                    ·{" "}
                    {step.thread_mode === "reply"
                      ? t("Reply", "回复")
                      : t("New thread", "新邮件")}
                  </small>
                </li>
              ))}
            </ol>
            <div className="sequence-actions">
              <button
                className="button small-button"
                onClick={() => downloadTemplate(template)}
              >
                <Download size={14} />
                {t("Download JSON", "下载 JSON")}
              </button>
              {!template.is_default && (
                <button
                  className="button small-button"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      await api("/sequence-templates/" + template.id, {
                        method: "DELETE",
                      });
                      await onChange();
                    } catch (e) {
                      setError(errorText(e));
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  <Trash2 size={14} />
                  {t("Delete template", "删除模板")}
                </button>
              )}
            </div>
          </div>
        ))}
        <button className="button primary" onClick={onUse}>
          {t("Create from a template", "用模板创建序列")}
          <ChevronRight size={16} />
        </button>
      </div>
    </Drawer>
  );
}
