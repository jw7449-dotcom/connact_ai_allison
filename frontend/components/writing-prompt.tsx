"use client";

import { Sparkles } from "lucide-react";
import type { Draft } from "@/lib/types";
import { useApp } from "@/lib/context";
import { Field } from "./ui";

export default function WritingPrompt({
  draft,
  edit,
}: {
  draft: Draft;
  edit: (patch: Partial<Draft>) => void;
}) {
  const { t } = useApp();
  const starters = [
    {
      name: t("Introduce myself", "自我介绍"),
      prompt: t(
        "Write a warm introductory email using my background and the recipient's supplied information. Explain why I am reaching out, mention one relevant detail only if supported by selected evidence, and ask for a brief conversation. Keep it specific and easy to answer.",
        "根据我的背景与收件人的已提供信息，写一封友好的介绍邮件。说明联系原因，仅在所选证据支持时提及一项相关细节，并邀请简短交流。内容具体，让对方容易回复。",
      ),
    },
    {
      name: t("Ask for advice", "请教建议"),
      prompt: t(
        "Draft an informational interview request. Briefly introduce me using the linked persona or context I provide, explain what I hope to learn from the recipient, and ask for 15 minutes. Do not invent a shared connection, achievement, or prior conversation.",
        "写一封职业访谈邀请。根据绑定画像或我提供的背景简短介绍我，说明希望向对方了解什么，并邀请 15 分钟交流。不要编造共同关系、成就或以往交流。",
      ),
    },
    {
      name: t("Follow up politely", "礼貌跟进"),
      prompt: t(
        "Write a short follow-up to an earlier outreach email. Restate the reason for connecting and offer a low-pressure next step. Use the current email as context if present. Do not claim that the recipient replied or showed interest unless the provided context says so.",
        "写一封简短的跟进邮件，重申联系原因并提出轻松的下一步。若当前邮件有内容则将其作为背景。除非提供的背景明确说明，否则不要声称对方已回复或表达兴趣。",
      ),
    },
  ];
  return (
    <section
      className="email-prompt-panel"
      aria-label={t("Prompt editor", "Prompt 编辑器")}
    >
      <div className="email-mode-intro">
        <strong>
          <Sparkles size={16} />
          {t("Tell AI exactly what to write", "直接告诉 AI 要写什么")}
        </strong>
        <p>
          {t(
            "Start with a prompt below or write your own. Add background, an intended outcome, and any wording to keep.",
            "选择下方起始 Prompt 或自行编写，补充背景、目标及希望保留的措辞。",
          )}
        </p>
      </div>
      <div
        className="email-prompt-starters"
        aria-label={t("Starter prompts", "起始 Prompt")}
      >
        {starters.map((starter) => (
          <button
            className="button small-button"
            type="button"
            key={starter.name}
            onClick={() => edit({ custom_instructions: starter.prompt })}
          >
            {starter.name}
          </button>
        ))}
      </div>
      <Field label={t("Your prompt", "您的 Prompt")}>
        <textarea
          className="email-prompt-input"
          rows={7}
          maxLength={6000}
          value={draft.custom_instructions || ""}
          onChange={(event) =>
            edit({ custom_instructions: event.target.value })
          }
          placeholder={t(
            "Write an email to…\nMy background is…\nThe goal is…\nInclude… and avoid…",
            "写一封邮件给……\n我的背景是……\n联系目标是……\n需要包含……，避免……",
          )}
        />
      </Field>
      <div className="email-prompt-caption">
        <span>{t("Saved with this draft", "随草稿保存")}</span>
        <span>
          {(draft.custom_instructions || "").length.toLocaleString()} / 6,000
        </span>
      </div>
      <details className="email-request-preview">
        <summary>{t("Preview writing request", "预览写作请求")}</summary>
        <dl>
          <dt>{t("Primary prompt", "主要 Prompt")}</dt>
          <dd>
            {draft.custom_instructions ||
              t("Add your prompt above.", "请在上方填写 Prompt。")}
          </dd>
          <dt>{t("Context", "背景")}</dt>
          <dd>
            {draft.purpose || t("No additional brief", "暂无额外写作背景")} ·{" "}
            {draft.contact_id
              ? t("Linked contact", "已绑定联系人")
              : t("No contact", "无联系人")}{" "}
            ·{" "}
            {draft.persona_id
              ? t("Linked persona", "已绑定画像")
              : t("No persona", "无画像")}{" "}
            · {(draft.evidence_ids || []).length}{" "}
            {t("selected sources", "项所选来源")}
          </dd>
          <dt>{t("Style", "风格")}</dt>
          <dd>
            {draft.language === "zh" ? "简体中文" : "English"} · {draft.tone} ·{" "}
            {draft.length}
          </dd>
        </dl>
      </details>
    </section>
  );
}
