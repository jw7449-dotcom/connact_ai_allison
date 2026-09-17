import type { Draft, Preview } from "./types";

export type SequenceStep = {
  id: string;
  position: number;
  title: string;
  purpose: string;
  delay_days: number;
  thread_mode: "new_thread" | "reply";
  draft_id: string;
  draft: Draft;
};
export type SequenceJob = {
  id: string;
  status: string;
  completed_steps: number;
  total_steps: number;
  result_steps: {
    title: string;
    purpose: string;
    delay_days: number;
    thread_mode: string;
  }[];
  error: string | null;
  mode: string;
  model: string;
};
export type Sequence = {
  id: string;
  name: string;
  description: string;
  language: "en" | "zh";
  contact_id: string | null;
  persona_id: string | null;
  status: "draft" | "ready";
  revision: number;
  updated_at: string;
  steps: SequenceStep[];
  step_count?: number;
  generation: SequenceJob | null;
};
export type SequenceTemplate = {
  id: string;
  schema_version: number;
  name: string;
  description: string;
  is_default: boolean;
  steps: {
    title: string;
    purpose: string;
    delay_days: number;
    thread_mode: "new_thread" | "reply";
    subject?: string;
    body_html?: string;
  }[];
};
export type SequencePreview = {
  can_mark_ready: boolean;
  issues: string[];
  steps: {
    step_id: string;
    position: number;
    issues: string[];
    preview: Preview;
  }[];
};
