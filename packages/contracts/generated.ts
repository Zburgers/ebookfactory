// GENERATED FILE — run scripts/generate-contracts.py; do not edit manually.

export interface ApprovalRequest {
  expected_content_hash: string;
  budget?: Record<string, unknown>;
}

export interface ApprovalResponse {
  run_id: string;
  task_id: string;
  job_id: string;
}

export interface BriefCreateRequest {
  structured_brief: Record<string, unknown>;
}

export interface BriefResponse {
  brief_id: string;
  content_hash: string;
}

export interface CapabilityRequest {
  job_id: string;
  worker_id: string;
  generation: number;
  tool: string;
}

export interface CapabilityResponse {
  capability: string;
  expires_in_seconds: number;
}

export interface CheckpointRequest {
  job_id: string;
  worker_id: string;
  generation: number;
  checkpoint?: Record<string, unknown>;
}

export interface CompleteRequest {
  job_id: string;
  worker_id: string;
  generation: number;
  result_refs?: Record<string, unknown>;
}

export interface DependencyStatus {
  status: string;
  reason?: string | null;
}

export interface FailRequest {
  job_id: string;
  worker_id: string;
  generation: number;
  error_class: string;
  retryable?: boolean;
  retry_after_seconds?: number | null;
}

export interface HTTPValidationError {
  detail?: Array<ValidationError>;
}

export interface HealthResponse {
  service: string;
  status: string;
  version: string;
}

export interface HeartbeatRequest {
  job_id: string;
  worker_id: string;
  generation: number;
  lease_seconds?: number;
}

export interface MessageCreateRequest {
  conversation_id: string;
  channel?: string;
  external_dedupe_id?: string | null;
  content: string;
}

export interface MessageResponse {
  message_id: string;
  sequence: number;
  duplicate: boolean;
}

export interface ProjectCreateRequest {
  title: string;
  profile: string;
  language: string;
}

export interface ProjectResponse {
  project_id: string;
  conversation_id: string;
  title: string;
  profile: string;
  language: string;
  state: string;
}

export interface ProviderSettingRequest {
  scope?: string;
  endpoint?: string | null;
  protocol?: string | null;
  credential_ref?: string | null;
  orchestration_model?: string | null;
  drafting_model?: string | null;
  review_model?: string | null;
}

export interface ProviderSettingResponse {
  setting_id: string;
  provider: string;
  scope: string;
  endpoint: string | null;
  protocol: string | null;
  orchestration_model: string | null;
  drafting_model: string | null;
  review_model: string | null;
  credential_configured: boolean;
}

export interface ReadinessResponse {
  service: string;
  status: string;
  dependencies: Record<string, DependencyStatus>;
}

export interface RunCancelRequest {
  reason: string;
}

export interface SectionCreateRequest {
  order_no: number;
  heading: string;
}

export interface SectionResponse {
  section_id: string;
}

export interface SectionRevisionRequest {
  content: string;
  summary?: string;
  expected_parent_revision_id?: string | null;
  source_refs?: Array<string>;
  knowledge_refs?: Array<string>;
}

export interface SectionRevisionResponse {
  section_id: string;
  revision_id: string;
  revision: number;
  content_hash: string;
}

export interface ValidationError {
  loc: Array<string | number>;
  msg: string;
  type: string;
  input?: Record<string, unknown>;
  ctx?: Record<string, unknown>;
}

export interface WorkerClaimRequest {
  worker_id: string;
  lease_seconds?: number;
}

export interface WorkerLeaseResponse {
  job_id: string;
  task_id: string;
  run_id: string;
  attempt_id: string;
  generation: number;
  cancellation_epoch: number;
  lease_until: string;
}
