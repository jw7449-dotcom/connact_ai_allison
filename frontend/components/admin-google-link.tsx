"use client";

import { useEffect, useState, type FormEvent } from "react";
import { CheckCircle2, ShieldCheck } from "lucide-react";
import { api, errorText, post } from "@/lib/api";
import { useApp } from "@/lib/context";
import { googleAuthorizationUrl, googleErrorText } from "@/lib/google-auth";
import styles from "./admin-google-link.module.css";

type AdminSession = {
  authenticated: boolean;
  is_admin: boolean;
  email: string | null;
  google_configured: boolean;
  google_linked: boolean;
};

export default function AdminGoogleLink({ revision }: { revision: number }) {
  const { t } = useApp();
  const [session, setSession] = useState<AdminSession | null>(null);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const url = new URL(window.location.href);
    const code = url.searchParams.get("error");
    if (code?.startsWith("google_")) {
      setError(googleErrorText(code));
      url.searchParams.delete("error");
    }
    // Only the server's session response can confirm that linking succeeded.
    if (url.searchParams.has("google_link"))
      url.searchParams.delete("google_link");
    window.history.replaceState(
      window.history.state,
      "",
      url.pathname + url.search + url.hash,
    );
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setSession(null);
    setLoadError("");
    api<AdminSession>("/auth/session", { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) setSession(value);
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setLoadError(errorText(failure));
      });
    return () => controller.abort();
  }, [revision, retry]);

  async function linkGoogle(e: FormEvent) {
    e.preventDefault();
    if (busy || !session?.google_configured || session.google_linked) return;
    setBusy(true);
    setError("");
    try {
      const result = await post<{ authorization_url: string }>(
        "/auth/google/link-admin",
        { email: email.trim().toLowerCase() },
      );
      window.location.assign(googleAuthorizationUrl(result.authorization_url));
    } catch (failure) {
      setError(errorText(failure));
      setBusy(false);
    }
  }

  if (
    session &&
    (!session.authenticated ||
      !session.is_admin ||
      (!session.google_linked && session.email !== "admin"))
  )
    return null;

  return (
    <section className={styles.section} aria-labelledby="admin-google-heading">
      <div className={styles.heading}>
        {session?.google_linked ? (
          <CheckCircle2 size={18} aria-hidden="true" />
        ) : (
          <ShieldCheck size={18} aria-hidden="true" />
        )}
        <h2 id="admin-google-heading">
          {t("Administrator Google sign-in", "管理员 Google 登录")}
        </h2>
      </div>
      {loadError ? (
        <>
          <p className={styles.error} role="alert">
            {loadError}
          </p>
          <button
            className="button ghost"
            onClick={() => setRetry((v) => v + 1)}
          >
            {t("Retry", "重试")}
          </button>
        </>
      ) : !session ? (
        <p role="status">{t("Checking account…", "正在检查账号…")}</p>
      ) : session.google_linked ? (
        <p role="status">
          {t("Google account connected", "Google 账号已绑定")}: {session.email}
        </p>
      ) : !session.google_configured ? (
        <p role="status">
          {t(
            "Google linking is awaiting server configuration.",
            "Google 账号绑定尚待服务端配置。",
          )}
        </p>
      ) : (
        <>
          <p>
            {t(
              "Connect your Google account to this administrator account. Your workspace and administrator access stay with this account.",
              "将你的 Google 账号绑定到当前管理员账号，保留原有工作区和管理员权限。",
            )}
          </p>
          <form className={styles.form} onSubmit={linkGoogle}>
            <label>
              {t("Google account email", "Google 账号邮箱")}
              <input
                type="email"
                autoComplete="email"
                required
                maxLength={320}
                value={email}
                disabled={busy}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <button className="button" disabled={busy || !email.trim()}>
              {busy
                ? t("Connecting…", "正在跳转…")
                : t("Link Google account", "绑定 Google 账号")}
            </button>
          </form>
        </>
      )}
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
