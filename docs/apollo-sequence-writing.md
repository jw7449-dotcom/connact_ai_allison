# Apollo writing and Sequence trial — 2026-09-09

Observed through the user's signed-in Apollo web app in Chrome. This is a visible-product trial, not a description of Apollo's backend or a reproduction of its private implementation. The existing sequence was read only. An isolated inactive sequence, `Connact.ai UI trial — 2026-09-09 — DO NOT SEND`, was created from Apollo's **Find the right contact** template. No contacts were added, no sequence was activated and no email was sent.

## Creation flow

**Create sequence** offers four paths: **AI-assisted**, **Templates**, **Clone**, and **From scratch**.

The AI-assisted path generated a review screen with three editable automatic emails across seven days: Day 1 Outreach, Day 4 Follow-up and Day 7 Last pitch. Follow-ups inherited the first subject as replies. The review screen allowed editing subject/body, expanding each step, opening **Edit my information**, and **Save sequence**. The AI-generated candidate was inspected but not saved. Edit my information opened a separate AI context center with Company profile and Product profiles. Its company fields included offering, customer profile, pain points, value proposition, competitors, social proof, CTA and additional information. Existing company information was not changed.

The sequence-template gallery showed 25 templates, search and categories for stage, signal, industry and call-based targeting. **Use template** immediately created an inactive sequence and opened its editor. The selected template contained a manual email immediately, an automatic email after six days and another after five days. The template's three subjects were initially empty; attempting to save active variants failed until subjects were filled.

## The three writing modes

| Mode | Observed controls and behavior | Trial result |
| --- | --- | --- |
| Assisted | Email type Outreach / Follow-up / Last pitch; AI research chips; tones Default, Direct, Formal, Casual, Creative and Custom; AI context selection; editable guidelines; messaging model and Generate preview | Switched the isolated test step to Assisted and saved specific guidelines. The first step only enabled Outreach. Standard displayed a cost of two credits. With no saved contacts, Generate preview did not produce a recipient preview. |
| Prompt | Separate subject and New thread / Reply; model selector; prompt-template picker; editable User prompt and optional System instructions; AI Context; fallback choices Mark as failed, Use email template, Ignore missing variables | Applied the Fully Personalized Email prompt template and verified that user and system fields filled. The picker also offered Signal based Personalization Email and Personalized Opener Email. This account's model menu exposed Claude Haiku 4.5 only. No per-contact prompt output was generated. |
| Template | Subject, rich body, sender/recipient variables, New thread / Reply, Write with AI, attachments, desktop/mobile contact preview | Edited a short test subject/body, saved the sequence and observed the success state. Template preview sometimes displayed an explicitly labeled Example Contact while loading; that is sample data, not a saved recipient. |

Switching Template to Assisted warns that it may overwrite changes. Switching Assisted to Prompt displayed a warning labeled "Switch to template mode?" saying the AI configuration would be cleared; after continuing the Prompt tab was selected. This appears to be a labeling mismatch in Apollo's visible UI.

**Write with AI** opens an AI variable panel with AI snippet, AI subject line and existing AI variable. Selecting AI snippet inserted a dynamic variable into the test body and opened a side panel with Context, snippet type (Opener), research selection, tone inferred from the body, optional guidelines and **Submit & preview**. Submit & preview was disabled without a contact. The dynamic snippet was removed from the test body's saved final copy. Apollo's prompt templates expose editable prompt text; this document records their product structure without copying that text.

## Editing the connected step timeline

The editor presents steps as vertically connected cards separated by timing controls. Cards can collapse, and a **Sequence steps** side panel lists every step with drag-to-reorder handles, timing, variants and Add A/B test. This supports interpreting the requested Chinese "流式步骤" as an ordered, connected workflow/timeline; this observation does not establish streamed token rendering.

**Add a step** exposed:

- Add a step with Assistant.
- Automatic email and Manual email.
- Phone call and Action item.
- LinkedIn connection request, message, view profile and interact with post.

An automatic email was added as step four. It defaulted to Assisted mode and a three-day delay. Its timing panel allowed immediately after the preceding step completes, or a numerical wait in minutes, hours or days. Step actions exposed change type, clone step, delete step and clone test. These action controls were inspected; deletion and cloning were not executed.

On saving the new AI automatic email, Apollo showed **Review AI emails before they send?**, with a checkbox to convert that step to a manual email. The test step was converted to Manual and saved. Its resulting card showed a task scheduled immediately with a due date in three days. Reloading the sequence confirmed four saved steps and the edited first subject/body. This distinguishes an automatic email's send delay from a manual task's due date. The overall sequence remained inactive.

## After creation: views and settings

The sequence exposes Editor, Contacts, Emails, Tasks, Activity, Health, Report and Settings. Contacts showed **0 Total / No records found**. Emails showed **No emails here**. The steps editor and account have distinct save and activation controls.

Settings exposed sequence name, description, tags, owner, schedule and rules. The name/description were saved to clearly identify the trial. The normal business-hours schedule displayed Monday–Friday, 8 AM–5 PM, with edit/create schedule links. Observed rules included finish on reply or booked meeting, pause on out-of-office reply, finish on unsubscribe, fail on bounce/spam, optional finish on link click, unresponsive status after five days, contact/account stage exclusions, maximum emails in a rolling 24 hours, CC/BCC and bounce protection. Their values were inspected but not changed.

## Account and verification limits

- The account had no linked mailbox. Sending, mailbox authorization, actual delivery, enrollment and reply handling were not tested.
- No saved contacts were added for this trial, so contact-specific Assisted/Prompt generation and AI variable preview were not verified. The displayed credit counter was 130 during editing and 135 after reload; the UI alone does not establish actual billed usage.
- The Health tab returned **Per page not supported** and showed a high-bounce auto-pause disabled state behind the error. Its healthy operation could not be verified.
- The AI-assisted create preview and template-derived creation worked. Clone was completed through the test sequence menu. Its setup asked for a name and schedule, and the new inactive four-step copy preserved content while its copied variant was inactive. A further creation attempt hit the account sequence limit at three listed sequences. After cleanup restored capacity, **From scratch** opened a **New Sequence** form with name, description, schedule (Normal Business Hours, Monday–Friday, 8 AM–5 PM), Back and Create. The form was exited with Back without submitting; scratch creation beyond this form was not verified. No upgrade was attempted.
- Both temporary resources were archived: `Connact.ai Clone trial 2026-09-09 DO NOT SEND` (ID `6aa1077d26a690001c3c3e32`) and the initial isolated four-step trial (ID `6aa102768decf3001c7023c2`). The creation limit persisted after archiving only the clone and reloading, so the initial trial was also archived. Final verification showed All Sequences containing only the original user sequence (1–1 of 1), and Create sequence opened normally again. Both trial resources had zero contacts and zero scheduled/sent emails. Existing user sequence content and account settings were not edited. Tasks, Activity and Report were visible navigation destinations but were not explored further in the bounded supplemental trial.

## Product adaptation for Connact.ai

| User need / observed pattern | Connact.ai adaptation requirement |
| --- | --- |
| Independent entry point | Add Sequences to the left navigation and allow reopening saved sequence plans. |
| Start from existing writing | Select saved drafts and snapshot their subject/body into chosen steps; preserve source draft attribution without mutating the draft. |
| AI or reusable steps | Offer AI-generated step planning and three clearly described default step templates, alongside user-created/uploaded reusable templates. Preview the plan before applying it. |
| Connected editing | Show numbered step cards linked by wait controls and cumulative timing; support add, edit, reorder and remove; keep initial email and reply subject behavior explicit. |
| Complete writing modes | Assisted needs a real brief/evidence/guidelines flow; Prompt needs a real editable prompt flow; Template needs editable content and reusable templates. Persist settings and distinguish preview from accepted draft content. |
| Review before execution | Persist and validate sequence plans independently from actual sending. Saving a plan does not mean contacts have been enrolled or mail has been delivered. |
| Honest preview | Show selected real-contact evidence or an explicitly labeled sample; keep unresolved variables visible and expose generation failures. |
| Failure and revision handling | Reject acceptance against stale draft revisions, preserve generation provenance and avoid silent provider fallbacks. |

The local implementation can adapt these visible interactions to professional networking. It must describe sequence planning separately from multi-step email execution; automatic delivery, reply processing, A/B testing and send-time AI variables require their own implemented and verified capabilities.
