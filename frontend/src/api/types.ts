export type RiskCaseStatus = "new" | "observing" | "dispatched" | "rejected" | "resolved";
export type MaintenanceRequestStatus =
  | "draft"
  | "approved"
  | "in_progress"
  | "completed"
  | "rejected"
  | "cancelled";
export type DecisionAction = "observe" | "dispatch" | "reject" | "clarify";

export interface ObjectOut {
  id: number;
  external_id: string | null;
  parent_id: number | null;
  name: string;
  district: string | null;
  kind: string | null;
  geometry_wkt: string | null;
  geometry_source: string | null;
}

export interface ObjectTreeNode {
  id: number;
  external_id: string | null;
  name: string;
  kind: string | null;
  hierarchy_level: number | null;
  parent_id: number | null;
  own_open_risk_count: number;
  own_max_priority_rank: number;
  aggregated_open_risk_count: number;
  aggregated_max_priority_rank: number;
  aggregated_max_priority: "none" | "medium" | "high";
  children: ObjectTreeNode[];
}

export interface ObjectsTreeResponse {
  roots: ObjectTreeNode[];
}

export type DegradationTrendStatus = "worsening" | "stable" | "improving" | "insufficient_data";

// Динамика частоты "чистых" эпизодов неисправности канала — НЕ прогноз износа оборудования
// (данных о возрасте/дате установки нет и не будет). См.
// docs/ТЗ_тренд_деградации_канала.md, раздел 7 — обязательная оговорка везде, где показано.
export interface DegradationTrendOut {
  channel_id: number;
  as_of: string;
  recent_window_days: number;
  baseline_window_days: number;
  recent_count: number;
  baseline_count: number;
  status: DegradationTrendStatus;
}

export interface ChannelOut {
  id: number;
  external_channel_id: number;
  object_id: number | null;
  device_id: number | null;
  sensor_type: string;
  location_tag: string | null;
  display_name: string | null;
  degradation_trend?: DegradationTrendOut | null;
}

export interface EpisodeOut {
  id: number;
  start_time: string;
  end_time: string | null;
  is_flapping_incident: boolean;
  left_censored: boolean;
  right_censored: boolean;
}

export interface RiskCaseOut {
  id: number;
  channel_id: number;
  category: string;
  status: RiskCaseStatus;
  priority: string | null;
  opened_at: string;
  closed_at: string | null;
  latest_probability: number | null;
  channel_label: string | null;
  channel_external_id: number | null;
}

export interface PredictionOut {
  id: number;
  channel_id: number;
  risk_case_id: number | null;
  model_version_id: number;
  category: string;
  probability: number;
  window_start: string;
  window_end: string;
  threshold_used: number | null;
  explanation: Record<string, unknown> | null;
  data_quality_flag: string | null;
  created_at: string;
}

export interface MaintenanceRequestOut {
  id: number;
  risk_case_id: number;
  work_type: string;
  justification: string | null;
  priority: string | null;
  recommended_by: string | null;
  status: MaintenanceRequestStatus;
  approved_by_user_id: number | null;
  approved_by_username: string | null;
  approved_at: string | null;
  created_at: string;
  category: string | null;
  channel_label: string | null;
  object_name: string | null;
}

export interface ModelVersionOut {
  id: number;
  name: string;
  sensor_types: string;
  trained_at: string;
  threshold: number | null;
  metrics: Record<string, unknown> | null;
  is_active: boolean;
}

export interface DashboardSummary {
  risk_cases: {
    total: number;
    total_open: number;
    by_status: Record<string, number>;
    by_category: Record<string, number>;
    open_by_priority: Record<string, number>;
    open_with_anomaly: number;
  };
  requests: {
    by_status: Record<string, number>;
  };
  top_objects: { object_id: number; name: string; open_risk_count: number }[];
  models: {
    id: number;
    name: string;
    sensor_types: string;
    threshold: number | null;
    trained_at: string;
    roc_auc_test: number | null;
    target_met: boolean | null;
  }[];
  last_prediction_by_category: Record<string, string>;
  worker: {
    virtual_time: string;
    updated_at: string;
    seconds_since_update: number;
    is_stale: boolean;
  } | null;
  daily_volume: { date: string; opened: number; closed: number }[];
  top_worsening_channels: {
    channel_id: number;
    label: string;
    recent_count: number;
    baseline_count: number;
  }[];
}

export type UserRole = "admin" | "dispatcher" | "analyst";

export interface UserOut {
  id: number;
  username: string;
  role: UserRole;
  is_active: boolean;
  object_ids: number[];
}

export interface AuditLogEntry {
  id: number;
  user_id: number | null;
  username: string | null;
  role: string | null;
  entity_type: string;
  entity_id: number;
  old_state: Record<string, unknown> | null;
  new_state: Record<string, unknown> | null;
  reason: string | null;
  created_at: string;
}
