import type { Metadata } from "next";
import PublicSite, { publicStyles as styles } from "@/components/public-site";

// Support details are deployment configuration, read at request time.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Connact.ai — Prepare your next professional connection",
  description:
    "Discover professional contacts, organize your background and research, and prepare thoughtful outreach drafts with Connact.ai.",
};

export default function AboutPage() {
  return (
    <PublicSite current="about">
      <section className={styles.hero} aria-labelledby="about-title">
        <div>
          <p className={styles.eyebrow}>Research. Prepare. Connect.</p>
          <h1 id="about-title">Make your next connection more thoughtful.</h1>
          <p className={styles.lead}>
            Find relevant people, understand their professional background, and
            turn your own experience into a considered introduction. Connact.ai
            keeps the research and the writing in one workspace.
          </p>
          <div className={styles.actions}>
            <a className={styles.primaryLink} href="/">
              Open your workspace <span aria-hidden="true">→</span>
            </a>
            <a className={styles.textLink} href="#chinese" lang="zh-CN">
              中文介绍 ↓
            </a>
          </div>
          <p className={styles.caption}>
            Google sign-in verifies your identity. It does not connect your
            Gmail inbox or authorize sending email.
          </p>
        </div>
        <aside className={styles.workflow} aria-label="How Connact.ai works">
          <div className={styles.workflowHeading}>
            <span className={styles.smallDot} aria-hidden="true" />
            From research to a ready draft
          </div>
          <ol>
            <li>
              <span className={styles.stepNumber}>01</span>
              <div>
                <h2>Find the right people</h2>
                <p>
                  Search by professional interests and review source-backed
                  profiles.
                </p>
              </div>
            </li>
            <li>
              <span className={styles.stepNumber}>02</span>
              <div>
                <h2>Bring your context</h2>
                <p>
                  Save contacts and organize your experience into reusable
                  personas.
                </p>
              </div>
            </li>
            <li>
              <span className={styles.stepNumber}>03</span>
              <div>
                <h2>Give each message care</h2>
                <p>
                  Use AI writing suggestions, then review and edit your draft.
                </p>
              </div>
            </li>
          </ol>
          <div className={styles.workflowNote}>
            Your review is part of the process.
          </div>
        </aside>
      </section>

      <section className={styles.features} aria-labelledby="features-title">
        <div className={styles.sectionIntro}>
          <p className={styles.eyebrow}>A place to prepare</p>
          <h2 id="features-title">Keep the important context close.</h2>
        </div>
        <div className={styles.cardGrid}>
          <article>
            <span className={styles.cardLabel}>People &amp; research</span>
            <h3>Understand who you want to meet.</h3>
            <p>
              Discover professional profiles and save useful contacts, source
              information, notes, and tags. Available details depend on the
              connected data providers.
            </p>
          </article>
          <article>
            <span className={styles.cardLabel}>Personas &amp; writing</span>
            <h3>Start with your own experience.</h3>
            <p>
              Upload a resume or build a persona, then prepare and refine drafts
              with AI assistance. Reuse writing templates and keep control of
              the final text.
            </p>
          </article>
          <article>
            <span className={styles.cardLabel}>Sequence planning</span>
            <h3>Plan the next step with intention.</h3>
            <p>
              Organize outreach steps and follow-up drafts before taking action.
              Connect Gmail separately to send reviewed messages, schedule
              delivery and synchronize saved contacts&apos; replies. Sequence
              plans and manual follow-up tasks do not send emails automatically.
            </p>
          </article>
        </div>
      </section>

      <section className={styles.accountNote} aria-labelledby="account-title">
        <div>
          <p className={styles.eyebrow}>Your account</p>
          <h2 id="account-title">Know what you are connecting.</h2>
        </div>
        <div>
          <p>
            Google sign-in uses basic identity permissions to create or access
            your Connact.ai account. Workspace data is associated with your
            account. Service administrators can inspect account records and
            workspace content, including uploaded documents.
          </p>
          <a className={styles.textLink} href="/privacy">
            Read how your information is used <span aria-hidden="true">→</span>
          </a>
        </div>
      </section>

      <section id="chinese" lang="zh-CN" className={styles.chineseSummary}>
        <p className={styles.eyebrow}>中文介绍</p>
        <h2>把找人、了解背景和准备沟通，放在同一个工作区。</h2>
        <p>
          Connact.ai
          帮助你搜索职业人士、查看职业资料并保存联系人；你可以上传简历、整理个人背景，
          借助 AI
          起草和修改邮件，复用写作模板，以及规划后续联系步骤。资料完整程度取决于接入的数据服务。
        </p>
        <p>
          Google 登录仅用于确认身份、进入个人工作区，不授权读取 Gmail
          或发送邮件。
          当前版本用于准备草稿与联系计划，尚不提供邮件发送或收件箱同步。
          管理员能够查看账号记录、工作区内容及上传的文档；详情请阅读
          <a href="/privacy#chinese">隐私政策中文说明</a>。
        </p>
      </section>
    </PublicSite>
  );
}
