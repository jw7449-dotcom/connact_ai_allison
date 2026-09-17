export type PersonaData = {
  name: string;
  education: string;
  experience: string;
  skills: string;
  sectors: string;
  career_goals: string;
  target_regions: string;
  target_roles: string;
  contact_purpose: string;
};
export type Persona = {
  id: string;
  label: string;
  version: number;
  data: PersonaData;
  updated_at: string;
};
export type Evidence = {
  id: string;
  provider: string;
  url: string;
  title: string;
  snippet: string;
  kind: string;
  retrieved_at: string;
};
export type Assessment = {
  id: string;
  contact_id: string;
  persona_id: string;
  persona_version: number;
  reason: string;
  provider: string;
  source_ids: string[];
  language: string;
};
export type PeopleJob = {
  id: string;
  kind: "search" | "profile" | "email" | "email_apify";
  status: "queued" | "running" | "waiting" | "succeeded" | "failed";
  error: string;
  retryable: boolean;
  created_at: string;
  input: Record<string, unknown>;
  result: {
    items?: Contact[];
    total?: number;
    page?: number;
    per_page?: number;
    has_more?: boolean;
    total_is_estimate?: boolean;
    contact?: Contact;
    phase?: "profiles" | "complete";
    profile_progress?: {
      total: number;
      ready: number;
      failed: number;
      skipped: number;
      pending: number;
    };
  };
};
export type ProfessionalProfile = {
  summary?: string;
  headline?: string;
  experience?: {
    title: string;
    company: string;
    start_date: string;
    end_date: string;
    location: string;
    description: string;
  }[];
  education?: {
    school: string;
    degree: string;
    field_of_study: string;
    start_date: string;
    end_date: string;
  }[];
  skills?: string[];
  source_provider?: string;
  source_url?: string;
  retrieved_at?: string;
  source_id?: string;
};
export type Contact = {
  id: string;
  provider: string;
  provider_id: string | null;
  saved: boolean;
  name: string;
  title: string;
  company: string;
  location: string;
  school: string;
  profile_url: string;
  email: string;
  email_status: string;
  tags: string[];
  notes: string;
  domains: Record<string, { sector: string }>;
  sources: Evidence[];
  assessments: Assessment[];
  drafts?: Draft[];
  professional?: ProfessionalProfile;
  profile_prefetch?: {
    status: PeopleJob["status"] | "skipped";
    error: string;
    cached?: boolean;
    job_id?: string;
  } | null;
  jobs?: PeopleJob[];
  missing_fields?: string[];
  phone?: string;
  phone_status?: string;
};
export type Draft = {
  id: string;
  contact_id: string | null;
  persona_id: string | null;
  persona_version: number | null;
  language: "en" | "zh";
  purpose: string;
  starting_point: string;
  writing_mode: "assisted" | "prompt" | "template";
  tone: string;
  length: "short" | "medium" | "long";
  cta: string;
  model: string;
  custom_instructions: string;
  evidence_ids: string[];
  subject: string;
  body_html: string;
  status: "draft" | "ready";
  revision: number;
  updated_at: string;
  generation_provider: string;
};
export type WritingModels = {
  mode: string;
  provider: string;
  default_model: string;
  models: {
    id: string;
    label: string;
    provider?: string;
    provider_label?: string;
    configured?: boolean;
    available?: boolean;
  }[];
  configured: boolean;
};
export type Generation = {
  id: string;
  status:
    "queued" | "running" | "succeeded" | "failed" | "accepted" | "discarded";
  draft_revision: number;
  model: string;
  action: string;
  result: { subject: string; body_html: string } | null;
  error: string;
  snapshot: Record<string, unknown>;
  created_at: string;
};
export type Preview = {
  subject: string;
  body_html: string;
  body_text: string;
  missing_variables: string[];
  can_mark_ready: boolean;
  persona_changed: boolean;
  recipient_email: string;
  variables: Record<string, string>;
};
export type Config = {
  auth_mode?: "local" | "invite" | "open";
  is_admin?: boolean;
  workspace_id?: string;
  people_mode: string;
  ai_mode: string;
  public_search_mode: string;
  providers: Record<string, boolean>;
};
