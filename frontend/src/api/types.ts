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

export interface ChannelOut {
  id: number;
  external_channel_id: number;
  object_id: number | null;
  device_id: number | null;
  sensor_type: string;
  location_tag: string | null;
  display_name: string | null;
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
  approved_at: string | null;
}
