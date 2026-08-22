"""Domain enumerations.

These are the ubiquitous language in executable form (docs/GLOSSARY.md). Values are the
strings stored in Postgres enums; renaming one is a migration, not a refactor.
"""

from enum import StrEnum

# --------------------------------------------------------------------------- organization


class OrganizationType(StrEnum):
    """ADR-0002: one Organization abstraction, discriminated by type."""

    FPO = "FPO"
    PACS = "PACS"
    SHG = "SHG"
    FPC = "FPC"
    COOPERATIVE = "COOPERATIVE"


class MembershipRole(StrEnum):
    MEMBER = "MEMBER"
    DIRECTOR = "DIRECTOR"
    STAFF = "STAFF"


class MembershipStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    EXITED = "EXITED"


class OrgResourceType(StrEnum):
    """FR-103. Absent resources are represented as unknown, never as zero."""

    WORKING_CAPITAL = "WORKING_CAPITAL"
    WAREHOUSE = "WAREHOUSE"
    COLD_STORAGE = "COLD_STORAGE"
    MACHINERY = "MACHINERY"
    VEHICLE = "VEHICLE"
    PROCESSING_UNIT = "PROCESSING_UNIT"
    INPUT_INVENTORY = "INPUT_INVENTORY"


# --------------------------------------------------------------------------- roles & access


class Role(StrEnum):
    """Three roles for MVP (context.md §4). Permissions are the union of grants (FR-104)."""

    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    FPO_CEO = "FPO_CEO"
    FARMER = "FARMER"
    # Designed for, not granted in MVP:
    FIELD_OFFICER = "FIELD_OFFICER"
    MARKET_OFFICER = "MARKET_OFFICER"
    FINANCE_OFFICER = "FINANCE_OFFICER"
    RESEARCHER = "RESEARCHER"


class VisibilityScope(StrEnum):
    """INV-5. The information boundary, enforced in SQL (DATA-MODEL.md §7)."""

    OWNER = "OWNER"
    ORG_INTERNAL = "ORG_INTERNAL"
    SHARED_WITH_MEMBERS = "SHARED_WITH_MEMBERS"
    PUBLIC = "PUBLIC"


# --------------------------------------------------------------------------- land & crops


class TenureType(StrEnum):
    """ADR-0003: ownership, cultivation and membership are three separate things."""

    OWNED = "OWNED"
    LEASED = "LEASED"
    SHARECROPPED = "SHARECROPPED"
    JOINT = "JOINT"
    ALLOTTED = "ALLOTTED"
    OTHER = "OTHER"


class Season(StrEnum):
    KHARIF = "KHARIF"
    RABI = "RABI"
    ZAID = "ZAID"
    PERENNIAL = "PERENNIAL"


class CropCycleStatus(StrEnum):
    PLANNED = "PLANNED"
    SOWN = "SOWN"
    GROWING = "GROWING"
    HARVEST_READY = "HARVEST_READY"
    HARVESTED = "HARVESTED"
    SOLD = "SOLD"
    CLOSED = "CLOSED"
    ABANDONED = "ABANDONED"


class Grade(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    REJECT = "REJECT"


class FarmResourceType(StrEnum):
    """Integrated farming as one entity, not six subsystems (DATA-MODEL.md Q5)."""

    CROP = "CROP"
    LIVESTOCK = "LIVESTOCK"
    POULTRY = "POULTRY"
    FISHERY = "FISHERY"
    COMPOST = "COMPOST"
    MANURE = "MANURE"
    AGROFORESTRY = "AGROFORESTRY"
    WATER = "WATER"
    EQUIPMENT = "EQUIPMENT"
    STRUCTURE = "STRUCTURE"


class ResourceFlowType(StrEnum):
    FEED = "FEED"
    FERTILITY = "FERTILITY"
    WATER = "WATER"
    ENERGY = "ENERGY"
    RESIDUE = "RESIDUE"
    LABOUR = "LABOUR"
    INCOME = "INCOME"


class InputCategory(StrEnum):
    SEED = "SEED"
    NUTRIENT = "NUTRIENT"
    CROP_PROTECTION = "CROP_PROTECTION"
    WATER = "WATER"
    LABOUR = "LABOUR"
    ENERGY = "ENERGY"


# --------------------------------------------------------------------------- provenance


class SourceType(StrEnum):
    """INV-3. Base trust weights live in provenance/trust.py."""

    FIELD_OFFICER = "FIELD_OFFICER"
    FARMER_SELF_REPORT = "FARMER_SELF_REPORT"
    AI_INFERENCE = "AI_INFERENCE"
    EXTERNAL_SOURCE = "EXTERNAL_SOURCE"
    ORG_RECORD = "ORG_RECORD"
    FIXTURE = "FIXTURE"


class VerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    DISPUTED = "DISPUTED"
    SUPERSEDED = "SUPERSEDED"


class DiscrepancyStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    ACCEPTED = "ACCEPTED"


# --------------------------------------------------------------------------- decisions


class RecommendationStatus(StrEnum):
    """INV-1. No code path may reach EXECUTED without a persisted Approval (FR-707)."""

    SUGGESTED = "SUGGESTED"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"
    OUTCOME_RECORDED = "OUTCOME_RECORDED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class RecommendationType(StrEnum):
    BUYER_SELECTION = "BUYER_SELECTION"
    LOT_ALLOCATION = "LOT_ALLOCATION"
    CROP_PLAN = "CROP_PLAN"
    CROP_PROTECTION = "CROP_PROTECTION"
    FUNDING_ALLOCATION = "FUNDING_ALLOCATION"
    PROCUREMENT = "PROCUREMENT"
    SCHEME_PURSUIT = "SCHEME_PURSUIT"
    RISK_MITIGATION = "RISK_MITIGATION"
    SCHEDULE = "SCHEDULE"


class ApprovalDecision(StrEnum):
    APPROVED = "APPROVED"
    APPROVED_WITH_MODIFICATION = "APPROVED_WITH_MODIFICATION"
    REJECTED = "REJECTED"


class Adherence(StrEnum):
    """INV-7. Attribution is refused when this is UNKNOWN (FR-1004)."""

    YES = "YES"
    PARTIAL = "PARTIAL"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


class AttributionStrength(StrEnum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    UNCERTAIN = "UNCERTAIN"
    CONFOUNDED = "CONFOUNDED"


# --------------------------------------------------------------------------- risk & market


class RiskDomain(StrEnum):
    """The seven domains agreed in discovery (FR-551)."""

    CLIMATE = "CLIMATE"
    WEATHER = "WEATHER"
    CROP_HEALTH = "CROP_HEALTH"
    MARKET = "MARKET"
    POLICY = "POLICY"
    SUPPLY_CHAIN = "SUPPLY_CHAIN"
    GLOBAL = "GLOBAL"


class RiskStatus(StrEnum):
    OPEN = "OPEN"
    MITIGATING = "MITIGATING"
    CLOSED = "CLOSED"


class Likelihood(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Impact(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class BuyerType(StrEnum):
    WHOLESALER = "WHOLESALER"
    PROCESSOR = "PROCESSOR"
    RETAILER = "RETAILER"
    EXPORTER = "EXPORTER"
    INSTITUTIONAL = "INSTITUTIONAL"
    GOVERNMENT = "GOVERNMENT"
    ECOMMERCE = "ECOMMERCE"
    AGGREGATOR = "AGGREGATOR"


# --------------------------------------------------------------------------- schemes


class EligibilityStatus(StrEnum):
    """FR-561. INSUFFICIENT_DATA is never silently downgraded to NOT_ELIGIBLE."""

    ELIGIBLE = "ELIGIBLE"
    LIKELY_ELIGIBLE = "LIKELY_ELIGIBLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


class ApplicationStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    ELIGIBLE = "ELIGIBLE"
    DOCUMENTS_PENDING = "DOCUMENTS_PENDING"
    APPLIED = "APPLIED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# --------------------------------------------------------------------------- calendar


class CalendarOrigin(StrEnum):
    MANUAL = "MANUAL"
    AUTO_GENERATED = "AUTO_GENERATED"
    AI_RECOMMENDED = "AI_RECOMMENDED"
    OFFICIAL_DEADLINE = "OFFICIAL_DEADLINE"


class CalendarStatus(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TaskStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


# --------------------------------------------------------------------------- governance


class ConsentPurpose(StrEnum):
    """INV-9. Per-purpose, revocable, versioned (FR-1101)."""

    SERVICE_DELIVERY = "SERVICE_DELIVERY"
    ORG_ANALYTICS = "ORG_ANALYTICS"
    MODEL_IMPROVEMENT = "MODEL_IMPROVEMENT"
    ANONYMIZED_RESEARCH = "ANONYMIZED_RESEARCH"


class ActorKind(StrEnum):
    HUMAN = "HUMAN"
    SYSTEM = "SYSTEM"
    AI = "AI"


class ExternalRecordKind(StrEnum):
    WEATHER = "WEATHER"
    MARKET_PRICE = "MARKET_PRICE"
    SCHEME = "SCHEME"
    NEWS = "NEWS"
    DEMAND = "DEMAND"
    FUEL_PRICE = "FUEL_PRICE"


class NewsDomain(StrEnum):
    POLICY = "POLICY"
    CLIMATE = "CLIMATE"
    MARKET = "MARKET"
    SUPPLY_CHAIN = "SUPPLY_CHAIN"
    GLOBAL = "GLOBAL"
    INPUT_PRICE = "INPUT_PRICE"
