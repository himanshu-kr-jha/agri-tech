"""All ORM models.

Importing this package registers every table on ``Base.metadata`` — which is what Alembic
autogenerate reads. A model that is not imported here does not exist as far as migrations
are concerned, so add new modules to the imports below.
"""

from agrivardhak.domain.models.crops import (
    Crop,
    CropCycle,
    InputApplication,
    Variety,
)
from agrivardhak.domain.models.decisions import (
    Approval,
    Attribution,
    DecisionPacket,
    EvidenceSnapshot,
    Intervention,
    Outcome,
    Prediction,
    Recommendation,
)
from agrivardhak.domain.models.land import (
    Farm,
    FarmResource,
    Plot,
    PlotTenure,
    ResourceFlow,
)
from agrivardhak.domain.models.market import (
    Buyer,
    BuyerMatch,
    DemandSignal,
    Lot,
    LotItem,
    NewsEvent,
    RiskRegisterEntry,
    Sale,
)
from agrivardhak.domain.models.operations import (
    AuditRecord,
    CalendarEvent,
    Consent,
    ConversationTurn,
    DomainEvent,
    LlmCallLog,
    Task,
)
from agrivardhak.domain.models.organization import (
    Announcement,
    Farmer,
    GovernanceProfile,
    Membership,
    Organization,
    OrgResource,
    RoleGrant,
    User,
)
from agrivardhak.domain.models.provenance import (
    AttributePolicy,
    DataDiscrepancy,
    DataSource,
    ExternalRecord,
    Observation,
)
from agrivardhak.domain.models.schemes import (
    EligibilityAssessment,
    FundingAllocation,
    FundingRequirement,
    Scheme,
    SchemeApplication,
)

__all__ = [
    "Announcement",
    "Approval",
    "AttributePolicy",
    "Attribution",
    "AuditRecord",
    "Buyer",
    "BuyerMatch",
    "CalendarEvent",
    "Consent",
    "ConversationTurn",
    "Crop",
    "CropCycle",
    "DataDiscrepancy",
    "DataSource",
    "DecisionPacket",
    "DemandSignal",
    "DomainEvent",
    "EligibilityAssessment",
    "EvidenceSnapshot",
    "ExternalRecord",
    "Farm",
    "FarmResource",
    "Farmer",
    "FundingAllocation",
    "FundingRequirement",
    "GovernanceProfile",
    "InputApplication",
    "Intervention",
    "LlmCallLog",
    "Lot",
    "LotItem",
    "Membership",
    "NewsEvent",
    "Observation",
    "OrgResource",
    "Organization",
    "Outcome",
    "Plot",
    "PlotTenure",
    "Prediction",
    "Recommendation",
    "ResourceFlow",
    "RiskRegisterEntry",
    "RoleGrant",
    "Sale",
    "Scheme",
    "SchemeApplication",
    "Task",
    "User",
    "Variety",
]
