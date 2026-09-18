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

export interface ArtifactView {
  artifact_id: string;
  revision_id: string | null;
  relative_path: string;
  mime_type: string;
  byte_count: number;
  sha256: string;
  validation_state: string;
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

export interface ExportArtifactResponse {
  artifact_id: string;
  filename: string;
  sha256: string;
  byte_count: number;
  download_path: string;
}

export interface ExportResponse {
  revision_id: string;
  title: string;
  package_state: string;
  artifacts: Array<ExportArtifactResponse>;
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

export interface MessageView {
  message_id: string;
  sequence: number;
  channel: string;
  role: string;
  content: string;
  turn_state: string;
  created_at: string;
}

export interface ProductionOutputRequest {
  job_id: string;
  worker_id: string;
  generation: number;
  content: string;
  provider?: string | null;
  model?: string | null;
  call_id?: string | null;
  provider_request_id?: string | null;
  usage?: ProductionUsageRequest | null;
}

export interface ProductionOutputResponse {
  run_id: string;
  task_id: string;
  revision_id: string;
  artifact_id: string;
  content_hash: string;
  duplicate: boolean;
  usage_call_id?: string | null;
}

export interface ProductionUsageRequest {
  input_tokens?: number | null;
  output_tokens?: number | null;
  cache_read_tokens?: number | null;
  cache_write_tokens?: number | null;
  reasoning_tokens?: number | null;
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

export interface ProviderConnectionTestResponse {
  provider: string;
  protocol: string;
  model: string | null;
  outcome: string;
  http_status: number | null;
  response_id: string | null;
  usage: Record<string, unknown> | null;
  error: string | null;
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

export interface QuotaSnapshotRequest {
  provider: string;
  account_alias: string;
  bucket: string;
  source: string;
  observed_at: string;
  stale_after: string;
  used?: number | string | null;
  remaining?: number | string | null;
  units?: string | null;
  window_seconds?: number | null;
  resets_at?: string | null;
  plan_label?: string | null;
  capability_state: string;
  error?: string | null;
}

export interface ReadinessResponse {
  service: string;
  status: string;
  dependencies: Record<string, DependencyStatus>;
}

export interface ReviewFindingRequest {
  revision_id?: string | null;
  artifact_id?: string | null;
  severity: string;
  criterion: string;
  evidence: string;
}

export interface ReviewFindingResponse {
  finding_id: string;
}

export interface ReviewFindingView {
  finding_id: string;
  revision_id: string | null;
  artifact_id: string | null;
  severity: string;
  criterion: string;
  evidence: string;
  resolution_revision_id: string | null;
}

export interface ReviewResolutionRequest {
  resolution_revision_id: string;
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

export interface SectionView {
  section_id: string;
  order_no: number;
  heading: string;
  latest_revision_id: string | null;
  latest_revision: number | null;
  content: string | null;
  content_hash: string | null;
}

export interface TelegramLinkRequest {
  chat_id: number;
}

export interface TelegramStatusResponse {
  configured: boolean;
  token_configured: boolean;
  allowed_chat_count: number;
  allowed_sender_count: number;
  linked_chat_count: number;
  next_update_id: number;
}

export interface TelegramUpdateResponse {
  accepted: boolean;
  duplicate: boolean;
  reason?: string | null;
  message_id?: string | null;
}

export interface UsageCallRequest {
  call_id: string;
  provider: string;
  model: string;
  purpose: string;
  outcome: string;
  project_id?: string | null;
  run_id?: string | null;
  task_id?: string | null;
  attempt_id?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  reasoning_tokens?: number | null;
  provider_request_id?: string | null;
}

export interface UsageFinalizeRequest {
  outcome?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  reasoning_tokens?: number | null;
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
