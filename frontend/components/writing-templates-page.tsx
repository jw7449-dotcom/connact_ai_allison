"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { post, errorText } from "@/lib/api";
import { useApp } from "@/lib/context";
import type { Draft } from "@/lib/types";
import { Busy, Heading } from "./ui";
import WritingTemplateLibrary from "./writing-template-library";
import "./email-writing.css";

export default function WritingTemplatesPage() {
  const { t, guard, refresh, go, notify } = useApp();
  const [busy, setBusy] = useState(false);
  async function create(content?: Pick<Draft, "subject" | "body_html">) {
    setBusy(true);
    try {
      if (guard.current) await guard.current();
      const draft = await post<Draft>("/drafts", {
        writing_mode: "template",
        ...content,
      });
      await refresh();
      await go("/email?draft=" + draft.id);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="email-templates-page">
      <Heading
        title={t("Email templates", "邮件模板")}
        detail={t(
          "Keep your best emails ready for the next conversation.",
          "保存常用邮件，为下一次交流做好准备。",
        )}
      >
        <button
          className="button primary"
          disabled={busy}
          onClick={() =>
            void create().catch((error) => notify(errorText(error)))
          }
        >
          {busy ? <Busy /> : <Plus size={16} />}
          {t("Write a new template", "编写新模板")}
        </button>
      </Heading>
      <WritingTemplateLibrary disabled={busy} onApply={create} />
    </div>
  );
}
