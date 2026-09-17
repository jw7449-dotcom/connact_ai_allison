"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Archive,
  Check,
  Clock,
  Inbox,
  Mail,
  Plus,
  RefreshCw,
  Reply,
  ShieldCheck,
  Unplug,
} from "lucide-react";
import { api, ApiError, errorText, post } from "@/lib/api";
import { useApp } from "@/lib/context";
import type { Draft } from "@/lib/types";
import type {
  MailboxesResponse,
  Mailbox,
  MailMessage,
  MailThread,
  MailSend,
  MailTask,
  Suppression,
} from "@/lib/mail-types";
import { Badge, Busy, Drawer, Empty, Field, Heading, Nav } from "./ui";
import { DraftEditor } from "./email-studio";
import "./mail.css";

const patch = <T,>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body) });
const localDate = (value: string | null | undefined) =>
  value ? new Date(value).toLocaleString() : "—";
function useMailboxes() {
  const [data, setData] = useState<MailboxesResponse | null>(null);
  const [error, setError] = useState("");
  const [errorStatus, setErrorStatus] = useState<number | undefined>();
  const [loading, setLoading] = useState(true);
  const requestVersion = useRef(0);
  const reload = useCallback(async () => {
    const version = ++requestVersion.current;
    setLoading(true);
    try {
      const result = await api<MailboxesResponse>("/mailboxes");
      if (version !== requestVersion.current) return;
      setData(result);
      setError("");
      setErrorStatus(undefined);
    } catch (e) {
      if (version !== requestVersion.current) return;
      setData(null);
      setError(errorText(e));
      setErrorStatus(e instanceof ApiError ? e.status : undefined);
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { data, error, errorStatus, loading, reload };
}

function MailPrivacy() {
  const { t } = useApp();
  return (
    <div className="mail-privacy">
      <ShieldCheck size={19} />
      <div>
        <strong>
          {t("Only your platform contacts", "仅显示平台联系人邮件")}
        </strong>
        <p>
          {t(
            "Gmail grants mailbox-wide access. Connact.ai imports and displays only messages whose exact email address matches a saved contact in this workspace. Other participants' messages in a conversation are filtered out. Message bodies are not sent to AI by default; remote images are not loaded.",
            "Gmail 授权覆盖整个邮箱。本平台仅导入和显示与当前工作区已保存联系人邮箱精确匹配的邮件，同一会话中其他人员的邮件也会过滤。邮件正文默认不会发送给 AI，远程图片不会加载。",
          )}
        </p>
      </div>
    </div>
  );
}

export function Mailboxes() {
  const { t, notify } = useApp();
  const query = useSearchParams();
  const {
    data,
    error: loadError,
    errorStatus,
    loading,
    reload,
  } = useMailboxes();
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [disconnect, setDisconnect] = useState<Mailbox | null>(null);
  const [deleteData, setDeleteData] = useState(false);
  const [settings, setSettings] = useState<Mailbox | null>(null);
  async function connect(mode: "send" | "sync") {
    setBusy("connect");
    setError("");
    try {
      const response = await post<{ authorization_url: string }>(
        "/mailboxes/connect",
        { mode },
      );
      const url = new URL(response.authorization_url);
      if (url.protocol !== "https:" || url.hostname !== "accounts.google.com")
        throw new Error(
          t("Invalid Google authorization URL.", "Google 授权地址无效。"),
        );
      window.location.assign(url.href);
    } catch (e) {
      setError(errorText(e));
      setBusy("");
    }
  }
  async function sync(box: Mailbox) {
    setBusy(box.id);
    setError("");
    try {
      const result = await post<{ status: string; imported?: number }>(
        `/mailboxes/${box.id}/sync`,
      );
      notify(
        result.status === "running" || result.status === "queued"
          ? t("Gmail synchronization started.", "已开始同步 Gmail。")
          : t(
              `Synchronization finished. ${result.imported ?? 0} contact messages imported.`,
              `同步完成，导入 ${result.imported ?? 0} 封联系人邮件。`,
            ),
      );
      await reload();
    } catch (e) {
      setError(errorText(e));
      await reload();
    } finally {
      setBusy("");
    }
  }
  async function revoke() {
    if (!disconnect) return;
    setBusy(disconnect.id);
    setError("");
    try {
      await post(`/mailboxes/${disconnect.id}/disconnect`, {
        delete_data: deleteData,
      });
      setDisconnect(null);
      setDeleteData(false);
      await reload();
      notify(t("Gmail disconnected.", "Gmail 已断开。"));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }
  return (
    <div className="mail-page">
      <Heading
        title={t("Mailboxes", "邮箱")}
        detail={t(
          "Connect multiple Gmail accounts to send email and receive replies.",
          "连接多个 Gmail 账号，发送邮件并接收回复。",
        )}
      >
        <button
          className="button"
          disabled={!!busy || loading}
          onClick={() => void reload()}
        >
          <RefreshCw size={16} />
          {t("Refresh", "刷新")}
        </button>
      </Heading>
      <MailPrivacy />
      {query.get("gmail") === "connected" && (
        <p className="notice" role="status">
          {t(
            "Gmail connected successfully. Sync to import your platform contacts' messages.",
            "Gmail 已连接成功，请同步以导入平台联系人邮件。",
          )}
        </p>
      )}
      {(query.get("error") ||
        (query.get("gmail") && query.get("gmail") !== "connected")) && (
        <p className="error-panel" role="alert">
          {t(
            "Gmail authorization did not complete. Retry the connection, or ask your administrator to check OAuth configuration.",
            "Gmail 授权未完成。请重新连接，或请管理员检查 OAuth 配置。",
          )}
        </p>
      )}
      {loadError && (
        <div className="error-panel" role="alert">
          <strong>
            {t("Unable to check Gmail availability", "无法检查 Gmail 服务状态")}
          </strong>
          <p>
            {errorStatus === 404
              ? t(
                  "The running backend does not provide the Gmail mailbox API (HTTP 404). Ask your administrator to update or restart the backend, then retry.",
                  "当前运行的后端未提供 Gmail 邮箱接口（HTTP 404）。请管理员更新或重启后端，然后重试。",
                )
              : t(
                  "Mailbox information could not be loaded, so Gmail configuration has not been verified. Retry, or ask your administrator to check the service.",
                  "无法加载邮箱信息，尚不能确认 Gmail 配置。请重试，或请管理员检查服务。",
                )}
          </p>
          {errorStatus !== 404 && <p>{loadError}</p>}
          <button
            className="button"
            disabled={loading}
            onClick={() => void reload()}
          >
            {loading ? <Busy /> : <RefreshCw size={16} />}
            {t("Retry mailbox status", "重试邮箱状态")}
          </button>
        </div>
      )}
      {error && (
        <div className="error-panel" role="alert">
          {error}
        </div>
      )}
      <section className="panel mail-card">
        <div className="mail-card-head">
          <Mail size={25} />
          <div>
            <h2>{t("Connect Gmail", "连接 Gmail")}</h2>
            <p>
              {t(
                "Gmail access is separate from signing in with Google.",
                "Gmail 授权与 Google 登录相互独立。",
              )}
            </p>
          </div>
          <Badge tone={data?.configured && !loadError ? "green" : "amber"}>
            {loadError
              ? t("Mailbox service unavailable", "邮箱服务不可用")
              : !data
                ? t("Checking Gmail…", "正在检查 Gmail…")
                : data.configured
                  ? t("OAuth configured", "OAuth 已配置")
                  : t("Setup required", "需要配置")}
          </Badge>
        </div>
        {data && !data.configured && (
          <div className="notice">
            <p>
              {data.unavailable_reason ||
                t(
                  "Your administrator must configure the Google OAuth client, callback URL and token encryption key before a Gmail connection can be created.",
                  "管理员需配置 Google OAuth 客户端、回调地址及令牌加密密钥后，才可连接 Gmail。",
                )}
            </p>
            {data.callback_uri && (
              <p>
                {t("OAuth callback URL:", "OAuth 回调地址：")}{" "}
                <code>{data.callback_uri}</code>
              </p>
            )}
          </div>
        )}
        <div className="mail-actions">
          <button
            className="button primary"
            disabled={!!busy || !data?.configured}
            onClick={() => void connect("sync")}
          >
            {busy === "connect" ? <Busy /> : <Plus size={16} />}
            {t("Connect Gmail · send & receive", "连接 Gmail · 收发邮件")}
          </button>
          <button
            className="button"
            disabled={!!busy || !data?.configured}
            onClick={() => void connect("send")}
          >
            {t("Connect for sending only", "仅授权发送")}
          </button>
        </div>
      </section>
      {!data && !loadError && (
        <div className="boot">
          <Busy /> {t("Loading mailboxes…", "正在加载邮箱…")}
        </div>
      )}
      {data?.mailboxes.map((box) => {
        const canSync =
          box.can_receive ??
          (box.sync_enabled &&
            box.scopes.some(
              (scope) =>
                scope.includes("gmail.readonly") ||
                scope.includes("gmail.modify"),
            ));
        return (
          <section className="panel mail-card" key={box.id}>
            <div className="mail-card-head">
              <span className="mail-gmail-icon">G</span>
              <div>
                <h2>{box.email}</h2>
                <p>
                  {box.display_name || "Gmail"} ·{" "}
                  {canSync
                    ? t("Send & receive", "收发邮件")
                    : t("Sending only", "仅发送")}
                </p>
              </div>
              <Badge
                tone={
                  box.status === "connected" || box.status === "active"
                    ? "green"
                    : "amber"
                }
              >
                {box.status}
              </Badge>
            </div>
            <p className="mail-hint">
              {t("Last sync:", "上次同步：")} {localDate(box.last_sync_at)} ·{" "}
              {t("Sync status:", "同步状态：")} {box.sync_status || "idle"}
            </p>
            {box.last_sync_error && (
              <p className="error-panel" role="alert">
                {box.last_sync_error}
              </p>
            )}
            <div className="mail-actions">
              <button
                className="button"
                disabled={
                  !!busy ||
                  !canSync ||
                  !["connected", "active"].includes(box.status)
                }
                onClick={() => void sync(box)}
              >
                {busy === box.id ? <Busy /> : <RefreshCw size={16} />}
                {t("Sync contact emails", "同步联系人邮件")}
              </button>
              {!canSync && (
                <button
                  className="button"
                  disabled={!!busy || !data.configured}
                  onClick={() => void connect("sync")}
                >
                  {t("Enable receiving", "开通收件")}
                </button>
              )}
              {!["connected", "active"].includes(box.status) && (
                <button
                  className="button"
                  disabled={!!busy || !data.configured}
                  onClick={() => void connect(canSync ? "sync" : "send")}
                >
                  {t("Reconnect Gmail", "重新连接 Gmail")}
                </button>
              )}
              <Nav href={`/inbox?mailbox=${box.id}`}>
                {t("Open inbox", "打开收件箱")}
              </Nav>
              <button
                className="text-button mail-danger"
                disabled={!!busy || box.status === "disconnected"}
                onClick={() => {
                  setDisconnect(box);
                  setDeleteData(false);
                }}
              >
                <Unplug size={15} />
                {t("Disconnect", "断开连接")}
              </button>
            </div>
          </section>
        );
      })}
      {disconnect && (
        <Drawer
          title={t("Disconnect Gmail", "断开 Gmail")}
          onClose={() => {
            if (!busy) setDisconnect(null);
          }}
        >
          <div className="mail-review">
            <h2>{disconnect.email}</h2>
            <p>
              {t(
                "Disconnecting removes stored access tokens, stops synchronization and cancels pending deliveries from this mailbox.",
                "断开后将移除保存的授权令牌、停止同步，并取消此邮箱的待发送邮件。",
              )}
            </p>
            <label className="mail-check">
              <input
                type="checkbox"
                checked={deleteData}
                onChange={(e) => setDeleteData(e.target.checked)}
              />
              {t(
                "Also delete this mailbox's imported email data from Connact.ai",
                "同时删除本平台中此邮箱已导入的邮件数据",
              )}
            </label>
            <p>
              {t(
                "To remove Google's authorization grant as well, open ",
                "如需同时撤销 Google 账号中的授权，请打开 ",
              )}
              <a
                href="https://myaccount.google.com/connections"
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("Google Account connections", "Google 账号连接管理")}
              </a>
              {t(".", "。")}
            </p>
            {error && (
              <p className="error-panel" role="alert">
                {error}
              </p>
            )}
            <button
              className="button"
              disabled={!!busy}
              onClick={() => void revoke()}
            >
              {busy ? <Busy /> : <Unplug size={16} />}
              {t("Confirm disconnect", "确认断开")}
            </button>
          </div>
        </Drawer>
      )}
      {data?.mailboxes.length ? (
        <section className="panel mail-card">
          <h2>{t("Sender settings", "发件人设置")}</h2>
          <p className="mail-hint">
            {t(
              "Set each mailbox's signature, timezone and sending hours. The signature appears in the final delivery preview.",
              "为每个邮箱设置签名、时区及发送时段。签名将在最终投递预览中显示。",
            )}
          </p>
          <div className="mail-actions">
            {data.mailboxes.map((box) => (
              <button
                className="button"
                key={box.id}
                onClick={() => setSettings(box)}
              >
                {box.email}
              </button>
            ))}
          </div>
        </section>
      ) : null}
      {settings && (
        <MailboxSettings
          box={settings}
          onClose={() => setSettings(null)}
          onSaved={() => {
            setSettings(null);
            void reload();
          }}
        />
      )}
    </div>
  );
}

function MailboxSettings({
  box,
  onClose,
  onSaved,
}: {
  box: Mailbox;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useApp();
  const [signature, setSignature] = useState("");
  const [timezone, setTimezone] = useState(
    box.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  );
  const [start, setStart] = useState(box.send_window_start ?? 0);
  const [end, setEnd] = useState(box.send_window_end ?? 24);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setSignature(
      new DOMParser()
        .parseFromString(
          (box.signature_html || "")
            .replace(/<br\s*\/?>/gi, "\n")
            .replace(/<\/(p|div)>/gi, "\n"),
          "text/html",
        )
        .body.textContent?.trim() || "",
    );
  }, [box.signature_html]);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      new Intl.DateTimeFormat("en", { timeZone: timezone }).format();
      if (start >= end)
        throw new Error(
          t(
            "The sending window must end after it starts.",
            "发送时段的结束时间必须晚于开始时间。",
          ),
        );
      const signature_html = signature
        ? `<p>${signature.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>")}</p>`
        : "";
      await patch(`/mailboxes/${box.id}`, {
        signature_html,
        timezone,
        send_window_start: start,
        send_window_end: end,
      });
      onSaved();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Drawer
      title={t("Gmail sender settings", "Gmail 发件人设置")}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <form className="mail-review" onSubmit={(e) => void save(e)}>
        <h2>{box.email}</h2>
        <Field label={t("Email signature", "邮件签名")}>
          <textarea
            maxLength={10000}
            rows={5}
            value={signature}
            onChange={(e) => setSignature(e.target.value)}
          />
        </Field>
        <Field label={t("Timezone · IANA name", "时区 · IANA 名称")}>
          <input
            required
            value={timezone}
            placeholder="Asia/Shanghai"
            onChange={(e) => setTimezone(e.target.value)}
          />
        </Field>
        <Field label={t("Sending window starts · hour", "发送时段开始 · 小时")}>
          <input
            type="number"
            min={0}
            max={23}
            required
            value={start}
            onChange={(e) => setStart(Number(e.target.value))}
          />
        </Field>
        <Field label={t("Sending window ends · hour", "发送时段结束 · 小时")}>
          <input
            type="number"
            min={1}
            max={24}
            required
            value={end}
            onChange={(e) => setEnd(Number(e.target.value))}
          />
        </Field>
        <p className="mail-hint">
          {t(
            "0–24 allows sending all day. Scheduled delivery follows this mailbox's timezone and allowed hours.",
            "0–24 表示全天可发送。预约邮件遵循此邮箱时区与允许发送时段。",
          )}
        </p>
        {error && (
          <p className="error-panel" role="alert">
            {error}
          </p>
        )}
        <button className="button primary" disabled={busy}>
          {busy ? <Busy /> : <Check size={16} />}
          {t("Save sender settings", "保存发件人设置")}
        </button>
      </form>
    </Drawer>
  );
}

export function MailInbox() {
  const { t, contacts, notify, refresh, guard } = useApp();
  const query = useSearchParams();
  const { data, error: mailboxError, reload: reloadMailboxes } = useMailboxes();
  const [mailbox, setMailbox] = useState(query.get("mailbox") || "");
  const [folder, setFolder] = useState("inbox");
  const [unread, setUnread] = useState(false);
  const [pendingReply, setPendingReply] = useState(false);
  const [intentFilter, setIntentFilter] = useState("");
  const [addressInput, setAddressInput] = useState({ email: "", domain: "" });
  const [addressFilter, setAddressFilter] = useState({ email: "", domain: "" });
  const [messages, setMessages] = useState<MailMessage[]>([]);
  const [selected, setSelected] = useState<MailMessage | null>(null);
  const [thread, setThread] = useState<MailThread | null>(null);
  const [notes, setNotes] = useState("");
  const [intent, setIntent] = useState("none");
  const [suppressed, setSuppressed] = useState<Suppression[]>([]);
  const [tasks, setTasks] = useState<MailTask[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const pageController = useRef<AbortController | null>(null);
  const [version, setVersion] = useState(0);
  const [replyDraft, setReplyDraft] = useState<{
    id: string;
    message: MailMessage;
  } | null>(null);
  const [taskFor, setTaskFor] = useState<MailMessage | null>(null);
  const [suppressFor, setSuppressFor] = useState<MailMessage | null>(null);
  const parameters = new URLSearchParams({ folder, limit: "200" });
  if (mailbox) parameters.set("mailbox_id", mailbox);
  if (unread) parameters.set("unread", "true");
  if (pendingReply) parameters.set("pending_reply", "true");
  if (intentFilter) parameters.set("intent", intentFilter);
  if (addressFilter.email) parameters.set("email", addressFilter.email);
  if (addressFilter.domain) parameters.set("domain", addressFilter.domain);
  const messageQuery = parameters.toString();
  useEffect(() => {
    const controller = new AbortController();
    pageController.current = controller;
    setLoaded(false);
    setLoadingMore(false);
    setHasMore(false);
    setError("");
    setMessages([]);
    setSelected(null);
    setThread(null);
    Promise.all([
      api<MailMessage[]>("/mail/messages?" + messageQuery + "&offset=0", {
        signal: controller.signal,
      }),
      api<Suppression[]>("/mail/suppressions", { signal: controller.signal }),
      api<MailTask[]>("/mail/tasks", { signal: controller.signal }),
    ])
      .then(([items, blocks, followups]) => {
        if (controller.signal.aborted) return;
        setMessages(items);
        setHasMore(items.length === 200);
        setSuppressed(blocks);
        setTasks(followups);
        setLoaded(true);
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          setError(errorText(e));
          setLoaded(true);
        }
      });
    return () => controller.abort();
  }, [messageQuery, version]);
  async function loadMore() {
    const controller = pageController.current;
    if (!controller || controller.signal.aborted || loadingMore || !hasMore)
      return;
    setLoadingMore(true);
    setError("");
    try {
      const items = await api<MailMessage[]>(
        "/mail/messages?" + messageQuery + "&offset=" + messages.length,
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      setMessages((current) => {
        const ids = new Set(current.map((item) => item.id));
        return [...current, ...items.filter((item) => !ids.has(item.id))];
      });
      setHasMore(items.length === 200);
    } catch (e) {
      if (!controller.signal.aborted) setError(errorText(e));
    } finally {
      if (!controller.signal.aborted) setLoadingMore(false);
    }
  }
  function clearFilters() {
    setAddressInput({ email: "", domain: "" });
    setAddressFilter({ email: "", domain: "" });
    setPendingReply(false);
    setIntentFilter("");
    setUnread(false);
  }
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    setThread(null);
    setError("");
    api<MailThread>(
      `/mail/threads/${encodeURIComponent(selected.gmail_thread_id)}?mailbox_id=${encodeURIComponent(selected.mailbox_id)}`,
      { signal: controller.signal },
    )
      .then((result) => {
        setThread(result);
        setNotes(result.notes || "");
        setIntent(result.intent || "none");
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorText(e));
      });
    return () => controller.abort();
  }, [selected]);
  async function sync() {
    setBusy("sync");
    setError("");
    const boxes = (data?.mailboxes || []).filter(
      (box) =>
        (!mailbox || box.id === mailbox) &&
        ["connected", "active"].includes(box.status) &&
        (box.can_receive ??
          (box.sync_enabled &&
            box.scopes.some((scope) =>
              /gmail\.(readonly|modify)/.test(scope),
            ))),
    );
    try {
      if (!boxes.length)
        throw new Error(
          t(
            "Connect Gmail with receiving access in Mailboxes first.",
            "请先在邮箱页面连接 Gmail 并授权收件。",
          ),
        );
      for (const box of boxes) await post(`/mailboxes/${box.id}/sync`);
      setVersion((v) => v + 1);
      await reloadMailboxes();
      notify(
        t("Contact email synchronization finished.", "联系人邮件同步已完成。"),
      );
    } catch (e) {
      setError(errorText(e));
      await reloadMailboxes();
    } finally {
      setBusy("");
    }
  }
  async function updateMessage(
    message: MailMessage,
    body: { is_unread?: boolean; is_archived?: boolean },
  ) {
    setBusy(message.id);
    setError("");
    try {
      const updated = await patch<MailMessage>(
        `/mail/messages/${message.id}`,
        body,
      );
      setMessages((items) =>
        items
          .map((item) => (item.id === updated.id ? updated : item))
          .filter(
            (item) =>
              (!unread || item.is_unread) &&
              (folder !== "inbox" || !item.is_archived) &&
              (folder !== "archive" || item.is_archived),
          ),
      );
      setThread(
        (previous) =>
          previous && {
            ...previous,
            messages: previous.messages.map((item) =>
              item.id === updated.id ? updated : item,
            ),
          },
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }
  async function saveThread() {
    if (!selected) return;
    setBusy("notes");
    setError("");
    try {
      await patch(
        `/mail/threads/${encodeURIComponent(selected.gmail_thread_id)}?mailbox_id=${encodeURIComponent(selected.mailbox_id)}`,
        { notes, intent },
      );
      setSuppressed(await api<Suppression[]>("/mail/suppressions"));
      notify(t("Conversation notes saved.", "会话备注已保存。"));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }
  async function reply(message: MailMessage) {
    setBusy("reply");
    setError("");
    try {
      if (guard.current) await guard.current();
      const d = await post<Draft>("/drafts", {
        contact_id: message.contact_id,
        subject: /^re:/i.test(message.subject)
          ? message.subject
          : `Re: ${message.subject}`,
      });
      await refresh();
      setReplyDraft({ id: d.id, message });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }
  const incoming = thread?.messages
    .filter(
      (message) =>
        message.direction === "inbound" || message.direction === "incoming",
    )
    .at(-1);
  const contact = contacts.find((c) => c.id === selected?.contact_id);
  const suppression = suppressed.find(
    (entry) => entry.contact_id === selected?.contact_id,
  );
  const pendingTasks = tasks.filter(
    (task) =>
      task.status === "pending" && task.contact_id === selected?.contact_id,
  );
  return (
    <div className="mail-page">
      <Heading
        title={t("Inbox", "收件箱")}
        detail={t(
          "Read and reply to saved platform contacts in their original Gmail conversations.",
          "查看已保存平台联系人的邮件，并在原 Gmail 会话中回复。",
        )}
      >
        <Nav href="/mailboxes">{t("Manage mailboxes", "管理邮箱")}</Nav>
        <button
          className="button primary"
          disabled={!!busy}
          onClick={() => void sync()}
        >
          {busy === "sync" ? <Busy /> : <RefreshCw size={16} />}
          {t("Sync now", "立即同步")}
        </button>
      </Heading>
      <MailPrivacy />
      {(error || mailboxError) && (
        <div className="error-panel" role="alert">
          {error || mailboxError}
          <button
            className="text-button"
            onClick={() => {
              setVersion((v) => v + 1);
              void reloadMailboxes();
            }}
          >
            {t("Refresh", "刷新")}
          </button>
        </div>
      )}
      {(data?.mailboxes || [])
        .filter(
          (box) => (!mailbox || box.id === mailbox) && box.last_sync_error,
        )
        .map((box) => (
          <p className="error-panel" key={box.id}>
            {box.email}: {box.last_sync_error}
          </p>
        ))}
      <form
        className="mail-toolbar"
        aria-label={t("Inbox filters", "收件箱筛选")}
        onSubmit={(event) => {
          event.preventDefault();
          setAddressFilter({
            email: addressInput.email.trim().toLowerCase(),
            domain: addressInput.domain.trim().toLowerCase().replace(/^@/, ""),
          });
          setVersion((current) => current + 1);
        }}
      >
        <Field label={t("Mailbox", "邮箱")}>
          <select value={mailbox} onChange={(e) => setMailbox(e.target.value)}>
            <option value="">
              {t("All connected mailboxes", "全部已连接邮箱")}
            </option>
            {data?.mailboxes.map((box) => (
              <option key={box.id} value={box.id}>
                {box.email}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("Contact email · exact", "联系人邮箱 · 精确匹配")}>
          <input
            type="search"
            autoComplete="off"
            value={addressInput.email}
            placeholder="contact@example.com"
            onChange={(e) =>
              setAddressInput((current) => ({
                ...current,
                email: e.target.value,
              }))
            }
          />
        </Field>
        <Field label={t("Email domain · exact", "邮箱域名 · 精确匹配")}>
          <input
            type="search"
            autoComplete="off"
            value={addressInput.domain}
            placeholder="example.com"
            onChange={(e) =>
              setAddressInput((current) => ({
                ...current,
                domain: e.target.value,
              }))
            }
          />
        </Field>
        <Field label={t("Intent filter", "意向筛选")}>
          <select
            value={intentFilter}
            onChange={(e) => setIntentFilter(e.target.value)}
          >
            <option value="">{t("All intents", "全部意向")}</option>
            <option value="none">{t("Unclassified", "未分类")}</option>
            <option value="interested">{t("Interested", "有兴趣")}</option>
            <option value="not_now">{t("Not now", "暂时不考虑")}</option>
            <option value="not_interested">
              {t("Not interested", "无兴趣")}
            </option>
          </select>
        </Field>
        <Field label={t("Folder", "文件夹")}>
          <select value={folder} onChange={(e) => setFolder(e.target.value)}>
            <option value="inbox">{t("Inbox", "收件箱")}</option>
            <option value="sent">{t("Sent", "已发送")}</option>
            <option value="archive">{t("Archived", "已归档")}</option>
            <option value="all">
              {t("All contact mail", "全部联系人邮件")}
            </option>
          </select>
        </Field>
        <label className="mail-check">
          <input
            type="checkbox"
            checked={unread}
            onChange={(e) => setUnread(e.target.checked)}
          />
          {t("Unread only", "仅未读")}
        </label>
        <label className="mail-check">
          <input
            type="checkbox"
            checked={pendingReply}
            onChange={(e) => setPendingReply(e.target.checked)}
          />
          {t("Awaiting my reply", "待我回复")}
        </label>
        <button type="submit" className="button">
          {t("Apply filters", "应用筛选")}
        </button>
        <button type="button" className="text-button" onClick={clearFilters}>
          {t("Clear filters", "清除筛选")}
        </button>
      </form>
      <div className="mail-inbox-layout">
        <section
          className="panel mail-message-list"
          aria-label={t("Contact messages", "联系人邮件")}
        >
          {!loaded ? (
            <div className="empty">
              <Busy /> {t("Loading messages…", "正在加载邮件…")}
            </div>
          ) : !messages.length ? (
            <Empty
              title={t("No contact emails here", "暂无联系人邮件")}
              detail={t(
                addressFilter.email ||
                  addressFilter.domain ||
                  intentFilter ||
                  pendingReply ||
                  unread
                  ? "No saved-contact messages match these filters. Adjust or clear the filters to see other contact emails."
                  : "Save a contact with an exact email address, connect Gmail with receiving access, then sync.",
                addressFilter.email ||
                  addressFilter.domain ||
                  intentFilter ||
                  pendingReply ||
                  unread
                  ? "没有已保存联系人的邮件符合当前筛选。调整或清除筛选可查看其他联系人邮件。"
                  : "保存带有准确邮箱地址的联系人，连接 Gmail 并授权收件，然后同步。",
              )}
            >
              <Nav href="/contacts">{t("View contacts", "查看联系人")}</Nav>
            </Empty>
          ) : (
            messages.map((message) => (
              <button
                className={`mail-message-tile ${selected?.id === message.id ? "selected" : ""} ${message.is_unread ? "unread" : ""}`}
                key={message.id}
                onClick={() => setSelected(message)}
              >
                <div>
                  <strong>
                    {contacts.find((c) => c.id === message.contact_id)?.name ||
                      message.contact_email}
                  </strong>
                  <small>{localDate(message.received_at)}</small>
                </div>
                <b>{message.subject || t("(No subject)", "（无主题）")}</b>
                <p>{message.snippet}</p>
                <small>
                  {message.from_email}
                  {message.is_unread && ` · ${t("Unread", "未读")}`}
                </small>
              </button>
            ))
          )}
          {loaded && messages.length > 0 && (
            <div className="mail-pagination">
              <span>
                {t(
                  `${messages.length} contact messages loaded`,
                  `已加载 ${messages.length} 封联系人邮件`,
                )}
              </span>
              {hasMore && (
                <button
                  className="button"
                  disabled={loadingMore}
                  onClick={() => void loadMore()}
                >
                  {loadingMore ? <Busy /> : <Plus size={15} />}
                  {t("Load more messages", "加载更多邮件")}
                </button>
              )}
            </div>
          )}
        </section>
        <section
          className="panel mail-thread"
          aria-label={t("Email conversation", "邮件会话")}
        >
          {!selected ? (
            <Empty
              title={t("Select a conversation", "选择会话")}
              detail={t(
                "Only saved contacts' messages are available here.",
                "这里仅提供已保存联系人的邮件。",
              )}
            />
          ) : !thread ? (
            <div className="empty">
              <Busy /> {t("Opening conversation…", "正在打开会话…")}
            </div>
          ) : (
            <>
              <div className="mail-thread-heading">
                <h2>{selected.subject || t("(No subject)", "（无主题）")}</h2>
                <p>
                  {contact?.name || selected.contact_email} ·{" "}
                  {
                    data?.mailboxes.find(
                      (box) => box.id === selected.mailbox_id,
                    )?.email
                  }
                </p>
                {!!incoming && pendingTasks.length > 0 && (
                  <p className="notice">
                    {t(
                      `This contact has ${pendingTasks.length} pending manual follow-up task(s). Review them after reading the reply.`,
                      `此联系人还有 ${pendingTasks.length} 个待处理的手动跟进任务，请读完回复后检查。`,
                    )}{" "}
                    <Nav href="/followups">
                      {t("Review follow-ups", "查看跟进任务")}
                    </Nav>
                  </p>
                )}
                <div className="mail-actions">
                  <button
                    className="button primary"
                    disabled={!!busy || !incoming || !!suppression}
                    onClick={() => incoming && void reply(incoming)}
                  >
                    <Reply size={16} />
                    {t("Reply in Gmail thread", "在原 Gmail 会话回复")}
                  </button>
                  <button
                    className="button"
                    disabled={!!busy}
                    onClick={() => setTaskFor(selected)}
                  >
                    <Clock size={16} />
                    {t("Add follow-up", "添加跟进任务")}
                  </button>
                  <button
                    className="text-button mail-danger"
                    disabled={!!busy || !!suppression}
                    onClick={() => setSuppressFor(selected)}
                  >
                    {t("Stop contacting", "停止联系")}
                  </button>
                </div>
                {suppression && (
                  <p className="notice">
                    {t(
                      "This contact is suppressed. Sending is blocked.",
                      "此联系人已停止联系，邮件发送已被阻止。",
                    )}{" "}
                    <Nav href="/followups">
                      {t("Manage suppression", "管理停止联系")}
                    </Nav>
                  </p>
                )}
              </div>
              <div className="mail-thread-messages">
                {thread.messages.map((message) => (
                  <article key={message.id} className="mail-message">
                    <header>
                      <div>
                        <strong>{message.from_email}</strong>
                        <p>
                          {t("To:", "收件人：")}{" "}
                          {(message.to_emails || []).join(", ")}
                        </p>
                        <small>{localDate(message.received_at)}</small>
                      </div>
                      <div className="mail-actions">
                        <button
                          className="text-button"
                          disabled={!!busy}
                          onClick={() =>
                            void updateMessage(message, {
                              is_unread: !message.is_unread,
                            })
                          }
                        >
                          {message.is_unread
                            ? t("Mark read", "标为已读")
                            : t("Mark unread", "标为未读")}
                        </button>
                        <button
                          className="text-button"
                          disabled={!!busy}
                          onClick={() =>
                            void updateMessage(message, {
                              is_archived: !message.is_archived,
                            })
                          }
                        >
                          <Archive size={14} />
                          {message.is_archived
                            ? t("Restore", "恢复")
                            : t("Archive", "归档")}
                        </button>
                      </div>
                    </header>
                    <pre className="mail-body-text">
                      {message.body_text ||
                        message.snippet ||
                        t("No text content.", "无文字内容。")}
                    </pre>
                    {message.attachments?.length > 0 && (
                      <p className="mail-hint">
                        {t("Attachments:", "附件：")}{" "}
                        {message.attachments.map((item) => (
                          <a
                            key={item.id}
                            href={`/api/mail/messages/${encodeURIComponent(message.id)}/attachments/${encodeURIComponent(item.id)}`}
                            download
                          >
                            {item.filename || item.name || "Attachment"}
                            {item.size
                              ? ` (${Math.ceil(item.size / 1024)} KB)`
                              : ""}{" "}
                          </a>
                        ))}
                      </p>
                    )}
                  </article>
                ))}
              </div>
              <div className="mail-thread-notes">
                <h3>{t("Conversation notes", "会话备注")}</h3>
                <Field label={t("Contact intent", "联系人意向")}>
                  <select
                    value={intent}
                    onChange={(e) => setIntent(e.target.value)}
                  >
                    <option value="none">{t("Unclassified", "未分类")}</option>
                    <option value="interested">
                      {t("Interested", "有兴趣")}
                    </option>
                    <option value="not_now">
                      {t("Not now", "暂时不考虑")}
                    </option>
                    <option value="not_interested">
                      {t("Not interested", "无兴趣")}
                    </option>
                  </select>
                </Field>
                {intent === "not_interested" && (
                  <p className="notice">
                    {t(
                      "Saving Not interested also blocks further contact and pending deliveries.",
                      "保存“无兴趣”将同时阻止后续联系和待发送邮件。",
                    )}
                  </p>
                )}
                <Field label={t("Private workspace notes", "工作区内部备注")}>
                  <textarea
                    rows={3}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                  />
                </Field>
                <button
                  className="button"
                  disabled={!!busy}
                  onClick={() => void saveThread()}
                >
                  {busy === "notes" ? <Busy /> : <Check size={15} />}
                  {t("Save notes", "保存备注")}
                </button>
              </div>
            </>
          )}
        </section>
      </div>
      {replyDraft && (
        <Drawer
          title={t("Reply in original conversation", "在原会话中回复")}
          onClose={() => {
            void (async () => {
              try {
                if (guard.current) await guard.current();
                setReplyDraft(null);
              } catch (e) {
                notify(errorText(e));
              }
            })();
          }}
        >
          <div className="mail-reply-editor">
            <p className="notice">
              {t(
                "This reply stays with the original contact and Gmail conversation. Incoming email content is not passed to AI.",
                "此回复绑定原联系人及 Gmail 会话。收到的邮件正文不会传给 AI。",
              )}
            </p>
            <DraftEditor
              key={replyDraft.id}
              id={replyDraft.id}
              replySubject={
                /^re:/i.test(replyDraft.message.subject)
                  ? replyDraft.message.subject
                  : `Re: ${replyDraft.message.subject}`
              }
              replyMessageId={replyDraft.message.id}
              mailboxId={replyDraft.message.mailbox_id}
              onSent={() => {
                setReplyDraft(null);
                setVersion((v) => v + 1);
              }}
            />
          </div>
        </Drawer>
      )}
      {taskFor && (
        <TaskEditor
          contactId={taskFor.contact_id}
          mailboxId={taskFor.mailbox_id}
          threadId={taskFor.gmail_thread_id}
          onClose={() => setTaskFor(null)}
          onSaved={() => {
            setTaskFor(null);
            void api<MailTask[]>("/mail/tasks")
              .then(setTasks)
              .catch((e) => notify(errorText(e)));
            notify(t("Manual follow-up created.", "手动跟进任务已创建。"));
          }}
        />
      )}
      {suppressFor && (
        <SuppressionEditor
          contactId={suppressFor.contact_id}
          onClose={() => setSuppressFor(null)}
          onSaved={(entry) => {
            setSuppressed((items) => [...items, entry]);
            setSuppressFor(null);
          }}
        />
      )}
    </div>
  );
}

export function Outbox() {
  const { t } = useApp();
  const [sends, setSends] = useState<MailSend[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [resume, setResume] = useState<MailSend | null>(null);
  const reload = useCallback(async () => {
    try {
      setSends(await api<MailSend[]>("/mail/sends"));
      setError("");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoaded(true);
    }
  }, []);
  useEffect(() => {
    void reload();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") void reload();
    }, 20000);
    return () => clearInterval(timer);
  }, [reload]);
  async function action(send: MailSend, action: string) {
    setBusy(send.id);
    setError("");
    try {
      await post(
        `/mail/sends/${send.id}/${action}`,
        action === "resume" ? { confirmed: true } : {},
      );
      setResume(null);
      await reload();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }
  return (
    <div className="mail-page">
      <Heading
        title={t("Outbox", "发件箱")}
        detail={t(
          "Review delivery results and manage emails you scheduled. Incoming replies pause unsent outreach to that contact.",
          "查看投递结果并管理已预约的邮件。联系人回复后，发给该联系人的待发送邮件将暂停。",
        )}
      >
        <button className="button" onClick={() => void reload()}>
          <RefreshCw size={16} />
          {t("Refresh", "刷新")}
        </button>
        <Nav href="/email">{t("Write email", "撰写邮件")}</Nav>
      </Heading>
      {error && (
        <p className="error-panel" role="alert">
          {error}
        </p>
      )}
      <section className="panel mail-card">
        {!loaded ? (
          <div className="empty">
            <Busy />
          </div>
        ) : !sends.length ? (
          <Empty
            title={t("No deliveries yet", "暂无投递记录")}
            detail={t(
              "Send or schedule a reviewed draft in Email Studio.",
              "在邮件工作室审核草稿后发送或预约发送。",
            )}
          />
        ) : (
          <div className="mail-deliveries">
            {sends.map((send) => (
              <article key={send.id} className="mail-delivery">
                <div className="mail-card-head">
                  <div>
                    <h3>{send.subject}</h3>
                    <p>
                      {send.mailbox_email} → {send.recipient_email}
                    </p>
                  </div>
                  <Badge
                    tone={
                      send.status === "sent"
                        ? "green"
                        : ["failed", "uncertain", "blocked", "paused"].includes(
                              send.status,
                            )
                          ? "amber"
                          : "gray"
                    }
                  >
                    {send.status}
                  </Badge>
                </div>
                <p className="mail-hint">
                  {send.sent_at
                    ? t("Sent:", "已发送：")
                    : send.scheduled_at
                      ? t("Scheduled:", "预约时间：")
                      : t("Created:", "创建时间：")}{" "}
                  {localDate(
                    send.sent_at || send.scheduled_at || send.created_at,
                  )}
                </p>
                {send.error && <p className="notice">{send.error}</p>}
                {send.status === "uncertain" && (
                  <p className="notice">
                    {t(
                      "Delivery could not be confirmed. Check Gmail Sent before composing another send; this delivery is not automatically retried.",
                      "无法确认投递结果，请先检查 Gmail 已发送文件夹再发起其他发送；此邮件不会自动重试。",
                    )}
                  </p>
                )}
                <div className="mail-actions">
                  {["scheduled", "queued"].includes(send.status) && (
                    <button
                      className="button"
                      disabled={!!busy}
                      onClick={() => void action(send, "pause")}
                    >
                      {t("Pause", "暂停")}
                    </button>
                  )}
                  {["paused", "blocked"].includes(send.status) &&
                    send.mode === "schedule" && (
                      <button
                        className="button"
                        disabled={!!busy}
                        onClick={() => setResume(send)}
                      >
                        {t("Review & resume", "审核并恢复")}
                      </button>
                    )}
                  {["scheduled", "paused", "blocked"].includes(send.status) && (
                    <button
                      className="text-button mail-danger"
                      disabled={!!busy}
                      onClick={() => void action(send, "cancel")}
                    >
                      {t("Cancel delivery", "取消投递")}
                    </button>
                  )}
                  <Nav href={`/email?draft=${send.draft_id}`}>
                    {t("Open source draft", "打开原草稿")}
                  </Nav>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
      {resume && (
        <Drawer
          title={t("Resume scheduled delivery", "恢复预约发送")}
          onClose={() => {
            if (!busy) setResume(null);
          }}
        >
          <div className="mail-review">
            <dl>
              <dt>{t("From", "发件人")}</dt>
              <dd>{resume.mailbox_email}</dd>
              <dt>{t("To", "收件人")}</dt>
              <dd>{resume.recipient_email}</dd>
              <dt>{t("Subject", "主题")}</dt>
              <dd>{resume.subject}</dd>
              <dt>{t("Scheduled", "预约时间")}</dt>
              <dd>{localDate(resume.scheduled_at)}</dd>
            </dl>
            <p className="notice">
              {t(
                "If the scheduled time has passed, resuming makes this delivery eligible to send now. Review the contact's latest reply before proceeding.",
                "如果预约时间已过，恢复后此邮件将可以立即发送。请先检查联系人的最新回复。",
              )}
            </p>
            {resume.body_text && (
              <pre className="mail-body-text">{resume.body_text}</pre>
            )}
            {resume.attachments && resume.attachments.length > 0 && (
              <div>
                <strong>{t("Attachments", "附件")}</strong>
                <ul>
                  {resume.attachments.map((item, i) => (
                    <li key={i}>
                      {item.filename} · {Math.ceil(item.size / 1024)} KB
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {error && (
              <p className="error-panel" role="alert">
                {error}
              </p>
            )}
            <button
              className="button primary"
              disabled={!!busy}
              onClick={() => void action(resume, "resume")}
            >
              {busy ? <Busy /> : <Check size={16} />}
              {t("Confirm resume", "确认恢复发送")}
            </button>
          </div>
        </Drawer>
      )}
    </div>
  );
}

function TaskEditor({
  contactId,
  mailboxId,
  threadId,
  onClose,
  onSaved,
}: {
  contactId?: string;
  mailboxId?: string;
  threadId?: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t, contacts } = useApp();
  const [contact, setContact] = useState(contactId || "");
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await post("/mail/tasks", {
        contact_id: contact,
        mailbox_id: mailboxId,
        thread_id: threadId,
        title,
        due_at: new Date(due).toISOString(),
        notes,
        status: "pending",
      });
      onSaved();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Drawer
      title={t("Add manual follow-up", "添加手动跟进")}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <form className="mail-review" onSubmit={(e) => void save(e)}>
        <p className="notice">
          {t(
            "A follow-up is a task for you. It does not automatically generate or send an email.",
            "跟进是供您处理的任务，不会自动生成或发送邮件。",
          )}
        </p>
        <Field label={t("Contact", "联系人")}>
          <select
            required
            disabled={!!contactId || busy}
            value={contact}
            onChange={(e) => setContact(e.target.value)}
          >
            <option value="">{t("Choose contact", "选择联系人")}</option>
            {contacts
              .filter((c) => c.saved)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} · {c.email}
                </option>
              ))}
          </select>
        </Field>
        <Field label={t("Task", "任务")}>
          <input
            required
            maxLength={250}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <Field label={t("Due · your local time", "截止时间 · 当前时区")}>
          <input
            type="datetime-local"
            required
            value={due}
            onChange={(e) => setDue(e.target.value)}
          />
        </Field>
        <Field label={t("Notes", "备注")}>
          <textarea
            rows={3}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </Field>
        {error && (
          <p className="error-panel" role="alert">
            {error}
          </p>
        )}
        <button className="button primary" disabled={busy} type="submit">
          {busy ? <Busy /> : <Plus size={16} />}
          {t("Create follow-up", "创建跟进")}
        </button>
      </form>
    </Drawer>
  );
}

function SuppressionEditor({
  contactId,
  onClose,
  onSaved,
}: {
  contactId?: string;
  onClose: () => void;
  onSaved: (entry: Suppression) => void;
}) {
  const { t, contacts } = useApp();
  const [contact, setContact] = useState(contactId || "");
  const [reason, setReason] = useState("manual");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      onSaved(
        await post<Suppression>("/mail/suppressions", {
          contact_id: contact,
          reason,
          notes,
        }),
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Drawer
      title={t("Stop contacting", "停止联系")}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <form className="mail-review" onSubmit={(e) => void save(e)}>
        <p>
          {t(
            "Block new sends and scheduled outreach to this email address in the current workspace.",
            "在当前工作区阻止向此邮箱地址发送新邮件及预约外联邮件。",
          )}
        </p>
        <Field label={t("Contact", "联系人")}>
          <select
            required
            disabled={!!contactId || busy}
            value={contact}
            onChange={(e) => setContact(e.target.value)}
          >
            <option value="">{t("Choose contact", "选择联系人")}</option>
            {contacts
              .filter((c) => c.saved && c.email)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} · {c.email}
                </option>
              ))}
          </select>
        </Field>
        <Field label={t("Reason", "原因")}>
          <select value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="manual">{t("Manual stop", "手动停止")}</option>
            <option value="unsubscribe">{t("Unsubscribed", "退订")}</option>
            <option value="rejection">
              {t("Rejected contact", "拒绝联系")}
            </option>
            <option value="hard_bounce">{t("Hard bounce", "永久退信")}</option>
          </select>
        </Field>
        <Field label={t("Notes", "备注")}>
          <textarea
            rows={3}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </Field>
        {error && (
          <p className="error-panel" role="alert">
            {error}
          </p>
        )}
        <button className="button" disabled={busy} type="submit">
          {busy ? <Busy /> : <ShieldCheck size={16} />}
          {t("Confirm stop contacting", "确认停止联系")}
        </button>
      </form>
    </Drawer>
  );
}

export function Followups() {
  const { t, contacts } = useApp();
  const [tasks, setTasks] = useState<MailTask[]>([]);
  const [suppressed, setSuppressed] = useState<Suppression[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [create, setCreate] = useState(false);
  const [suppress, setSuppress] = useState(false);
  const [release, setRelease] = useState<Suppression | null>(null);
  const [loaded, setLoaded] = useState(false);
  const reload = useCallback(async () => {
    try {
      const [todo, blocks] = await Promise.all([
        api<MailTask[]>("/mail/tasks"),
        api<Suppression[]>("/mail/suppressions"),
      ]);
      setTasks(todo);
      setSuppressed(blocks);
      setError("");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoaded(true);
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  async function status(task: MailTask, status: string) {
    setBusy(task.id);
    try {
      await patch(`/mail/tasks/${task.id}`, { status });
      await reload();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }
  async function unblock() {
    if (!release) return;
    setBusy(release.id);
    try {
      await api(`/mail/suppressions/${release.id}`, { method: "DELETE" });
      setRelease(null);
      await reload();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }
  return (
    <div className="mail-page">
      <Heading
        title={t("Follow-ups", "手动跟进")}
        detail={t(
          "Plan your next step and honor requests to stop contacting. Tasks never send emails automatically.",
          "安排下一步并尊重停止联系要求。任务不会自动发送邮件。",
        )}
      >
        <button className="button" onClick={() => void reload()}>
          <RefreshCw size={16} />
          {t("Refresh", "刷新")}
        </button>
        <button className="button primary" onClick={() => setCreate(true)}>
          <Plus size={16} />
          {t("Add follow-up", "添加跟进")}
        </button>
      </Heading>
      {error && (
        <p className="error-panel" role="alert">
          {error}
        </p>
      )}
      <section className="panel mail-card">
        <h2>{t("Manual tasks", "手动任务")}</h2>
        {!loaded ? (
          <div className="empty">
            <Busy />
          </div>
        ) : !tasks.length ? (
          <Empty
            title={t("No follow-ups yet", "暂无跟进任务")}
            detail={t(
              "Create a task here or from a contact conversation.",
              "在此处或联系人会话中创建任务。",
            )}
          />
        ) : (
          tasks.map((task) => (
            <article className="mail-delivery" key={task.id}>
              <div className="mail-card-head">
                <div>
                  <h3>{task.title}</h3>
                  <p>
                    {contacts.find((c) => c.id === task.contact_id)?.name ||
                      task.contact_id}{" "}
                    · {localDate(task.due_at)}
                  </p>
                </div>
                <Badge
                  tone={
                    task.status === "pending" &&
                    new Date(task.due_at).getTime() < Date.now()
                      ? "amber"
                      : "gray"
                  }
                >
                  {task.status}
                </Badge>
              </div>
              {task.notes && <p className="mail-note">{task.notes}</p>}
              <div className="mail-actions">
                {task.status === "pending" && (
                  <>
                    <button
                      className="button"
                      disabled={!!busy}
                      onClick={() => void status(task, "completed")}
                    >
                      <Check size={15} />
                      {t("Complete", "完成")}
                    </button>
                    <button
                      className="text-button"
                      disabled={!!busy}
                      onClick={() => void status(task, "cancelled")}
                    >
                      {t("Cancel task", "取消任务")}
                    </button>
                  </>
                )}
                <Nav href={`/email?contact=${task.contact_id}`}>
                  {t("Write email", "撰写邮件")}
                </Nav>
                {task.mailbox_id && (
                  <Nav href={`/inbox?mailbox=${task.mailbox_id}`}>
                    {t("Open inbox", "打开收件箱")}
                  </Nav>
                )}
              </div>
            </article>
          ))
        )}
      </section>
      <section className="panel mail-card">
        <div className="mail-card-head">
          <div>
            <h2>{t("Do not contact", "停止联系名单")}</h2>
            <p>
              {t(
                "Suppression is enforced for this workspace across connected mailboxes.",
                "停止联系设置适用于此工作区的全部已连接邮箱。",
              )}
            </p>
          </div>
          <button className="button" onClick={() => setSuppress(true)}>
            <ShieldCheck size={16} />
            {t("Add suppression", "添加停止联系")}
          </button>
        </div>
        {!suppressed.length && loaded && (
          <p className="mail-hint">
            {t("No suppressed contacts.", "暂无停止联系的联系人。")}
          </p>
        )}
        {suppressed.map((entry) => (
          <article className="mail-delivery" key={entry.id}>
            <div className="mail-card-head">
              <div>
                <h3>
                  {contacts.find((c) => c.id === entry.contact_id)?.name ||
                    entry.email ||
                    entry.contact_id}
                </h3>
                <p>
                  {entry.email ||
                    contacts.find((c) => c.id === entry.contact_id)?.email}{" "}
                  · {entry.reason}
                </p>
                {entry.notes && <p>{entry.notes}</p>}
              </div>
              <button
                className="text-button"
                disabled={!!busy}
                onClick={() => setRelease(entry)}
              >
                {t("Review & remove", "审核并移除")}
              </button>
            </div>
          </article>
        ))}
      </section>
      {create && (
        <TaskEditor
          onClose={() => setCreate(false)}
          onSaved={() => {
            setCreate(false);
            void reload();
          }}
        />
      )}
      {suppress && (
        <SuppressionEditor
          onClose={() => setSuppress(false)}
          onSaved={() => {
            setSuppress(false);
            void reload();
          }}
        />
      )}
      {release && (
        <Drawer
          title={t("Remove contact suppression", "移除停止联系限制")}
          onClose={() => {
            if (!busy) setRelease(null);
          }}
        >
          <div className="mail-review">
            <h2>
              {release.email ||
                contacts.find((c) => c.id === release.contact_id)?.email}
            </h2>
            <p>
              {t(
                "Only remove this restriction when you have a reason to contact this person again. Removing it allows new sends; review any paused deliveries separately.",
                "仅在有理由再次联系此人时移除此限制。移除后将允许新发送；已暂停的邮件需单独审核。",
              )}
            </p>
            {error && (
              <p className="error-panel" role="alert">
                {error}
              </p>
            )}
            <button
              className="button"
              disabled={!!busy}
              onClick={() => void unblock()}
            >
              {t("Confirm removal", "确认移除")}
            </button>
          </div>
        </Drawer>
      )}
    </div>
  );
}
