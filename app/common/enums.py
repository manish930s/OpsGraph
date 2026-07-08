from enum import Enum

class Severity(str, Enum):
    SEV_1 = "SEV-1"
    SEV_2 = "SEV-2"
    SEV_3 = "SEV-3"
    SEV_4 = "SEV-4"

class EnvironmentName(str, Enum):
    PRODUCTION = "production"
    PRODUCTION_SIM = "production-sim"
    STAGING = "staging"
    DEVELOPMENT = "development"

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class SourceType(str, Enum):
    LOG = "log"
    METRIC = "metric"
    TRACE = "trace"
    DEPLOYMENT = "deployment"
    TOPOLOGY = "topology"
    HISTORICAL_INCIDENT = "historical_incident"
    RUNBOOK = "runbook"
    ARCHITECTURE_DOCUMENT = "architecture_document"
    TROUBLESHOOTING_DOCUMENT = "troubleshooting_document"

class ActionType(str, Enum):
    DIAGNOSTIC = "diagnostic"
    CONTAINMENT = "containment"
    REMEDIATION = "remediation"
    VERIFICATION = "verification"

class FaultCategory(str, Enum):
    DATABASE_CONNECTION_POOL = "database_connection_pool"
    DATABASE_QUERY_LATENCY = "database_query_latency"
    DATABASE_CONNECTION_FAILURE = "database_connection_failure"
    DATABASE_CAPACITY_SATURATION = "database_capacity_saturation"
    
    MEMORY_LEAK = "memory_leak"
    CPU_SATURATION = "cpu_saturation"
    THREAD_POOL_EXHAUSTION = "thread_pool_exhaustion"
    BAD_DEPLOYMENT = "bad_deployment"
    CONFIGURATION_REGRESSION = "configuration_regression"
    
    DOWNSTREAM_TIMEOUT = "downstream_timeout"
    DOWNSTREAM_ERROR_SPIKE = "downstream_error_spike"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    
    QUEUE_BACKLOG = "queue_backlog"
    CONSUMER_LAG = "consumer_lag"
    CONSUMER_FAILURE = "consumer_failure"
    
    DISK_SATURATION = "disk_saturation"
    NETWORK_LATENCY = "network_latency"
    DNS_RESOLUTION_FAILURE = "dns_resolution_failure"
