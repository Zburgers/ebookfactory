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

export interface ReadinessResponse {
  service: string;
  status: string;
  dependencies: Record<string, DependencyStatus>;
}

export interface RunCancelRequest {
  reason: string;
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
