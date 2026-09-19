"use client";
import { useState, useEffect, useRef } from "react";
import {
  Plus,
  Upload,
  FileText,
  Check,
  ArrowRight,
  ShieldCheck,
  UserRound,
  Save,
} from "lucide-react";
import { useApp } from "@/lib/context";
import { api, post, put, errorText } from "@/lib/api";
import type { Persona, PersonaData } from "@/lib/types";
import {
  Heading,
  Field,
  Avatar,
  Badge,
  Busy,
  DateLabel,
  Nav,
  Empty,
} from "./ui";
import WritingTemplateLibrary from "./writing-template-library";
const blank: PersonaData = {
  name: "",
  education: "",
  experience: "",
  skills: "",
  sectors: "",
  career_goals: "",
  target_regions: "",
  target_roles: "",
  contact_purpose: "",
};
const fields: [keyof PersonaData, string, string, string][] = [
  ["name", "Full name", "姓名", "Alex Morgan"],
  ["education", "Education", "教育经历", "School, degree, dates"],
  [
    "experience",
    "Work experience",
    "工作经历",
    "Role, organization, responsibilities",
  ],
  ["skills", "Skills", "技能", "Financial modeling, valuation, Python"],
  [
    "sectors",
    "Finance focus",
    "金融细分领域",
    "Investment Banking, Private Equity",
  ],
  [
    "career_goals",
    "Career goals",
    "职业目标",
    "The next step you are working toward",
  ],
  [
    "target_regions",
    "Target regions",
    "目标地区",
    "New York, London, Hong Kong",
  ],
  [
    "target_roles",
    "Target organizations or roles",
    "目标机构或职位",
    "Investment Banking Analyst",
  ],
  [
    "contact_purpose",
    "Default contact purpose",
    "默认联系目的",
    "Learn about career paths in investment banking",
  ],
];
type ResumeJob = {
  document_id: string;
  original_name: string;
  status: string;
  data: PersonaData | null;
  extracted_text: string;
  error: string | null;
};
export default function Personas({
  initialPersonaId,
  onSaved,
}: {
  initialPersonaId?: string;
  onSaved?: (persona: Persona) => void;
} = {}) {
  const { t, personas, refresh, notify, config } = useApp();
  const initial =
    initialPersonaId === undefined
      ? personas[0]
      : personas.find((p) => p.id === initialPersonaId);
  const [selected, setSelected] = useState<Persona | null>(initial || null),
    [data, setData] = useState<PersonaData>(initial?.data || blank),
    [label, setLabel] = useState(initial?.label || ""),
    [documentId, setDocumentId] = useState<string | null>(null),
    [raw, setRaw] = useState(""),
    [uploading, setUploading] = useState(false),
    [saving, setSaving] = useState(false),
    [error, setError] = useState(""),
    [dirty, setDirty] = useState(false),
    [parsed, setParsed] = useState<ResumeJob | null>(null),
    [documents, setDocuments] = useState<ResumeJob[]>([]),
    [hydrated, setHydrated] = useState(false);
  const [tab, setTab] = useState<"background" | "templates">("background");
  const storageKey = `connact-persona-editor:${config?.workspace_id || "local-personal"}${onSaved ? ":finance:" + (initialPersonaId || "new") : ""}`;
  const viewId = useRef(0);
  useEffect(() => {
    try {
      const cached = JSON.parse(sessionStorage.getItem(storageKey) || "null");
      const recover =
        !onSaved ||
        ((cached?.dirty || cached?.uploading || cached?.parsed) &&
          (initialPersonaId
            ? cached?.selected?.id === initialPersonaId
            : !cached?.selected));
      if (cached && recover) {
        setSelected(cached.selected);
        setData(cached.data);
        setLabel(cached.label);
        setDocumentId(cached.documentId);
        setRaw(cached.raw || "");
        setDirty(cached.dirty);
        setUploading(cached.uploading);
        setParsed(cached.parsed);
      }
    } catch {
      /* Invalid local buffer does not replace server data. */
    }
    setHydrated(true);
    void api<ResumeJob[]>("/documents")
      .then(setDocuments)
      .catch(() => {});
  }, [storageKey]);
  useEffect(() => {
    if (!hydrated) return;
    try {
      sessionStorage.setItem(
        storageKey,
        JSON.stringify({
          selected,
          data,
          label,
          documentId,
          raw,
          dirty,
          uploading,
          parsed,
        }),
      );
    } catch {
      /* Manual server save remains available if browser storage is full. */
    }
  }, [
    storageKey,
    hydrated,
    selected,
    data,
    label,
    documentId,
    raw,
    dirty,
    uploading,
    parsed,
  ]);
  useEffect(() => {
    if (!documentId || !uploading) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const job = await api<ResumeJob>(`/documents/${documentId}/status`);
        if (!alive) return;
        if (["parsed", "failed"].includes(job.status)) {
          setUploading(false);
          if (job.status === "parsed") {
            setParsed(job);
            setRaw(job.extracted_text || "");
          } else
            setError(
              job.error ||
                "Resume parsing failed. You can retry or enter details manually.",
            );
          void api<ResumeJob[]>("/documents")
            .then((v) => {
              if (alive) setDocuments(v);
            })
            .catch(() => {});
          return;
        }
      } catch (e) {
        if (alive) setError(errorText(e));
      }
      if (alive) timer = setTimeout(poll, 1500);
    }
    void poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [documentId, uploading]);
  const choose = (p: Persona | null) => {
    if (
      dirty &&
      !window.confirm(
        t("Discard unsaved persona edits?", "放弃尚未保存的画像修改？"),
      )
    )
      return;
    viewId.current += 1;
    setSelected(p);
    setData(p?.data || blank);
    setLabel(p?.label || "");
    setDocumentId(null);
    setRaw("");
    setError("");
    setDirty(false);
    setParsed(null);
    setUploading(false);
  };
  async function upload(file: File) {
    const targetView = viewId.current;
    setUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await api<ResumeJob>("/documents/jobs", {
        method: "POST",
        body: form,
      });
      if (targetView !== viewId.current) return;
      setDocumentId(result.document_id);
      setParsed(null);
      setDocuments((old) => [
        result,
        ...old.filter((d) => d.document_id !== result.document_id),
      ]);
      if (result.status === "failed") {
        setError(result.error || "Resume parsing failed.");
        setUploading(false);
        return;
      }
      if (result.status === "parsed") {
        setParsed(result);
        setRaw(result.extracted_text || "");
        setUploading(false);
      }
      notify(
        t(
          "Resume saved. Parsing continues in the background; you can return later.",
          "简历已保存，解析在后台继续，可以稍后回来查看。",
        ),
      );
    } catch (e) {
      if (targetView === viewId.current) {
        setError(errorText(e));
        setUploading(false);
      }
    }
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    const targetView = viewId.current;
    try {
      const body = {
        label,
        data,
        document_id: documentId,
        version: selected?.version,
      };
      const p = selected
        ? await put<Persona>("/personas/" + selected.id, body)
        : await post<Persona>("/personas", body);
      if (targetView === viewId.current) {
        setSelected(p);
        setData(p.data);
        setDirty(false);
      }
      await refresh();
      if (targetView === viewId.current && onSaved) {
        try {
          sessionStorage.removeItem(storageKey);
        } catch {
          /* Optional browser buffer. */
        }
        onSaved(p);
      }
      notify(
        t(
          "Persona saved. A versioned snapshot is ready for personalization.",
          "画像已保存，可用于个性化推荐和写信。",
        ),
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  }
  return (
    <>
      <Heading title={t("Personas", "职业画像")}>
        <button className="button primary" onClick={() => choose(null)}>
          <Plus size={16} />
          {t("New persona", "新建画像")}
        </button>
      </Heading>
      <div className="persona-layout">
        <aside className="persona-list">
          <div className="list-label">
            {t("YOUR PERSONAS", "您的画像")}
            <Badge>{personas.length}</Badge>
          </div>
          {personas.map((p) => (
            <button
              key={p.id}
              className={`persona-tile ${selected?.id === p.id ? "selected" : ""}`}
              onClick={() => choose(p)}
            >
              <Avatar name={p.data.name || p.label} />
              <span>
                <strong>{p.label}</strong>
                <small>
                  {p.data.sectors || t("Finance persona", "金融画像")}
                </small>
                <small>
                  v{p.version} · <DateLabel value={p.updated_at} />
                </small>
              </span>
              {selected?.id === p.id && <Check size={16} />}
            </button>
          ))}
          {!personas.length && (
            <p className="muted">
              {t(
                "Your saved personas will appear here.",
                "保存后的画像将在此显示。",
              )}
            </p>
          )}
          <div className="sidebar-tip">
            <ShieldCheck size={20} />
            <h4>{t("Your background stays yours", "职业背景由您掌控")}</h4>
            <p>
              {t(
                "Files are stored in your workspace. Review extracted details before using them.",
                "文件存储在您的工作区。使用前请检查解析内容。",
              )}
            </p>
          </div>
          {documents.length > 0 && (
            <details className="raw-text">
              <summary>{t("Recent resume imports", "最近导入的简历")}</summary>
              {documents.map((doc) => (
                <div
                  key={doc.document_id}
                  className="row"
                  style={{ marginTop: 8 }}
                >
                  <span>
                    {doc.original_name} · {doc.status}
                  </span>
                  <button
                    type="button"
                    className="button ghost"
                    onClick={() => {
                      setDocumentId(doc.document_id);
                      setError("");
                      setParsed(doc.status === "parsed" ? doc : null);
                      setRaw(doc.extracted_text || "");
                      setUploading(
                        ["queued", "processing"].includes(doc.status),
                      );
                      if (doc.status === "failed")
                        setError(doc.error || "Resume parsing failed.");
                    }}
                  >
                    {t("View result", "查看结果")}
                  </button>
                  {doc.status === "failed" && (
                    <button
                      type="button"
                      className="button ghost"
                      onClick={async () => {
                        try {
                          const retried = await post<ResumeJob>(
                            `/documents/${doc.document_id}/retry`,
                          );
                          setDocumentId(retried.document_id);
                          setUploading(true);
                          setParsed(null);
                          setError("");
                        } catch (e) {
                          setError(errorText(e));
                        }
                      }}
                    >
                      {t("Retry parsing", "重新解析")}
                    </button>
                  )}
                </div>
              ))}
            </details>
          )}
          {uploading && (
            <p className="muted" role="status">
              {t(
                "Parsing is saved in the background. You can use other pages and return later.",
                "解析任务已保存在后台，可切换到其他页面后回来查看。",
              )}
            </p>
          )}
          {parsed?.data && (
            <div className="panel" style={{ margin: "16px 0", padding: 16 }}>
              <strong>
                {t(
                  "Extracted details are ready to review",
                  "提取结果已就绪，请检查",
                )}
              </strong>
              <p>
                {parsed.data.name} · {parsed.data.education}
              </p>
              <button
                type="button"
                className="button"
                onClick={() => {
                  setData(parsed.data!);
                  setLabel(
                    label || parsed.original_name.replace(/\.[^.]+$/, ""),
                  );
                  setDirty(true);
                  setParsed(null);
                  setError("");
                }}
              >
                {t("Use parsed fields", "使用提取的字段")}
              </button>
            </div>
          )}
        </aside>
        <div className="persona-main">
          <div className="persona-tabs" role="tablist">
            {(["background", "templates"] as const).map((key) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                className={tab === key ? "active" : ""}
                onClick={() => setTab(key)}
              >
                {key === "background"
                  ? t("Background", "背景")
                  : t("Templates", "模板")}
              </button>
            ))}
          </div>
          {tab === "templates" ? (
            selected ? (
              <WritingTemplateLibrary
                personaId={selected.id}
                disabled={saving}
              />
            ) : (
              <Empty
                title={t("No persona selected", "尚未选择画像")}
                detail={t(
                  "Create or choose a persona before adding templates to it.",
                  "请先创建或选择一个画像，再为它添加模板。",
                )}
              />
            )
          ) : (
            <section className="panel persona-form">
              <div className="section-head">
                <h2>
                  {selected
                    ? t("Edit persona", "编辑画像")
                    : t("Create your persona", "创建职业画像")}
                </h2>
                <Badge tone={dirty ? "amber" : "green"}>
                  {dirty
                    ? t("Unsaved changes", "尚未保存")
                    : selected
                      ? `Version ${selected.version}`
                      : t("New", "新建")}
                </Badge>
              </div>
              <div className="upload-zone">
                <span className="upload-icon">
                  <Upload size={23} />
                </span>
                <div>
                  <strong>{t("Start with your resume", "从简历开始")}</strong>
                  <p>
                    {t(
                      "Text-based PDF or DOCX · Up to 8 MB · No scanned documents",
                      "文本型 PDF 或 DOCX · 不超过 8 MB · 不支持扫描件",
                    )}
                  </p>
                  <small>
                    {config?.ai_mode === "mock"
                      ? t(
                          "Mock extraction uses section headings. Review unmapped text below.",
                          "模拟解析按章节标题提取，请检查原文中未映射的内容。",
                        )
                      : t(
                          "Resume text is sent to your configured AI provider for extraction.",
                          "简历文本将发送至已配置的 AI 服务进行提取。",
                        )}
                  </small>
                </div>
                <label className={`button ${uploading ? "disabled" : ""}`}>
                  {uploading ? <Busy /> : <Upload size={15} />}{" "}
                  {uploading
                    ? t("Parsing…", "解析中…")
                    : t("Upload resume", "上传简历")}
                  <input
                    aria-label="Upload resume"
                    type="file"
                    accept=".pdf,.docx"
                    disabled={uploading}
                    hidden
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void upload(f);
                      e.target.value = "";
                    }}
                  />
                </label>
              </div>
              {error && (
                <div className="error-panel" role="alert">
                  {error}
                  <p>
                    {t(
                      "You can continue with manual entry below.",
                      "您可以继续使用下方表单手动填写。",
                    )}
                  </p>
                </div>
              )}
              {raw && (
                <details className="raw-text">
                  <summary>
                    {t("Review extracted source text", "检查提取的简历原文")}
                  </summary>
                  <pre>{raw}</pre>
                  {documentId && (
                    <a href={"/api/documents/" + documentId + "/download"}>
                      {t("Download original resume", "下载原始简历")}
                    </a>
                  )}
                </details>
              )}
              <div className="form-intro">
                <UserRound size={17} />
                <span>
                  {t(
                    "Or tell your story in your own words",
                    "也可以直接手动填写职业背景",
                  )}
                </span>
              </div>
              <form onSubmit={save}>
                <fieldset
                  disabled={saving}
                  style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
                >
                  <div className="form-grid">
                    <Field
                      label={t("Persona name", "画像名称")}
                      className="full"
                    >
                      <input
                        required
                        value={label}
                        maxLength={150}
                        placeholder={t(
                          "e.g. Investment banking opportunities",
                          "例如：投资银行求职",
                        )}
                        onChange={(e) => {
                          setLabel(e.target.value);
                          setDirty(true);
                        }}
                      />
                    </Field>
                    {fields.map(([key, en, zh, placeholder]) => (
                      <Field
                        label={t(en, zh)}
                        key={key}
                        className={
                          [
                            "experience",
                            "career_goals",
                            "contact_purpose",
                          ].includes(key)
                            ? "full"
                            : ""
                        }
                      >
                        {[
                          "name",
                          "sectors",
                          "target_regions",
                          "skills",
                        ].includes(key) ? (
                          <input
                            value={data[key]}
                            placeholder={placeholder}
                            onChange={(e) => {
                              setData({ ...data, [key]: e.target.value });
                              setDirty(true);
                            }}
                          />
                        ) : (
                          <textarea
                            rows={key === "experience" ? 3 : 2}
                            value={data[key]}
                            placeholder={placeholder}
                            onChange={(e) => {
                              setData({ ...data, [key]: e.target.value });
                              setDirty(true);
                            }}
                          />
                        )}
                      </Field>
                    ))}
                  </div>
                  <div className="form-footer">
                    <span>
                      {t(
                        "Only saved details are used for recommendations.",
                        "只有已保存的资料会用于推荐。",
                      )}
                    </span>
                    <button
                      className="button primary"
                      disabled={saving || uploading}
                    >
                      {saving ? <Busy /> : <Save size={16} />}{" "}
                      {t("Save persona", "保存画像")}
                    </button>
                  </div>
                </fieldset>
              </form>
            </section>
          )}
        </div>
      </div>
    </>
  );
}
