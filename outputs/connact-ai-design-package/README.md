# Connact.ai Design Delivery Package

Version 1.1 · September 6, 2026

This package contains design documents and an offline interactive demo for phased development. It is not a deployed backend, and the package itself does not connect to Apollo, an AI model, or Gmail.

## Files

| File | Purpose |
| --- | --- |
| connact-ai-detailed-design.docx | 18-page detailed design, including AI writing interaction, evidence, versions and variables, page layout, technical architecture, interfaces, subsequent sending, and acceptance |
| connact-ai-workflow-demo.html | Bilingual English/Simplified Chinese offline demo, including product flow, exception scenarios, technical architecture tracking, and four-phase Prompts |
| connact-ai-feature-roadmap.xlsx | 7 worksheets, 58 phased features, 9 Soon management to-dos, 22 acceptance scenarios, AI writing steps, 15 interfaces/contracts, and four-phase complete Prompts |
| prompt-01-mvp.md | Phase 1: Resume, People Search, Contact, AI Writing, Preview, and Draft |
| prompt-02-mailboxes-send.md | Phase 2: Account isolation, multiple Gmail mailboxes, single-email testing, sending, and scheduling |
| prompt-03-inbox-followup.md | Phase 3: Inbox, Original Conversation Reply, Manual Follow-up, and Scheduling Protection |
| prompt-04-campaigns-polish.md | Phase 4: Batch Campaigns, Templates, Statistics, Settings, and Academic Contract |

## Recommended Reading and Usage Order

1. Extract and keep all files in the same directory. Open the HTML file in a browser; no dependencies or internet connection are required.
   Use the language button in the upper-right corner to switch the complete demo, roadmap data, and embedded prompts between English and Simplified Chinese.
2. Confirm the fictional examples in Personas, save Maya in People Search, then click Write. You can write the body manually first, then generate suggestions, observing that the body is not overwritten.
3. Adopt the suggestions and preview, test the "Missing Name" and "Suggestion Expired" scenarios; switch the top Workflow / Architecture to view the logic.
4. The top Phase 2–4 only changes the scope of the demo, showing simulated interactions for connections, inbox, and campaigns, which do not represent that these services are completed. Simulated reminder expiration does not send emails.
5. Read the AI Writing Design in Word Sections 03–07, then filter by phase in Excel.
6. Start with prompt-01-mvp.md, and place the corresponding prompt in a new development task in the same codebase. For the next phase, first read the existing code and the acceptance results from the previous phase to avoid rebuilding the project.

## Excel Usage

The feature count, completed count, and completion rate in "Phase Overview" are calculated from formulas in "Feature List." The initial implementation status is "Not Started," and the verification level is "Unverified"; neither indicates completed development.

The "Feature List" can filter by phase, module, and status, with frozen headers and requirement IDs. The light yellow implementation status, verification level, and verification evidence are used for updates during development. Mock and real verification are recorded separately.

The "Phase Prompts" save all the body text; after filtering by phase, copy the text in paragraph order. A more convenient way is to directly copy the independent Markdown files.

## Chinese Backup

The repository also retains `outputs/connact-ai-design-package-zh-CN.zip`, a complete Chinese-language snapshot created before the English documentation conversion.

## Confirmed Scope

A personal workspace supports multiple Gmail mailboxes. The architecture reserves room for teams, but team collaboration is not included. English is the default interface language, with Simplified Chinese available as an option; email language is controlled independently. Finance is the core domain, while Academic remains an entry point backed by a replaceable data-source contract. None of the four phases includes automated email sequences.

Accounts and login are scheduled for Phase 2 and are completed before real Gmail data is integrated. Phase 1 uses a local fixed workspace mode and is not considered a public deployment certification solution. Phase 4 only refines settings and does not delay basic identity isolation.

## Verification Scope of This Delivery Package

- Word has completed Chinese font correction, rendering, and page-by-page checks.
- XLSX has been checked for visual output of 7 tables, phased formulas, filtered tables, dropdowns for status, and frozen panes; formula error scanning found no errors.
- HTML has been validated on desktop and widths of 1024, 736, and 390 px, with no horizontal page overflow or JavaScript errors found; no external network requests were made during validation.
- Demo validation includes filtering, repeated saving, generation without overwriting the original draft, adoption, variable preview, missing variable blocking, expired suggestion blocking, draft isolation between contacts, refresh recovery, simulated test sending, only reminders without sending, and Prompt viewing.

The HTML demo records only the selected resume file name; its parsing and writing examples use fixed fictional data. Rich-text editing, server-side persistence, OAuth, and live sending remain product implementation work. This package does not provide proof of live API calls, delivery, or reply synchronization.

Resetting the demo will clear the state saved in the current browser. If the browser disables local storage, the demo can still be viewed during the current session; if copy permissions are unavailable, text will be displayed for manual copying.

## Soon Administrator Backend

The administrator backend has been included in Soon, with specific phases and dates to be determined, and is not counted toward the P1–P4 delivery milestones. The HTML left-side Admin Console and phased pages can view the scope of nine pages; Word Section 17 and Excel's Soon filter are synchronized. Currently, only entry placeholders and planning are done, and management functions are not implemented. The four Prompts have been supplemented with the same scope boundaries.

## Apollo and LinkedIn Collaboration Notes

Apollo provides structured people search and on-demand email enrichment; SerpAPI retrieves LinkedIn public profiles via Google search, supplementing career background clues. Apollo's name, organization, or profile URL is used to locate LinkedIn; verified LinkedIn information is used to assist Apollo in matching and enrichment. Results from both sources are associated with the same Contact, with sources, timestamps, and conflicts preserved separately. Search summaries can only be marked as unverified clues and cannot automatically confirm the same person, overwrite fields, or be used for alumni statements. This is the target design of dual-source collaboration: the current MVP still uses a general Google query and has not yet implemented LinkedIn-directed search, reverse matching, or automatic cross-verification.

The People Search page in the demo has added collaboration notes and a "View Dual-Source Example"; Word Sections 02, 09, the Feature List P1-09 to P1-12, Acceptance T03, and the first-phase Prompt have been synchronized. SerpAPI searches LinkedIn public pages via Google Search API, which does not indicate that LinkedIn's official API has been integrated. Reference: https://serpapi.com/search-api

## Project Naming

The external product name is uniformly **Connact.ai**, with fixed capitalization and decimal points. Document, Demo, API titles, and development Prompts use the same name. Delivery files and directories use the `connact-ai-` prefix; the four-phase Prompts follow the `prompt-01-…` to `prompt-04-…` numbering rule.

The repository directory `coldemail`, existing database/database user `meridian`, test database `meridian_test`, internal package name `meridian-workspace`, container user, and browser storage key are compatibility identifiers, retained with original values, and not displayed as product names. Changing the product name does not require database migration or clearing user data.
