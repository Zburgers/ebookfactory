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

export interface ArtRevisionResultRequest {
  job_id: string;
  worker_id: string;
  generation: number;
  provider: string;
  model: string;
  art: ProductionArtRequest;
}

export interface ArtRevisionResultResponse {
  accepted: boolean;
  artifact_id: string;
  usage_call_id?: string | null;
}

export interface ArtifactReviewRequest {
  decision: string;
  note?: string | null;
  expected_owner_review_state: string;
}

export interface ArtifactReviewResponse {
  artifact_id: string;
  run_id?: string | null;
  attempt_id?: string | null;
  usage_call_id?: string | null;
  revision_id: string | null;
  relative_path: string;
  mime_type: string;
  byte_count: number;
  sha256: string;
  validation_state: string;
  owner_review_state: string;
  owner_review_note: string | null;
  owner_reviewed_at: string | null;
  download_path: string;
  generation_provider?: string | null;
  generation_model?: string | null;
  usage_outcome?: string | null;
  revision_job_id?: string | null;
  revision_task_id?: string | null;
}

export interface ArtifactView {
  artifact_id: string;
  run_id?: string | null;
  attempt_id?: string | null;
  usage_call_id?: string | null;
  revision_id: string | null;
  relative_path: string;
  mime_type: string;
  byte_count: number;
  sha256: string;
  validation_state: string;
  owner_review_state: string;
  owner_review_note: string | null;
  owner_reviewed_at: string | null;
  download_path: string;
  generation_provider?: string | null;
  generation_model?: string | null;
  usage_outcome?: string | null;
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

export interface ExportRequest {
  art_artifact_id?: string | null;
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

export interface LiveQuotaResponse {
  fetched_at: string;
  source: string;
  windows: Array<LiveQuotaWindow>;
}

export interface LiveQuotaWindow {
  account_index: number;
  window_seconds: number;
  used: number;
  remaining: number;
  reset: string;
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
  turn_id?: string | null;
  queued?: boolean;
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

export interface ModelCatalogEntry {
  provider: string;
  model: string;
  qualified_model: string;
  context: string;
  max_output: string;
  thinking: boolean;
  images: boolean;
  pricing?: Record<string, unknown> | null;
}

export interface OrchestratorActivityRequest {
  turn_id: string;
  worker_id: string;
  generation: number;
  activity_type: string;
  payload?: Record<string, unknown>;
}

export interface OrchestratorClaimRequest {
  worker_id: string;
  lease_seconds?: number;
}

export interface OrchestratorDeltaRequest {
  turn_id: string;
  worker_id: string;
  generation: number;
  delta: string;
}

export interface OrchestratorFailureRequest {
  turn_id: string;
  worker_id: string;
  generation: number;
  error: string;
}

export interface OrchestratorGateRequest {
  turn_id: string;
  worker_id: string;
  generation: number;
  gate: string;
  status: string;
  note?: string | null;
  evidence?: Array<string>;
}

export interface OrchestratorHeartbeatRequest {
  turn_id: string;
  worker_id: string;
  generation: number;
  lease_seconds?: number;
}

export interface OrchestratorLeaseResponse {
  turn_id: string;
  worker_id: string;
  generation: number;
  lease_until: string;
}

export interface OrchestratorResultRequest {
  turn_id: string;
  worker_id: string;
  generation: number;
  content: string;
  provider: string;
  model: string;
  call_id: string;
  usage?: Record<string, number | null> | null;
}

export interface OrchestratorSpawnRequest {
  turn_id: string;
  worker_id: string;
  generation: number;
  role: string;
  instruction: string;
  context?: Record<string, unknown>;
}

export interface OwnerAuthResponse {
  authenticated: boolean;
}

export interface OwnerLoginRequest {
  token: string;
}

export interface PackagePreviewReviewRequest {
  decision: string;
  surface: string;
  tool_version: string;
  artifact_sha256: string;
  notes?: string | null;
}

export interface PackagePreviewReviewResponse {
  project_id: string;
  revision_id: string;
  artifact_id: string;
  artifact_sha256: string;
  byte_count: number;
  decision: string;
  surface: string;
  tool_version: string;
  notes: string | null;
  reviewed_at: string;
  package_state: string;
}

export interface ProductionArtRequest {
  filename: string;
  mime_type: string;
  byte_count: number;
  content_base64: string;
  call_id?: string | null;
  provider_request_id?: string | null;
  usage?: ProductionUsageRequest | null;
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
  art?: ProductionArtRequest | null;
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

export interface ProviderCatalogResponse {
  fetched_at: string;
  source: string;
  models: Array<ModelCatalogEntry>;
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

export interface ProviderMetadataResponse {
  provider: string;
  scope: string;
  protocol: string | null;
  orchestration_model: string | null;
  drafting_model: string | null;
  review_model: string | null;
  credential_configured: boolean;
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

export interface TaskResultRequest {
  job_id: string;
  worker_id: string;
  generation: number;
  result: string;
  provider: string;
  model: string;
  call_id?: string | null;
  provider_request_id?: string | null;
  usage?: ProductionUsageRequest | null;
}

export interface TaskResultResponse {
  accepted: boolean;
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
  linked_project_count: number;
  next_update_id: number;
}

export interface TelegramUpdateResponse {
  accepted: boolean;
  duplicate: boolean;
  reason?: string | null;
  message_id?: string | null;
  callback_id?: string | null;
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
  cache_read_tokens?: number | null;
  cache_write_tokens?: number | null;
  output_tokens?: number | null;
  reasoning_tokens?: number | null;
  provider_request_id?: string | null;
}

export interface UsageFinalizeRequest {
  outcome?: string | null;
  input_tokens?: number | null;
  cache_read_tokens?: number | null;
  cache_write_tokens?: number | null;
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

export interface WorkerActivityRequest {
  job_id: string;
  worker_id: string;
  generation: number;
  activity_type: string;
  payload?: Record<string, unknown>;
}

export interface WorkerClaimRequest {
  worker_id: string;
  lease_seconds?: number;
}

export interface WorkerJobContextResponse {
  project_id: string;
  run_id: string;
  task_id: string;
  job_id: string;
  task_type: string;
  cancellation_epoch: number;
  profile: string;
  language: string;
  brief: Record<string, unknown>;
  budget: Record<string, unknown>;
  instruction?: string | null;
  agent_context?: Record<string, unknown>;
  outline?: WorkerOutlineContext | null;
  section?: WorkerSectionContext | null;
  art_revision?: Record<string, string> | null;
  assembly?: boolean;
  review_sections?: Array<WorkerReviewSection>;
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

export interface WorkerOutlineContext {
  task_id: string;
  result: string;
}

export interface WorkerReviewSection {
  section_id: string;
  revision_id: string;
  heading: string;
  content: string;
}

export interface WorkerSectionContext {
  section_id: string;
  heading: string;
  outline: string;
}
