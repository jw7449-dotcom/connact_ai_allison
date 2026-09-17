"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Copy, Download, GitBranch, Inbox, Clock3 } from "lucide-react";
import { api, ApiError, errorText, post, put } from "@/lib/api";
import { useApp } from "@/lib/context";
import type { Draft, Preview } from "@/lib/types";
import type { Sequence } from "@/lib/sequence-types";
import { useDraft } from "@/lib/use-draft";
import { Badge, Busy, Field, Nav } from "./ui";
import { SendDraft } from "./mail-send";
import "./finance-review.css";

export function FinanceReview(props: {
  id: string;
  onReviewed: (draft: Draft) => void;
}) {
  return <ReviewDraft key={props.id} {...props} />;
}

function ReviewDraft({
  id,
  onReviewed,
}: {
  id: string;
  onReviewed: (draft: Draft) => void;
}) {
  const { t, refresh, notify } = useApp();
  const { draft, flush, accept, loadLatest, recovered, error, setError } =
    useDraft(id);
  const [preview, setPreview] = useState<
    (Preview & { revision: number }) | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  const submitting = useRef(false);
  const revision = draft?.revision;

  useEffect(() => {
    if (revision === undefined) return;
    let active = true;
    setLoading(true);
    setPreview(null);
    // Resolve the saved draft after the editor's autosave (or a recoverable
    // local buffer), keeping useDraft's revision/conflict rules intact.
    void flush()
      .then(async (saved) => {
        if (!saved) return;
        const resolved = await api<Preview>(`/drafts/${id}/preview`);
        if (active) {
          setPreview({ ...resolved, revision: saved.revision });
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(errorText(e));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id, revision, version, flush, setError]);

  function accepted(saved: Draft) {
    accept(saved);
    if (saved.status === "ready") onReviewed(saved);
  }

  async function markReviewed() {
    if (!preview || !preview.can_mark_ready || submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      const latest = await flush();
      if (!latest || latest.revision !== preview.revision)
        throw new Error(
          t(
            "The draft changed. Refresh the preview and review it again.",
            "草稿已更改，请刷新预览并重新审核。",
          ),
        );
      const saved = await put<Draft>(`/drafts/${id}`, {
        ...latest,
        status: "ready",
        revision: latest.revision,
      });
      accepted(saved);
      await refresh();
      notify(
        t("Draft reviewed. Continue when ready.", "草稿已审核，可继续下一步。"),
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  async function reload() {
    setBusy(true);
    try {
      await loadLatest();
      setVersion((value) => value + 1);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function copy(kind: "subject" | "body" | "both") {
    if (!preview) return;
    const content =
      kind === "subject"
        ? preview.subject
        : kind === "body"
          ? preview.body_text
          : `Subject: ${preview.subject}\n\n${preview.body_text}`;
    try {
      await navigator.clipboard.writeText(content);
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

  async function exportEmail() {
    if (!preview?.can_mark_ready || !preview.recipient_email) return;
    setBusy(true);
    try {
      await flush();
      window.location.assign(`/api/drafts/${id}/export.eml`);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function copyRecovered() {
    if (!draft) return;
    try {
      const body = new DOMParser().parseFromString(
        draft.body_html,
        "text/html",
      );
      await navigator.clipboard.writeText(
        `Subject: ${draft.subject}\n\n${body.body.textContent || ""}`,
      );
      notify(t("Recovered text copied.", "已复制恢复的文字。"));
    } catch {
      setError(
        t(
          "Clipboard access was denied. Your recovered edits are still saved in this tab.",
          "剪贴板访问被拒绝，恢复的修改仍保留在当前标签页。",
        ),
      );
    }
  }

  return (
    <div className="finance-review">
      <section
        className="panel finance-review-card"
        aria-label={t("Final review", "最终审核")}
      >
        <div className="section-head">
          <h2>{t("Review your email", "审核邮件")}</h2>
          {draft && (
            <Badge tone={draft.status === "ready" ? "green" : "gray"}>
              {draft.status === "ready"
                ? t("Reviewed", "已审核")
                : t("Draft", "草稿")}
            </Badge>
          )}
        </div>
        <p className="finance-review-intro">
          {t(
            "Check the recipient and resolved email below, then mark the content as reviewed. Gmail sending is optional and has its own confirmation.",
            "检查收件人和填入真实信息后的邮件，再标记为已审核。也可选择使用 Gmail 发送，发送前需单独确认。",
          )}
        </p>
        {error && (
          <div className="error-panel" role="alert">
            {error}
            {recovered && (
              <div>
                <p>
                  {t(
                    "Copy your recovered edits before loading the latest saved draft.",
                    "请先复制恢复的修改，再加载最新草稿。",
                  )}
                </p>
                <button className="button" onClick={() => void copyRecovered()}>
                  {t("Copy recovered text", "复制恢复的文字")}
                </button>
              </div>
            )}
            <button
              className="button"
              disabled={busy}
              onClick={() => void reload()}
            >
              {t("Load latest draft", "加载最新草稿")}
            </button>
          </div>
        )}
        {(loading && !error) || (!draft && !error) ? (
          <div className="finance-review-loading" role="status">
            <Busy /> {t("Resolving email preview…", "正在生成邮件预览…")}
          </div>
        ) : preview && draft ? (
          <>
            {preview.missing_variables.length > 0 && (
              <div className="error-panel" role="alert">
                <strong>{t("Missing variables", "缺失变量")}</strong>
                <p>{preview.missing_variables.join(", ")}</p>
                <p>
                  {t(
                    "Complete the contact or persona fields before reviewing.",
                    "请先补齐联系人或画像字段，再完成审核。",
                  )}
                </p>
              </div>
            )}
            {preview.persona_changed && (
              <p className="notice">
                {t(
                  "This persona changed. Return to the writing step, check the new background and save the draft again.",
                  "画像已更新，请返回写作步骤检查新背景，并重新保存草稿。",
                )}
              </p>
            )}
            {!preview.can_mark_ready &&
              !preview.missing_variables.length &&
              !preview.persona_changed && (
                <p className="notice">
                  {t(
                    "Choose a recipient and complete the subject and body in the writing step.",
                    "请返回写作步骤，选择收件人并补齐主题和正文。",
                  )}
                </p>
              )}
            <div className="finance-review-recipient">
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
            <h3 className="finance-review-subject">
              {preview.subject || t("No subject", "暂无主题")}
            </h3>
            <div
              className="preview-body finance-review-body"
              dangerouslySetInnerHTML={{ __html: preview.body_html }}
            />
            <div className="finance-review-actions">
              <button className="button" onClick={() => void copy("subject")}>
                <Copy size={15} />
                {t("Copy subject", "复制主题")}
              </button>
              <button className="button" onClick={() => void copy("body")}>
                <Copy size={15} />
                {t("Copy body", "复制正文")}
              </button>
              <button className="button" onClick={() => void copy("both")}>
                <Copy size={15} />
                {t("Copy all", "复制全部")}
              </button>
              <button
                className="button"
                disabled={
                  busy || !preview.can_mark_ready || !preview.recipient_email
                }
                onClick={() => void exportEmail()}
              >
                <Download size={15} />
                {t("Download email (.eml)", "下载邮件（.eml）")}
              </button>
            </div>
            <div className="finance-review-confirm">
              <button
                className="button primary"
                disabled={
                  busy ||
                  loading ||
                  !preview.can_mark_ready ||
                  preview.revision !== draft.revision ||
                  draft.status === "ready"
                }
                onClick={() => void markReviewed()}
              >
                {busy ? <Busy /> : <Check size={16} />}
                {draft.status === "ready"
                  ? t("Content reviewed", "内容已审核")
                  : t("Mark as reviewed & ready", "标记为已审核并可使用")}
              </button>
              <p>
                {t(
                  "Requires a recipient, subject, body and resolved variables. Reviewing saves the content status.",
                  "需选择收件人并补齐主题、正文和变量。审核操作将保存内容状态。",
                )}
              </p>
            </div>
          </>
        ) : null}
      </section>
      {draft && (
        <SendDraft
          draft={draft}
          flush={flush}
          accept={accepted}
          disabled={busy || loading || !preview?.can_mark_ready}
        />
      )}
    </div>
  );
}

export function FinanceFollowup({ draftId }: { draftId: string }) {
  return <FollowupDraft key={draftId} draftId={draftId} />;
}

function FollowupDraft({ draftId }: { draftId: string }) {
  const { t, config, refresh } = useApp();
  const [name, setName] = useState("");
  const [source, setSource] = useState<Draft | null>(null);
  const [sequence, setSequence] = useState<Sequence | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [finished, setFinished] = useState(false);
  const [version, setVersion] = useState(0);
  const creating = useRef(false);
  const storageKey = `connact-finance-sequence:${config?.workspace_id || "local"}:${draftId}`;

  useEffect(() => {
    let active = true;
    setLoading(true);
    void (async () => {
      try {
        const saved = await api<Draft>(`/drafts/${draftId}`);
        if (!active) return;
        setSource(saved);
        setName((value) => value || saved.subject.slice(0, 180));
        let stored = "";
        try {
          stored = sessionStorage.getItem(storageKey) || "";
        } catch {
          /* Optional tab recovery. */
        }
        if (stored) {
          try {
            const existing = await api<Sequence>(`/sequences/${stored}`);
            if (active) setSequence(existing);
          } catch (e) {
            if (!(e instanceof ApiError) || e.status !== 404) throw e;
            // Only a confirmed deletion clears recovery. A temporary failure
            // must not make a saved sequence disappear and invite duplicates.
            try {
              sessionStorage.removeItem(storageKey);
            } catch {
              /* Storage is optional. */
            }
          }
        }
        if (active) setError("");
      } catch (e) {
        if (active) setError(errorText(e));
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [draftId, storageKey, version]);

  async function createSequence() {
    if (!name.trim() || creating.current || sequence) return;
    creating.current = true;
    setBusy(true);
    setError("");
    try {
      const latest = await api<Draft>(`/drafts/${draftId}`);
      const currentPreview = await api<Preview>(`/drafts/${draftId}/preview`);
      if (latest.status !== "ready" || !currentPreview.can_mark_ready)
        throw new Error(
          t(
            "The draft needs review again. Return to the review step before creating a sequence.",
            "草稿需要重新审核，请返回审核步骤后再创建序列。",
          ),
        );
      // Sequence creation copies both emails in one transaction. Every copy
      // starts as a draft; the reviewed source and delivery state stay intact.
      const created = await post<Sequence>("/sequences", {
        name: name.trim(),
        language: latest.language,
        contact_id: latest.contact_id,
        persona_id: latest.persona_id,
        draft_ids: [latest.id, latest.id],
      });
      setSequence(created);
      try {
        sessionStorage.setItem(storageKey, created.id);
      } catch {
        /* Keep the result in memory. */
      }
      await refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      creating.current = false;
      setBusy(false);
    }
  }

  return (
    <section
      className="panel finance-followup"
      aria-label={t("Optional follow-up", "可选跟进")}
    >
      <div className="section-head">
        <h2>
          {sequence || finished
            ? t("Your workflow is complete", "本次流程已完成")
            : t("Plan your next conversation", "安排下一次交流")}
        </h2>
        <Badge tone={sequence || finished ? "green" : "blue"}>
          {sequence || finished
            ? t("Complete", "已完成")
            : t("Optional", "可选")}
        </Badge>
      </div>
      {error && (
        <div className="error-panel" role="alert">
          {error}
          <button
            className="button"
            disabled={busy || loading}
            onClick={() => setVersion((value) => value + 1)}
          >
            {t("Retry", "重试")}
          </button>
        </div>
      )}
      {loading ? (
        <p className="finance-review-loading" role="status">
          <Busy />
          {t("Loading your reviewed draft…", "正在加载已审核草稿…")}
        </p>
      ) : sequence ? (
        <div className="finance-followup-result" role="status">
          <Check size={24} />
          <div>
            <h3>{sequence.name}</h3>
            <p>
              {t(
                "Your sequence is saved. Open the sequence editor to adapt the follow-up message and review each step. Your original email remains saved separately.",
                "序列已保存。请在序列编辑器中调整跟进内容并逐步审核，原邮件仍独立保存。",
              )}
            </p>
            <Nav
              href={`/sequences?sequence=${sequence.id}`}
              className="button primary"
            >
              <GitBranch size={16} />
              {t("Open sequence editor", "打开序列编辑器")}
            </Nav>
          </div>
        </div>
      ) : finished ? (
        <p className="finance-review-intro">
          {t(
            "Your reviewed email is saved. You can return to it or manage replies and follow-ups from the workspace.",
            "已审核邮件已保存。你可以随时返回邮件，或在工作台管理回复和跟进。",
          )}
        </p>
      ) : source ? (
        <>
          <p className="finance-review-intro">
            {t(
              "Create a draft sequence using this email as a starting point, or finish here and arrange follow-ups later.",
              "以当前邮件为起点创建草稿序列，或先完成本次流程，之后再安排跟进。",
            )}
          </p>
          {source.status !== "ready" && (
            <p className="notice">
              {t(
                "Return to the review step to review this draft first.",
                "请先返回审核步骤，完成草稿审核。",
              )}
            </p>
          )}
          <Field label={t("Sequence name", "序列名称")}>
            <input
              value={name}
              maxLength={200}
              disabled={busy}
              placeholder={t("Finance outreach", "金融外联")}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <ol className="finance-followup-timeline">
            <li>
              <span>{t("Day 0", "第 0 天")}</span>
              <div>
                <strong>{t("Initial email", "首封邮件")}</strong>
                <p>
                  {t(
                    "An independent copy of your reviewed email.",
                    "当前已审核邮件的独立副本。",
                  )}
                </p>
              </div>
            </li>
            <li>
              <span>{t("+3 days", "+3 天")}</span>
              <div>
                <strong>{t("Follow-up draft", "跟进草稿")}</strong>
                <p>
                  {t(
                    "Starts with a copy of this email for you to adapt in the sequence editor.",
                    "以当前邮件副本为起点，在序列编辑器中调整跟进内容。",
                  )}
                </p>
              </div>
            </li>
          </ol>
          <p className="finance-followup-note">
            {t(
              "Both emails are saved as drafts. Open the sequence editor to adjust the messages and timing before use.",
              "两封邮件均保存为草稿。请在序列编辑器中调整内容与时间间隔，再使用。",
            )}
          </p>
          <div className="finance-review-actions">
            <button
              className="button primary"
              disabled={
                busy || !!error || !name.trim() || source.status !== "ready"
              }
              onClick={() => void createSequence()}
            >
              {busy ? <Busy /> : <GitBranch size={16} />}
              {t("Create follow-up sequence", "创建跟进序列")}
            </button>
            <button
              className="button"
              disabled={busy || source.status !== "ready"}
              onClick={() => setFinished(true)}
            >
              {t("Finish without a sequence", "完成，暂不创建序列")}
            </button>
          </div>
        </>
      ) : null}
      <div className="finance-followup-links">
        <Nav href={`/email?draft=${draftId}`}>
          {t("Open saved email", "打开已保存邮件")}
        </Nav>
        <Nav href="/inbox">
          <Inbox size={16} />
          {t("Inbox", "收件箱")}
        </Nav>
        <Nav href="/followups">
          <Clock3 size={16} />
          {t("Follow-ups", "手动跟进")}
        </Nav>
      </div>
    </section>
  );
}
