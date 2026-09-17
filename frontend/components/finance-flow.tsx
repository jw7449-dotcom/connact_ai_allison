"use client";
import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Landmark,
  Plus,
  RotateCcw,
} from "lucide-react";
import { useApp } from "@/lib/context";
import { api, post, put, errorText } from "@/lib/api";
import type { Contact, Draft, Persona, Preview } from "@/lib/types";
import { Avatar, Badge, Busy, Field, Heading, Nav } from "./ui";
import Personas from "./personas";
import { PeopleSearch } from "./people";
import { DraftEditor } from "./email-studio";
import { FinanceReview, FinanceFollowup } from "./finance-review";
import "./finance-flow.css";

type Progress = {
  step: number;
  personaId: string;
  contactId: string;
  draftId: string;
  searchJobId: string;
};
const empty: Progress = {
  step: 0,
  personaId: "",
  contactId: "",
  draftId: "",
  searchJobId: "",
};
const steps = [
  ["Profile", "画像准备"],
  ["People", "选择联系人"],
  ["Write", "撰写邮件"],
  ["Review", "预览审核"],
  ["Follow-up", "后续跟进"],
];

export default function FinanceFlow() {
  const { t, locale, personas, contacts, drafts, config, guard, refresh } =
    useApp();
  const storageKey = `connact-finance-flow:${config?.workspace_id || "local-personal"}`;
  const [flow, setFlow] = useState<Progress>(empty);
  const [hydrated, setHydrated] = useState(false);
  const [contact, setContact] = useState<Contact | null>(null);
  const [editor, setEditor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const acting = useRef(false);
  const content = useRef<HTMLDivElement>(null);
  const persona = personas.find((p) => p.id === flow.personaId);

  useEffect(() => {
    let restored = { ...empty, personaId: personas[0]?.id || "" };
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) || "null");
      if (saved && typeof saved === "object") {
        const p = personas.find((p) => p.id === saved.personaId);
        if (p) {
          const d = drafts.find(
            (d) =>
              d.id === saved.draftId &&
              d.persona_id === p.id &&
              d.contact_id === saved.contactId,
          );
          restored = {
            step: Number.isInteger(saved.step)
              ? Math.max(
                  0,
                  Math.min(saved.step, d ? (d.status === "ready" ? 4 : 3) : 1),
                )
              : 0,
            personaId: p.id,
            contactId:
              typeof saved.contactId === "string" ? saved.contactId : "",
            draftId: d?.id || "",
            searchJobId:
              typeof saved.searchJobId === "string" ? saved.searchJobId : "",
          };
          setReviewed(d?.status === "ready");
        }
      }
    } catch {
      /* An invalid browser record never replaces saved workspace data. */
    }
    setFlow(restored);
    setEditor(personas.length ? null : "");
    setHydrated(true);
  }, [storageKey]);

  useEffect(() => {
    if (!hydrated) return;
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(flow));
    } catch {
      /* The workflow remains usable without browser storage. */
    }
  }, [flow, storageKey, hydrated]);

  useEffect(() => {
    if (!flow.contactId) {
      setContact(null);
      return;
    }
    const saved = contacts.find((c) => c.id === flow.contactId);
    if (saved) {
      setContact(saved);
      return;
    }
    if (contact?.id === flow.contactId) return;
    let alive = true;
    api<Contact>("/contacts/" + flow.contactId)
      .then((c) => {
        if (alive) setContact(c);
      })
      .catch((e) => {
        if (alive) setError(errorText(e));
      });
    return () => {
      alive = false;
    };
  }, [flow.contactId, contacts]);

  const selectPersona = (p: Persona | undefined) => {
    setError("");
    setFlow((old) =>
      old.personaId === (p?.id || "")
        ? old
        : { ...empty, personaId: p?.id || "" },
    );
    if (p?.id !== flow.personaId) setReviewed(false);
  };
  const selectContact = (c: Contact) => {
    setContact(c);
    setError("");
    setFlow((old) => ({
      ...old,
      contactId: c.id,
      draftId: old.contactId === c.id ? old.draftId : "",
    }));
    if (c.id !== flow.contactId) setReviewed(false);
  };
  async function move(step: number) {
    if (acting.current || step === flow.step) return;
    acting.current = true;
    setBusy(true);
    setError("");
    try {
      if (guard.current) await guard.current();
      if (step > 0 && !persona)
        throw new Error(
          t("Save and select a persona first.", "请先保存并选择职业画像。"),
        );
      let draftId = flow.draftId;
      let current: Draft | null = null;
      if (step >= 2) {
        if (!contact || contact.id !== flow.contactId)
          throw new Error(t("Select a contact first.", "请先选择联系人。"));
        if (!draftId) {
          await post("/contacts/" + contact.id + "/save");
          const created = await post<Draft>("/drafts", {
            contact_id: contact.id,
            persona_id: persona!.id,
            purpose: persona!.data.contact_purpose,
            language: locale === "zh" ? "zh" : "en",
          });
          draftId = created.id;
          // Record immediately, so a later read failure cannot create a duplicate on retry.
          setFlow((old) => ({ ...old, draftId }));
        }
        current = await api<Draft>("/drafts/" + draftId);
        if (
          current.persona_id !== flow.personaId ||
          current.contact_id !== flow.contactId
        ) {
          setFlow((old) => ({ ...old, step: 1, draftId: "" }));
          setReviewed(false);
          throw new Error(
            t(
              "The draft context changed elsewhere. That draft is preserved. Confirm your contact and continue to create a new email for this workflow.",
              "草稿背景已在其他页面变更，该草稿已保留。请确认联系人后继续，为本次流程创建新邮件。",
            ),
          );
        }
        if (step === 2 && current.persona_version !== persona!.version) {
          current = await put<Draft>("/drafts/" + draftId, {
            ...current,
            status: "draft",
          });
          setReviewed(false);
        }
      }
      if (step >= 3 && current) {
        if (
          !current.subject.trim() ||
          !current.body_html.replace(/<[^>]*>/g, "").trim()
        )
          throw new Error(
            t(
              "Add an email subject and body before reviewing.",
              "请先填写邮件主题和正文，再进行预览审核。",
            ),
          );
        if (step === 4) {
          const preview = await api<Preview>("/drafts/" + draftId + "/preview");
          if (
            current.status !== "ready" ||
            !preview.can_mark_ready ||
            preview.persona_changed
          )
            throw new Error(
              t(
                "Review the latest email and mark it ready before continuing.",
                "请先审核最新邮件并标记为可使用，再继续。",
              ),
            );
        }
        setReviewed(current.status === "ready");
      }
      await refresh();
      setFlow((old) => ({ ...old, draftId, step }));
      content.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      setError(errorText(e));
    } finally {
      acting.current = false;
      setBusy(false);
    }
  }
  async function restart() {
    if (acting.current) return;
    acting.current = true;
    setBusy(true);
    try {
      if (guard.current) await guard.current();
      setFlow({ ...empty, personaId: flow.personaId });
      setReviewed(false);
      setEditor(null);
      setError("");
    } catch (e) {
      setError(errorText(e));
    } finally {
      acting.current = false;
      setBusy(false);
    }
  }
  const available = (step: number) =>
    step === 0 ||
    (!!persona &&
      (step === 1 || (!!flow.draftId && !!contact && (step < 4 || reviewed))));
  if (!hydrated)
    return (
      <div className="boot">
        <Busy /> {t("Opening workflow…", "正在打开流程…")}
      </div>
    );

  return (
    <div
      className="finance-flow"
      data-testid="finance-flow"
      data-step={flow.step}
    >
      <Heading
        title={t("Finance", "金融")}
        detail={t(
          "From your background to a thoughtful conversation, one step at a time.",
          "从职业背景到建立联系，一步步完成您的金融外联流程。",
        )}
      >
        <button
          className="button"
          onClick={() => void restart()}
          disabled={busy || flow.step === 0}
        >
          <RotateCcw size={15} />
          {t("Start another workflow", "开始新流程")}
        </button>
      </Heading>
      <section className="finance-flow-guide panel">
        <div className="finance-flow-intro">
          <span className="finance-flow-symbol">
            <Landmark size={24} />
          </span>
          <div>
            <h2>{t("Your finance outreach workflow", "金融外联引导")}</h2>
            <p>
              {t(
                "Choose your profile and contact once. Keep your context through writing, review, and follow-up.",
                "选好画像和联系人，将背景一路带入写作、审核和后续跟进。",
              )}
            </p>
          </div>
          <Badge>{flow.step + 1} / 5</Badge>
        </div>
        <nav
          className="finance-flow-steps"
          aria-label={t("Finance workflow steps", "金融引导步骤")}
        >
          {steps.map(([en, zh], i) => (
            <button
              key={en}
              aria-label={`${i + 1} ${t(en, zh)}`}
              aria-current={i === flow.step ? "step" : undefined}
              disabled={busy || editor !== null || !available(i)}
              onClick={() => void move(i)}
            >
              <span className="finance-step-number">
                {i < flow.step ? <Check size={16} /> : i + 1}
              </span>
              <span>{t(en, zh)}</span>
            </button>
          ))}
        </nav>
        {(persona || contact) && (
          <div className="finance-flow-context">
            {persona && (
              <span>
                {t("Profile", "画像")}
                <strong>{persona.label}</strong>
              </span>
            )}
            {contact && (
              <span>
                {t("Contact", "联系人")}
                <strong>
                  {contact.name} · {contact.company}
                </strong>
              </span>
            )}
            {flow.draftId && (
              <Nav href={"/email?draft=" + flow.draftId}>
                {t("Open saved draft", "打开已保存草稿")}{" "}
                <ArrowRight size={13} />
              </Nav>
            )}
          </div>
        )}
      </section>
      <div className="finance-flow-content" ref={content}>
        {error && (
          <div className="error-panel" role="alert">
            {error}
          </div>
        )}
        <fieldset className="finance-flow-stage" disabled={busy}>
          {flow.step === 0 && (
            <>
              <section className="panel finance-profile-picker">
                <h2>{t("Start with your background", "从您的职业背景开始")}</h2>
                <p>
                  {t(
                    "Choose a saved persona, enter your details, or import a resume. Save the persona to continue.",
                    "选择已有画像，或填写背景、导入简历。保存画像后继续。",
                  )}
                </p>
                <div className="finance-profile-actions">
                  <Field label={t("Workflow persona", "本次流程使用的画像")}>
                    <select
                      value={flow.personaId}
                      disabled={editor !== null}
                      onChange={(e) =>
                        selectPersona(
                          personas.find((p) => p.id === e.target.value),
                        )
                      }
                    >
                      <option value="">
                        {t("Choose a persona", "请选择画像")}
                      </option>
                      {personas.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <button
                    className="button"
                    disabled={editor !== null}
                    onClick={() => setEditor("")}
                  >
                    <Plus size={15} />
                    {t("Create a persona", "创建画像")}
                  </button>
                  {persona && (
                    <button
                      className="button"
                      disabled={editor !== null}
                      onClick={() => setEditor(persona.id)}
                    >
                      {t("Edit persona", "编辑画像")}
                    </button>
                  )}
                </div>
                {persona && editor === null && (
                  <div className="finance-persona-summary">
                    <Avatar name={persona.data.name || persona.label} />
                    <div>
                      <strong>{persona.data.name || persona.label}</strong>
                      <p>{persona.data.career_goals || persona.data.sectors}</p>
                    </div>
                    <Badge tone="green">
                      {t("Saved", "已保存")} · v{persona.version}
                    </Badge>
                  </div>
                )}
              </section>
              {editor !== null && (
                <div className="finance-embedded-persona">
                  <Personas
                    key={editor}
                    initialPersonaId={editor}
                    onSaved={(p) => {
                      selectPersona(p);
                      setEditor(null);
                    }}
                  />
                  <button className="button" onClick={() => setEditor(null)}>
                    {t("Close persona editor", "收起画像编辑器")}
                  </button>
                </div>
              )}
            </>
          )}
          {flow.step === 1 && (
            <>
              <p className="finance-step-hint">
                {t(
                  "Search, inspect the public profile and recommendations, then choose one person for this email.",
                  "搜索人员，查看公开履历和推荐理由，再选择本次联系的对象。",
                )}
              </p>
              {contacts.length > 0 && (
                <div className="finance-saved-contact">
                  <Field
                    label={t("Or choose a saved contact", "也可选择已有联系人")}
                  >
                    <select
                      value={
                        contacts.some((c) => c.id === flow.contactId)
                          ? flow.contactId
                          : ""
                      }
                      onChange={(e) => {
                        const c = contacts.find((c) => c.id === e.target.value);
                        if (c) selectContact(c);
                      }}
                    >
                      <option value="">
                        {t("Select from contacts", "从联系人中选择")}
                      </option>
                      {contacts.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name} · {c.company}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>
              )}
              <PeopleSearch
                selectedPersonaId={flow.personaId}
                selectedContactId={flow.contactId}
                onSelectContact={selectContact}
                initialJobId={flow.searchJobId}
                onJobChange={(id) =>
                  setFlow((old) =>
                    old.searchJobId === id ? old : { ...old, searchJobId: id },
                  )
                }
                initialFilters={{
                  title: persona?.data.target_roles || "",
                  location: persona?.data.target_regions || "",
                  keywords: persona?.data.sectors || "",
                }}
              />
            </>
          )}
          {flow.step === 2 && flow.draftId && (
            <>
              <p className="finance-step-hint">
                {t(
                  "Your profile and recipient are ready. Write directly, use AI, or choose a template. Continue when the subject and body are ready to review.",
                  "画像与收件人已带入。直接撰写、使用 AI 或套用模板，完成主题和正文后继续审核。",
                )}
              </p>
              <DraftEditor
                key={flow.draftId}
                id={flow.draftId}
                contextLocked
                hideDelivery
              />
            </>
          )}
          {flow.step === 3 && flow.draftId && (
            <FinanceReview
              key={flow.draftId}
              id={flow.draftId}
              onReviewed={() => setReviewed(true)}
            />
          )}
          {flow.step === 4 && flow.draftId && (
            <FinanceFollowup key={flow.draftId} draftId={flow.draftId} />
          )}
        </fieldset>
      </div>
      <footer className="finance-flow-footer panel">
        <button
          className="button"
          disabled={busy || flow.step === 0 || editor !== null}
          onClick={() => void move(flow.step - 1)}
        >
          <ArrowLeft size={16} />
          {t("Previous step", "上一步")}
        </button>
        <span>
          {flow.step === 1 && contact
            ? t(`Selected: ${contact.name}`, `已选择：${contact.name}`)
            : t(
                "Progress is kept in this browser tab.",
                "当前浏览器标签页会保留流程进度。",
              )}
        </span>
        {flow.step < 4 ? (
          <button
            className="button primary"
            disabled={
              busy ||
              editor !== null ||
              (flow.step === 0 && !persona) ||
              (flow.step === 1 && !contact) ||
              (flow.step === 3 && !reviewed)
            }
            onClick={() => void move(flow.step + 1)}
          >
            {busy ? <Busy /> : <ArrowRight size={16} />}
            {
              [
                t("Continue to people", "继续选择联系人"),
                t("Continue to writing", "继续撰写邮件"),
                t("Continue to review", "继续预览审核"),
                t("Continue to follow-up", "继续后续跟进"),
              ][flow.step]
            }
          </button>
        ) : (
          <button
            className="button primary"
            disabled={busy}
            onClick={() => void restart()}
          >
            <Check size={16} />
            {t("Finish workflow", "完成流程")}
          </button>
        )}
      </footer>
    </div>
  );
}
