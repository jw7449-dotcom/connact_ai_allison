"use client";
import { useEffect, useRef, useState } from "react";
import { Send, CalendarClock } from "lucide-react";
import { api, errorText, post, put } from "@/lib/api";
import { useApp } from "@/lib/context";
import type { Draft } from "@/lib/types";
import type {
  Mailbox,
  MailboxesResponse,
  MailSend,
  SendPreview,
} from "@/lib/mail-types";
import { Busy, Drawer, Field, Nav } from "./ui";
import "./mail.css";

type OutgoingAttachment = {
  filename: string;
  content_base64: string;
  size: number;
};
export function SendDraft({
  draft,
  flush,
  accept,
  disabled,
  replyMessageId,
  mailboxId,
  onSent,
}: {
  draft: Draft;
  flush: () => Promise<Draft | null>;
  accept: (draft: Draft) => void;
  disabled: boolean;
  replyMessageId?: string;
  mailboxId?: string;
  onSent?: () => void;
}) {
  const { t, notify } = useApp();
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [sender, setSender] = useState(mailboxId || "");
  const [mode, setMode] = useState<"send" | "test" | "schedule">("send");
  const [when, setWhen] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [attachments, setAttachments] = useState<OutgoingAttachment[]>([]);
  const [review, setReview] = useState<
    | (SendPreview & {
        key: string;
        mailbox: Mailbox;
        mode: "send" | "test" | "schedule";
        scheduled_at?: string;
        attachments: OutgoingAttachment[];
      })
    | null
  >(null);
  const [result, setResult] = useState<MailSend | null>(null);
  const submitting = useRef(false);
  useEffect(() => {
    let active = true;
    api<MailboxesResponse>("/mailboxes")
      .then((data) => {
        if (!active) return;
        const available = data.mailboxes.filter(
          (box) =>
            (box.status === "connected" || box.status === "active") &&
            box.can_send !== false,
        );
        setMailboxes(available);
        if (!mailboxId && available.length === 1) setSender(available[0].id);
        setLoaded(true);
      })
      .catch((e) => {
        if (active) {
          setError(errorText(e));
          setLoaded(true);
        }
      });
    return () => {
      active = false;
    };
  }, [mailboxId]);
  async function prepare() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const latest = await flush();
      if (!latest)
        throw new Error(t("Save the draft before sending.", "请先保存草稿。"));
      const mailbox = mailboxes.find((box) => box.id === sender);
      if (!mailbox)
        throw new Error(
          t("Choose a connected Gmail mailbox.", "请选择已连接的 Gmail 邮箱。"),
        );
      let scheduled_at: string | undefined;
      if (mode === "schedule") {
        if (
          !when ||
          !Number.isFinite(new Date(when).getTime()) ||
          new Date(when).getTime() <= Date.now()
        )
          throw new Error(
            t("Choose a future date and time.", "请选择未来的日期与时间。"),
          );
        scheduled_at = new Date(when).toISOString();
      }
      const params = new URLSearchParams({
        draft_id: draft.id,
        mailbox_id: sender,
        mode: mode === "test" ? "test" : "send",
      });
      if (replyMessageId) params.set("reply_message_id", replyMessageId);
      const preview = await api<SendPreview>("/mail/send-preview?" + params);
      setReview({
        ...preview,
        key: crypto.randomUUID(),
        mailbox,
        mode,
        scheduled_at,
        attachments,
      });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function markReady() {
    if (!review) return;
    setBusy(true);
    setError("");
    try {
      const latest = await flush();
      if (!latest || latest.revision !== review.revision)
        throw new Error(
          t(
            "The draft changed. Close this review and review the latest version.",
            "草稿已更改，请关闭并重新审核最新版本。",
          ),
        );
      const saved = await put<Draft>("/drafts/" + draft.id, {
        ...latest,
        status: "ready",
      });
      accept(saved);
      const params = new URLSearchParams({
        draft_id: draft.id,
        mailbox_id: review.mailbox.id,
        mode: review.mode === "test" ? "test" : "send",
      });
      if (replyMessageId) params.set("reply_message_id", replyMessageId);
      const preview = await api<SendPreview>("/mail/send-preview?" + params);
      setReview({
        ...review,
        ...preview,
        attachments: review.attachments,
        key: crypto.randomUUID(),
      });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function chooseFiles(files: FileList | null) {
    setError("");
    setAttachments([]);
    if (!files) return;
    const list = Array.from(files);
    if (
      list.length > 5 ||
      list.reduce((sum, file) => sum + file.size, 0) > 8 * 1024 * 1024
    ) {
      setError(
        t(
          "Choose at most 5 attachments, up to 8 MB total.",
          "最多选择 5 个附件，总计不超过 8 MB。",
        ),
      );
      return;
    }
    setBusy(true);
    try {
      setAttachments(
        await Promise.all(
          list.map(async (file) => ({
            filename: file.name,
            size: file.size,
            content_base64: await new Promise<string>((resolve, reject) => {
              const reader = new FileReader();
              reader.onload = () =>
                resolve(String(reader.result).split(",")[1]);
              reader.onerror = () =>
                reject(
                  new Error(t("Unable to read attachment.", "无法读取附件。")),
                );
              reader.readAsDataURL(file);
            }),
          })),
        ),
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    if (!review || submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      const latest = await flush();
      if (!latest || latest.revision !== review.revision)
        throw new Error(
          t(
            "The draft changed. Close this review and review the latest version before sending.",
            "草稿已更改，请关闭并重新审核最新版本后发送。",
          ),
        );
      const send = await post<MailSend>("/mail/send", {
        draft_id: draft.id,
        mailbox_id: review.mailbox.id,
        revision: review.revision,
        confirmed: true,
        idempotency_key: review.key,
        mode: review.mode,
        scheduled_at: review.scheduled_at,
        reply_message_id: replyMessageId,
        attachments: review.attachments.map(({ filename, content_base64 }) => ({
          filename,
          content_base64,
        })),
      });
      setResult(send);
      setReview(null);
      if (send.status === "sent" || send.status === "scheduled") {
        notify(
          send.status === "scheduled"
            ? t(
                "Email scheduled. Manage it in Outbox.",
                "邮件已预约，可在发件箱管理。",
              )
            : t("Gmail accepted the email.", "Gmail 已接受邮件。"),
        );
        onSent?.();
      }
    } catch (e) {
      // Keep the same idempotency key on a retry of this reviewed send.
      setError(errorText(e));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <section
      className="panel mail-send"
      aria-label={t("Send with Gmail", "使用 Gmail 发送")}
    >
      <div className="section-head">
        <h2>
          <Send size={17} />
          {t("Send with Gmail", "使用 Gmail 发送")}
        </h2>
        <Nav href="/outbox">{t("Outbox", "发件箱")}</Nav>
      </div>
      {loaded && !mailboxes.length && (
        <p className="notice">
          {t(
            "Connect a Gmail mailbox to send real email.",
            "连接 Gmail 邮箱以发送真实邮件。",
          )}{" "}
          <Nav href="/mailboxes">{t("Connect Gmail", "连接 Gmail")}</Nav>
        </p>
      )}
      <div className="mail-send-fields">
        <Field label={t("Sender · Gmail mailbox", "发件人 · Gmail 邮箱")}>
          <select
            value={sender}
            disabled={disabled || busy || !!mailboxId}
            onChange={(e) => setSender(e.target.value)}
          >
            <option value="">{t("Select a mailbox", "选择邮箱")}</option>
            {mailboxes.map((box) => (
              <option key={box.id} value={box.id}>
                {box.email}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("Delivery", "发送方式")}>
          <select
            value={mode}
            disabled={disabled || busy}
            onChange={(e) => setMode(e.target.value as typeof mode)}
          >
            <option value="send">{t("Send now", "立即发送")}</option>
            <option value="schedule">{t("Schedule", "预约发送")}</option>
            {!replyMessageId && (
              <option value="test">
                {t("Test to my own mailbox", "测试发送至本人邮箱")}
              </option>
            )}
          </select>
        </Field>
        {mode === "schedule" && (
          <Field label={t("Send at · your local time", "发送时间 · 当前时区")}>
            <input
              type="datetime-local"
              value={when}
              disabled={busy || disabled}
              onChange={(e) => setWhen(e.target.value)}
            />
          </Field>
        )}
      </div>
      <Field
        label={t(
          "Attachments · up to 5 files / 8 MB total",
          "附件 · 最多 5 个文件 / 总计 8 MB",
        )}
      >
        <input
          type="file"
          multiple
          disabled={busy || disabled}
          onChange={(e) => void chooseFiles(e.target.files)}
        />
      </Field>
      <p className="mail-hint">
        {t(
          "Sending requires a saved platform contact with an email address. Review the recipient, sender and final content before confirming.",
          "发送需要已保存且有邮箱地址的平台联系人。确认前请审核收件人、发件人及最终正文。",
        )}
      </p>
      {error && !review && (
        <p className="error-panel" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div
          className={
            result.status === "sent" || result.status === "scheduled"
              ? "notice"
              : "error-panel"
          }
          role="status"
        >
          {t("Delivery status:", "投递状态：")} {result.status}
          {result.error && <p>{result.error}</p>}{" "}
          <Nav href="/outbox">{t("View delivery details", "查看投递详情")}</Nav>
        </div>
      )}
      <button
        className="button primary"
        disabled={busy || disabled || !sender || !draft.contact_id}
        onClick={() => void prepare()}
      >
        {busy ? (
          <Busy />
        ) : mode === "schedule" ? (
          <CalendarClock size={16} />
        ) : (
          <Send size={16} />
        )}
        {t("Review & send", "审核并发送")}
      </button>
      {review && (
        <Drawer
          title={t("Confirm Gmail delivery", "确认 Gmail 投递")}
          onClose={() => {
            if (!busy) {
              setReview(null);
              setError("");
            }
          }}
        >
          <div className="mail-review">
            <dl>
              <dt>{t("From", "发件人")}</dt>
              <dd>{review.mailbox.email}</dd>
              <dt>{t("To", "收件人")}</dt>
              <dd>
                {review.mode === "test"
                  ? review.mailbox.email
                  : review.recipient_email}
              </dd>
              <dt>{t("When", "时间")}</dt>
              <dd>
                {review.scheduled_at
                  ? new Date(review.scheduled_at).toLocaleString()
                  : t("Immediately after confirmation", "确认后立即发送")}
              </dd>
              <dt>{t("Subject", "主题")}</dt>
              <dd>
                {review.mode === "test" ? "[Test] " : ""}
                {review.subject}
              </dd>
            </dl>
            {review.mode === "test" && (
              <p className="notice">
                {t(
                  "This test goes only to your own connected mailbox. The final contact will not receive this test.",
                  "本次测试仅发送至您本人连接的邮箱，联系人不会收到此测试。",
                )}
              </p>
            )}
            {replyMessageId && (
              <p className="notice">
                {t(
                  "Replying in the original Gmail conversation.",
                  "将在原 Gmail 会话内回复。",
                )}
              </p>
            )}
            <pre className="mail-body-text">{review.body_text}</pre>
            {review.attachments.length > 0 && (
              <div>
                <strong>{t("Attachments", "附件")}</strong>
                <ul>
                  {review.attachments.map((file, i) => (
                    <li key={i}>
                      {file.filename} · {Math.ceil(file.size / 1024)} KB
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {review.issues?.length > 0 && (
              <div className="error-panel" role="alert">
                {review.issues.map((issue) => (
                  <p key={issue}>{issue}</p>
                ))}
              </div>
            )}
            {error && (
              <div className="error-panel" role="alert">
                {error}
              </div>
            )}
            {draft.status !== "ready" && (
              <button
                className="button"
                disabled={busy}
                onClick={() => void markReady()}
              >
                {busy ? <Busy /> : <Send size={16} />}
                {t("Mark this content reviewed", "标记此内容已审核")}
              </button>
            )}
            <button
              className="button primary"
              disabled={busy || !review.can_send}
              onClick={() => void confirm()}
            >
              {busy ? <Busy /> : <Send size={16} />}
              {review.mode === "schedule"
                ? t("Confirm schedule", "确认预约发送")
                : review.mode === "test"
                  ? t("Confirm test send", "确认发送测试邮件")
                  : t("Confirm send", "确认发送")}
            </button>
          </div>
        </Drawer>
      )}
    </section>
  );
}
