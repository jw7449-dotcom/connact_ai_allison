export type Mailbox = {
  id: string;
  email: string;
  display_name: string;
  status: string;
  scopes: string[];
  sync_enabled: boolean;
  can_send?: boolean;
  can_receive?: boolean;
  signature_html?: string;
  timezone?: string;
  send_window_start?: number;
  send_window_end?: number;
  last_sync_at: string | null;
  last_sync_error: string;
  sync_status: string;
};

export type MailboxesResponse = {
  configured: boolean;
  mailboxes: Mailbox[];
  callback_uri: string;
  unavailable_reason?: string;
};

export type MailMessage = {
  id: string;
  mailbox_id: string;
  gmail_message_id: string;
  gmail_thread_id: string;
  contact_id: string;
  contact_email: string;
  from_email: string;
  to_emails: string[];
  subject: string;
  snippet: string;
  body_text: string;
  body_html: string;
  received_at: string;
  is_unread: boolean;
  is_archived: boolean;
  direction: string;
  attachments: {
    id: string;
    filename?: string;
    name?: string;
    size?: number;
  }[];
};

export type MailThread = {
  messages: MailMessage[];
  notes: string;
  intent: string;
};

export type MailSend = {
  id: string;
  mailbox_id: string;
  mailbox_email: string;
  draft_id: string;
  contact_id: string;
  recipient_email: string;
  subject: string;
  body_text?: string;
  body_html?: string;
  status: string;
  error: string;
  scheduled_at: string | null;
  created_at: string;
  sent_at: string | null;
  mode?: string;
  attachments?: { filename: string; size: number; mime_type: string }[];
};

export type SendPreview = {
  subject: string;
  body_text: string;
  body_html: string;
  recipient_email: string;
  revision: number;
  can_send: boolean;
  issues: string[];
};

export type MailTask = {
  id: string;
  contact_id: string;
  mailbox_id?: string;
  thread_id?: string;
  title: string;
  due_at: string;
  status: string;
  notes: string;
};

export type Suppression = {
  id: string;
  contact_id: string;
  email?: string;
  reason: string;
  notes: string;
};
