import type { ReactNode } from "react";
import styles from "./public-site.module.css";

export function publicSupportEmail() {
  const value = process.env.PUBLIC_SUPPORT_EMAIL?.trim() || "";
  return /^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(value) ? value : "";
}

export function SupportContact({ chinese = false }: { chinese?: boolean }) {
  const email = publicSupportEmail();
  return email ? (
    <a href={`mailto:${email}`}>{email}</a>
  ) : (
    <span>
      {chinese
        ? "请通过向你提供 Connact.ai 访问方式的联系人，联系服务管理员。"
        : "Contact the service administrator through the person who provided your Connact.ai access."}
    </span>
  );
}

export default function PublicSite({
  children,
  current,
}: {
  children: ReactNode;
  current: "about" | "privacy";
}) {
  return (
    <div className={styles.site}>
      <a className={styles.skip} href="#main-content">
        Skip to content
      </a>
      <header className={styles.header}>
        <a className={styles.brand} href="/about" aria-label="Connact.ai home">
          <img src="/connact-icon.svg" alt="" width="32" height="32" />
          <span>Connact.ai</span>
        </a>
        <nav aria-label="Public navigation" className={styles.navigation}>
          <a
            href="/about"
            aria-current={current === "about" ? "page" : undefined}
          >
            About
          </a>
          <a
            href="/privacy"
            aria-current={current === "privacy" ? "page" : undefined}
          >
            Privacy
          </a>
          <a className={styles.openLink} href="/">
            Open workspace <span aria-hidden="true">↗</span>
          </a>
        </nav>
      </header>
      <main id="main-content" className={styles.main}>
        {children}
      </main>
      <footer className={styles.footer}>
        <div>
          <strong>Connact.ai</strong>
          <p>Professional connections, thoughtfully prepared.</p>
        </div>
        <div className={styles.footerLinks}>
          <a href="/privacy">Privacy policy</a>
          <SupportContact />
        </div>
      </footer>
    </div>
  );
}

export { styles as publicStyles };
