// GENERATED FILE — run scripts/generate-contracts.py; do not edit manually.

export interface DependencyStatus {
  status: string;
  reason?: string | null;
}

export interface HealthResponse {
  service: string;
  status: string;
  version: string;
}

export interface ReadinessResponse {
  service: string;
  status: string;
  dependencies: Record<string, DependencyStatus>;
}
