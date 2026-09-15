import enum


class RiskCaseStatus(str, enum.Enum):
    new = "new"
    observing = "observing"
    dispatched = "dispatched"
    rejected = "rejected"
    resolved = "resolved"


class DecisionAction(str, enum.Enum):
    observe = "observe"
    dispatch = "dispatch"
    reject = "reject"
    clarify = "clarify"


class MaintenanceRequestStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    in_progress = "in_progress"
    completed = "completed"
    rejected = "rejected"
    cancelled = "cancelled"


class UserRole(str, enum.Enum):
    dispatcher = "dispatcher"
    analyst = "analyst"
    admin = "admin"


class EpisodeSource(str, enum.Enum):
    sensor_state = "sensor_state"
    dispatcher_confirmed = "dispatcher_confirmed"
    manual = "manual"
