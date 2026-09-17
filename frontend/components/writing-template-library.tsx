"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { BookOpen, Download, Save, Search, Upload } from "lucide-react";
import { api, errorText, post, put } from "@/lib/api";
import { useApp } from "@/lib/context";
import type { Draft } from "@/lib/types";
import { Badge, Busy, Field } from "./ui";

type WritingTemplate = {
  id: string;
  name: string;
  description: string;
  category: string;
  subject: string;
  body_html: string;
  revision: number;
  is_default: boolean;
};
type TemplateContent = Pick<WritingTemplate, "subject" | "body_html">;

export default function WritingTemplateLibrary({
  draft,
  disabled,
  flush,
  onApply,
  bodyOnly = false,
}: {
  draft?: Draft;
  disabled: boolean;
  flush?: () => Promise<Draft | null>;
  onApply: (content: TemplateContent) => Promise<void>;
  bodyOnly?: boolean;
}) {
  const { t, notify } = useApp();
  const [templates, setTemplates] = useState<WritingTemplate[]>([]),
    [selectedId, setSelectedId] = useState(""),
    [search, setSearch] = useState(""),
    [filter, setFilter] = useState("all"),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [showSave, setShowSave] = useState(false),
    [name, setName] = useState(""),
    [description, setDescription] = useState("");
  const uploadInput = useRef<HTMLInputElement>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const items = await api<WritingTemplate[]>("/writing-templates");
      if (!mounted.current) return;
      setTemplates(items);
      setSelectedId((value) =>
        items.some((item) => item.id === value) ? value : items[0]?.id || "",
      );
      setError("");
    } catch (failure) {
      if (mounted.current) setError(errorText(failure));
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  const visible = templates.filter(
    (item) =>
      (filter === "all" ||
        (filter === "saved" ? !item.is_default : item.is_default)) &&
      `${item.name} ${item.description} ${item.category}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const selected = visible.find((item) => item.id === selectedId) || visible[0];
  const canSave = !!draft?.body_html
    .replace(/<[^>]*>/g, "")
    .replace(/&nbsp;/g, " ")
    .trim();

  async function useTemplate() {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await onApply({
        subject: selected.subject,
        body_html: selected.body_html,
      });
      notify(
        draft
          ? t(
              "Template inserted. Edit the email below or generate a personalized suggestion.",
              "模板已插入，可在下方编辑邮件或生成个性化建议。",
            )
          : t(
              "A new draft was created from this template.",
              "已使用此模板创建新草稿。",
            ),
      );
    } catch (failure) {
      if (mounted.current) setError(errorText(failure));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  async function saveTemplate(update = false) {
    if (
      !flush ||
      !name.trim() ||
      (update && (!selected || selected.is_default))
    )
      return;
    setBusy(true);
    setError("");
    try {
      const current = await flush();
      if (!current || !mounted.current) return;
      const body = {
        name: name.trim(),
        description,
        category: update ? selected!.category : "Custom",
        subject: current.subject,
        body_html: current.body_html,
        ...(update ? { revision: selected!.revision } : {}),
      };
      const result = update
        ? await put<WritingTemplate>(`/writing-templates/${selected!.id}`, body)
        : await post<WritingTemplate>("/writing-templates", body);
      if (!mounted.current) return;
      setTemplates((items) => [
        result,
        ...items.filter((item) => item.id !== result.id),
      ]);
      setSelectedId(result.id);
      setFilter("saved");
      setSearch("");
      setShowSave(false);
      notify(
        t(
          "Email template saved to your workspace.",
          "邮件模板已保存至工作区。",
        ),
      );
    } catch (failure) {
      if (mounted.current) setError(errorText(failure));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  async function upload(file: File) {
    setBusy(true);
    setError("");
    try {
      if (file.size > 256_000)
        throw new Error(
          t(
            "Choose a JSON template smaller than 256 KB.",
            "请选择小于 256 KB 的 JSON 模板。",
          ),
        );
      let parsed: unknown;
      try {
        parsed = JSON.parse(await file.text());
      } catch {
        throw new Error(
          t(
            "This file is not valid JSON. Download a template to see the supported format.",
            "文件不是有效 JSON。请下载模板查看支持的格式。",
          ),
        );
      }
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
        throw new Error(
          t("Upload one email template object.", "请上传单个邮件模板对象。"),
        );
      const data = parsed as Record<string, unknown>;
      if (
        typeof data.name !== "string" ||
        typeof data.subject !== "string" ||
        typeof data.body_html !== "string"
      )
        throw new Error(
          t(
            "The template needs name, subject, and body_html fields.",
            "模板需要 name、subject 和 body_html 字段。",
          ),
        );
      const result = await post<WritingTemplate>("/writing-templates", {
        name: data.name,
        subject: data.subject,
        body_html: data.body_html,
        description:
          typeof data.description === "string" ? data.description : "",
        category: typeof data.category === "string" ? data.category : "Custom",
      });
      if (!mounted.current) return;
      setTemplates((items) => [result, ...items]);
      setSelectedId(result.id);
      setFilter("saved");
      setSearch("");
      notify(
        t(
          "Template uploaded and saved. Select Use template to insert it.",
          "模板已上传保存，点击使用模板即可插入。",
        ),
      );
    } catch (failure) {
      if (mounted.current) setError(errorText(failure));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  function download() {
    if (!selected) return;
    const { name, description, category, subject, body_html } = selected;
    const blob = new Blob(
      [
        JSON.stringify(
          { name, description, category, subject, body_html },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob),
      link = document.createElement("a");
    link.href = url;
    link.download =
      name.replace(/[^\p{L}\p{N}_-]/gu, "-").slice(0, 80) + ".json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <section
      className="email-template-library"
      aria-label={t("Email template library", "邮件模板库")}
    >
      <div className="email-mode-intro">
        <strong>
          <BookOpen size={16} />
          {t("Start from an email you can reuse", "从可复用邮件开始")}
        </strong>
        <p>
          {t(
            "Browse three starter templates, save your own email, or upload a JSON template. Variables resolve in Preview & copy.",
            "浏览三个默认模板，保存自定义邮件或上传 JSON 模板。变量将在预览与复制中替换。",
          )}
        </p>
      </div>
      <div className="email-template-tools">
        {draft && (
          <button
            type="button"
            className="button small-button"
            disabled={disabled || busy || !canSave}
            onClick={() => {
              setName(draft.subject || "");
              setDescription("");
              setShowSave(!showSave);
            }}
          >
            <Save size={14} />
            {t("Save email as template", "将邮件保存为模板")}
          </button>
        )}
        <button
          type="button"
          className="button small-button"
          disabled={disabled || busy}
          onClick={() => uploadInput.current?.click()}
        >
          <Upload size={14} />
          {t("Upload template", "上传模板")}
        </button>
        <input
          ref={uploadInput}
          type="file"
          hidden
          accept=".json,application/json"
          aria-label={t("Upload email template JSON", "上传邮件模板 JSON")}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void upload(file);
          }}
        />
      </div>
      {showSave && (
        <div className="email-template-save">
          <Field label={t("Template name", "模板名称")}>
            <input
              maxLength={200}
              value={name}
              disabled={busy}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <Field label={t("Template description", "模板说明")}>
            <input
              maxLength={2000}
              value={description}
              disabled={busy}
              onChange={(event) => setDescription(event.target.value)}
              placeholder={t(
                "When should this email be used?",
                "适用于什么场景？",
              )}
            />
          </Field>
          <p>
            {t(
              "Saves the subject and body currently in your email editor.",
              "保存邮件编辑器中当前的主题与正文。",
            )}
          </p>
          <div className="email-template-tools">
            <button
              type="button"
              className="button primary small-button"
              disabled={busy || !name.trim() || !canSave}
              onClick={() => void saveTemplate()}
            >
              {busy ? <Busy /> : <Save size={14} />}
              {t("Save new template", "保存新模板")}
            </button>
            {selected && !selected.is_default && (
              <button
                type="button"
                className="button small-button"
                disabled={busy || !name.trim() || !canSave}
                onClick={() => void saveTemplate(true)}
              >
                {t("Update selected template", "更新所选模板")}
              </button>
            )}
            <button
              type="button"
              className="text-button"
              disabled={busy}
              onClick={() => setShowSave(false)}
            >
              {t("Cancel", "取消")}
            </button>
          </div>
        </div>
      )}
      {error && (
        <div className="notice small" role="alert">
          {error}
          <button
            type="button"
            className="text-button"
            disabled={busy}
            onClick={() => void reload()}
          >
            {t("Reload library", "重新加载模板库")}
          </button>
        </div>
      )}
      {loading ? (
        <div className="email-template-loading">
          <Busy />
          {t("Loading templates…", "加载模板中…")}
        </div>
      ) : (
        <>
          <div className="email-template-filters">
            <label className="email-template-search">
              <Search size={15} />
              <input
                aria-label={t("Search email templates", "搜索邮件模板")}
                placeholder={t("Search templates", "搜索模板")}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <select
              aria-label={t("Template collection", "模板分类")}
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            >
              <option value="all">{t("All templates", "全部模板")}</option>
              <option value="starter">
                {t("Starter templates", "默认模板")}
              </option>
              <option value="saved">{t("My templates", "我的模板")}</option>
            </select>
          </div>
          <div className="email-template-browser">
            <div className="email-template-list">
              {visible.length ? (
                visible.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    aria-pressed={item.id === selected?.id}
                    disabled={busy}
                    onClick={() => {
                      setSelectedId(item.id);
                      setShowSave(false);
                    }}
                  >
                    <span>{item.name}</span>
                    <small>
                      {item.category} ·{" "}
                      {item.is_default
                        ? t("Starter", "默认")
                        : t("Saved", "已保存")}
                    </small>
                    <p>{item.description}</p>
                  </button>
                ))
              ) : (
                <p className="muted">
                  {t(
                    "No templates match. Save an email or upload a template to build your library.",
                    "暂无匹配模板。保存邮件或上传模板来创建您的模板库。",
                  )}
                </p>
              )}
            </div>
            {selected && (
              <article
                className="email-template-preview"
                aria-label={t("Template preview", "模板预览")}
              >
                <div className="email-template-preview-head">
                  <Badge>
                    {selected.is_default
                      ? t("STARTER", "默认")
                      : t("SAVED TEMPLATE", "已保存模板")}
                  </Badge>
                  <button
                    type="button"
                    className="text-button"
                    onClick={download}
                    aria-label={t(
                      "Download email template JSON",
                      "下载邮件模板 JSON",
                    )}
                  >
                    <Download size={15} />
                  </button>
                </div>
                <h3>{selected.subject || t("No subject", "无主题")}</h3>
                <div
                  className="email-template-body"
                  dangerouslySetInnerHTML={{ __html: selected.body_html }}
                />
                <button
                  type="button"
                  className="button primary small-button"
                  disabled={disabled || busy}
                  onClick={() => void useTemplate()}
                >
                  {busy ? <Busy /> : <BookOpen size={14} />}
                  {draft
                    ? t("Use template", "使用模板")
                    : t("Create draft from template", "用模板创建草稿")}
                </button>
                <p className="email-template-use-note">
                  {draft
                    ? bodyOnly
                      ? t(
                          "Replaces the current email body. This reply keeps the inherited thread subject.",
                          "替换当前邮件正文，此回复继续使用继承的会话主题。",
                        )
                      : t(
                          "Replaces the current subject and body. Edit the result in Your email below.",
                          "替换当前主题与正文，可在下方邮件内容中继续编辑。",
                        )
                    : t(
                        "Creates a new draft with this subject and body. Personalize it in Email Studio.",
                        "使用此主题与正文创建新草稿，可在邮件工作室中进行个性化编辑。",
                      )}
                </p>
              </article>
            )}
          </div>
          <div className="email-template-variables">
            <span>{t("Available variables", "可用变量")}</span>
            {["name", "company", "title", "school", "sender_name"].map(
              (key) => (
                <code key={key}>{"{{" + key + "}}"}</code>
              ),
            )}
          </div>
        </>
      )}
    </section>
  );
}
