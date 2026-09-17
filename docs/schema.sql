BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 5aba178b468a

CREATE TABLE workspaces (
    name VARCHAR(150) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE contacts (
    provider VARCHAR(30) NOT NULL, 
    provider_id VARCHAR(160), 
    saved BOOLEAN NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    title VARCHAR(250) NOT NULL, 
    company VARCHAR(250) NOT NULL, 
    location VARCHAR(250) NOT NULL, 
    school VARCHAR(250) NOT NULL, 
    profile_url TEXT NOT NULL, 
    email VARCHAR(250) NOT NULL, 
    email_status VARCHAR(60) NOT NULL, 
    tags JSON NOT NULL, 
    notes TEXT NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id), 
    UNIQUE (workspace_id, provider, provider_id)
);

CREATE INDEX ix_contacts_workspace_id ON contacts (workspace_id);

CREATE TABLE personas (
    label VARCHAR(150) NOT NULL, 
    domain VARCHAR(30) NOT NULL, 
    version INTEGER NOT NULL, 
    data JSON NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_personas_workspace_id ON personas (workspace_id);

CREATE TABLE contact_domain_profiles (
    contact_id VARCHAR(36) NOT NULL, 
    domain VARCHAR(30) NOT NULL, 
    data JSON NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(contact_id) REFERENCES contacts (id), 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id), 
    UNIQUE (workspace_id, contact_id, domain)
);

CREATE INDEX ix_contact_domain_profiles_contact_id ON contact_domain_profiles (contact_id);

CREATE INDEX ix_contact_domain_profiles_workspace_id ON contact_domain_profiles (workspace_id);

CREATE TABLE drafts (
    contact_id VARCHAR(36), 
    persona_id VARCHAR(36), 
    persona_version INTEGER, 
    language VARCHAR(10) NOT NULL, 
    purpose TEXT NOT NULL, 
    starting_point VARCHAR(60) NOT NULL, 
    tone VARCHAR(30) NOT NULL, 
    subject TEXT NOT NULL, 
    body_html TEXT NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    revision INTEGER NOT NULL, 
    generation_provider VARCHAR(30) NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(contact_id) REFERENCES contacts (id), 
    FOREIGN KEY(persona_id) REFERENCES personas (id), 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_drafts_contact_id ON drafts (contact_id);

CREATE INDEX ix_drafts_workspace_id ON drafts (workspace_id);

CREATE TABLE persona_revisions (
    persona_id VARCHAR(36) NOT NULL, 
    version INTEGER NOT NULL, 
    data JSON NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(persona_id) REFERENCES personas (id), 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id), 
    UNIQUE (workspace_id, persona_id, version)
);

CREATE INDEX ix_persona_revisions_persona_id ON persona_revisions (persona_id);

CREATE INDEX ix_persona_revisions_workspace_id ON persona_revisions (workspace_id);

CREATE TABLE source_evidence (
    contact_id VARCHAR(36) NOT NULL, 
    provider VARCHAR(30) NOT NULL, 
    url TEXT NOT NULL, 
    title VARCHAR(500) NOT NULL, 
    snippet TEXT NOT NULL, 
    kind VARCHAR(40) NOT NULL, 
    retrieved_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(contact_id) REFERENCES contacts (id), 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_source_evidence_contact_id ON source_evidence (contact_id);

CREATE INDEX ix_source_evidence_workspace_id ON source_evidence (workspace_id);

CREATE TABLE uploaded_documents (
    original_name VARCHAR(255) NOT NULL, 
    storage_key VARCHAR(100) NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    error TEXT, 
    extracted_text TEXT NOT NULL, 
    persona_id VARCHAR(36), 
    workspace_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(persona_id) REFERENCES personas (id), 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_uploaded_documents_workspace_id ON uploaded_documents (workspace_id);

CREATE TABLE match_assessments (
    contact_id VARCHAR(36) NOT NULL, 
    persona_id VARCHAR(36) NOT NULL, 
    persona_revision_id VARCHAR(36) NOT NULL, 
    persona_version INTEGER NOT NULL, 
    contact_fingerprint VARCHAR(64) NOT NULL, 
    language VARCHAR(10) NOT NULL, 
    reason TEXT NOT NULL, 
    source_ids JSON NOT NULL, 
    provider VARCHAR(30) NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(contact_id) REFERENCES contacts (id), 
    FOREIGN KEY(persona_id) REFERENCES personas (id), 
    FOREIGN KEY(persona_revision_id) REFERENCES persona_revisions (id), 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_match_assessments_contact_id ON match_assessments (contact_id);

CREATE INDEX ix_match_assessments_workspace_id ON match_assessments (workspace_id);

INSERT INTO alembic_version (version_num) VALUES ('5aba178b468a') RETURNING alembic_version.version_num;

COMMIT;

