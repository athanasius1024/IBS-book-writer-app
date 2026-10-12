-- Terran Society Organizational Database Schema
-- Version: 1.0
-- Created: 2025-12-08

-- Metadata table
CREATE TABLE IF NOT EXISTS tMeta (
    SchemaVersion TEXT NOT NULL,
    CreatedDate TEXT NOT NULL,
    LastModified TEXT NOT NULL,
    Description TEXT
);

INSERT INTO tMeta VALUES ('1.0', datetime('now'), datetime('now'), 'Terran Society Organizational Structure Database');

-- ==============================================================================
-- CORE ORGANIZATIONAL TABLES
-- ==============================================================================

-- Tiers: District, Region, World
CREATE TABLE IF NOT EXISTS tTier (
    TierName TEXT PRIMARY KEY,
    TierCode TEXT NOT NULL UNIQUE,
    SortOrder INTEGER NOT NULL,
    DocLoc TEXT,
    IsExample INTEGER DEFAULT 0 CHECK(IsExample IN (0,1)),
    ExampleNote TEXT
);

CREATE TABLE IF NOT EXISTS tTierExplain (
    TierExplainID INTEGER PRIMARY KEY AUTOINCREMENT,
    TierName TEXT NOT NULL,
    TierExplainHeader TEXT,
    TierExplainDesc TEXT,
    DocLoc TEXT,
    SortOrder INTEGER,
    FOREIGN KEY (TierName) REFERENCES tTier(TierName) ON DELETE CASCADE
);

-- Branches: Executive, Legislative, Judicial, Fair Witness, Military
CREATE TABLE IF NOT EXISTS tBranch (
    BranchName TEXT PRIMARY KEY,
    BranchCode TEXT NOT NULL UNIQUE,
    BranchHeader TEXT,
    BranchDesc TEXT,
    SortOrder INTEGER NOT NULL,
    DocLoc TEXT,
    IsExample INTEGER DEFAULT 0 CHECK(IsExample IN (0,1)),
    ExampleNote TEXT
);

CREATE TABLE IF NOT EXISTS tBranchExplain (
    BranchExplainID INTEGER PRIMARY KEY AUTOINCREMENT,
    BranchName TEXT NOT NULL,
    BranchExplainHeader TEXT,
    BranchExplainDesc TEXT,
    DocLoc TEXT,
    SortOrder INTEGER,
    FOREIGN KEY (BranchName) REFERENCES tBranch(BranchName) ON DELETE CASCADE
);

-- Institutions: Specific organizational bodies within tiers/branches
CREATE TABLE IF NOT EXISTS tInstitution (
    InstitutionID INTEGER PRIMARY KEY AUTOINCREMENT,
    InstitutionName TEXT NOT NULL,
    TierName TEXT NOT NULL,
    BranchName TEXT NOT NULL,
    InstitutionHeader TEXT,
    InstitutionDesc TEXT,
    DocLoc TEXT,
    SortOrder INTEGER,
    IsExample INTEGER DEFAULT 0 CHECK(IsExample IN (0,1)),
    ExampleNote TEXT,
    FOREIGN KEY (TierName) REFERENCES tTier(TierName),
    FOREIGN KEY (BranchName) REFERENCES tBranch(BranchName),
    UNIQUE(InstitutionName, TierName, BranchName)
);

CREATE TABLE IF NOT EXISTS tInstitutionDtl (
    InstitutionDtlID INTEGER PRIMARY KEY AUTOINCREMENT,
    InstitutionID INTEGER NOT NULL,
    InstitutionDtlHeader TEXT,
    InstitutionDtlDesc TEXT,
    DocLoc TEXT,
    SortOrder INTEGER,
    FOREIGN KEY (InstitutionID) REFERENCES tInstitution(InstitutionID) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tInstitutionExplain (
    InstitutionExplainID INTEGER PRIMARY KEY AUTOINCREMENT,
    InstitutionID INTEGER NOT NULL,
    InstitutionExplainHeader TEXT,
    InstitutionExplainDesc TEXT,
    DocLoc TEXT,
    SortOrder INTEGER,
    FOREIGN KEY (InstitutionID) REFERENCES tInstitution(InstitutionID) ON DELETE CASCADE
);

-- ==============================================================================
-- ROLES AND DUTIES
-- ==============================================================================

-- Roles: Specific positions/offices within institutions
CREATE TABLE IF NOT EXISTS tRole (
    RoleID INTEGER PRIMARY KEY AUTOINCREMENT,
    RoleName TEXT NOT NULL,
    InstitutionID INTEGER NOT NULL,
    RoleTitle TEXT,
    RoleDesc TEXT,
    TermLengthYears INTEGER,
    HasTermLimit INTEGER DEFAULT 0 CHECK(HasTermLimit IN (0,1)),
    TermLimitYears INTEGER,
    MaxConsecutiveTerms INTEGER,
    ElectionMethod TEXT CHECK(ElectionMethod IN ('Direct', 'Appointed', 'Internal', 'Mixed', NULL)),
    DocLoc TEXT,
    SortOrder INTEGER,
    IsExample INTEGER DEFAULT 0 CHECK(IsExample IN (0,1)),
    ExampleNote TEXT,
    FOREIGN KEY (InstitutionID) REFERENCES tInstitution(InstitutionID) ON DELETE CASCADE,
    UNIQUE(RoleName, InstitutionID)
);

CREATE TABLE IF NOT EXISTS tRoleDuty (
    RoleDutyID INTEGER PRIMARY KEY AUTOINCREMENT,
    RoleID INTEGER NOT NULL,
    RoleDutyHeader TEXT,
    RoleDutyDesc TEXT NOT NULL,
    DocLoc TEXT,
    SortOrder INTEGER,
    FOREIGN KEY (RoleID) REFERENCES tRole(RoleID) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tRoleExplain (
    RoleExplainID INTEGER PRIMARY KEY AUTOINCREMENT,
    RoleID INTEGER NOT NULL,
    RoleExplainHeader TEXT,
    RoleExplainDesc TEXT,
    DocLoc TEXT,
    SortOrder INTEGER,
    FOREIGN KEY (RoleID) REFERENCES tRole(RoleID) ON DELETE CASCADE
);

-- ==============================================================================
-- PROCESSES AND PROCEDURES
-- ==============================================================================

-- Processes: Operational procedures and workflows
CREATE TABLE IF NOT EXISTS tProc (
    ProcID INTEGER PRIMARY KEY AUTOINCREMENT,
    ProcName TEXT NOT NULL UNIQUE,
    ProcScope TEXT,
    ProcHeader TEXT,
    ProcDesc TEXT,
    DocLoc TEXT,
    SortOrder INTEGER,
    IsExample INTEGER DEFAULT 0 CHECK(IsExample IN (0,1)),
    ExampleNote TEXT
);

CREATE TABLE IF NOT EXISTS tProcDtl (
    ProcDtlID INTEGER PRIMARY KEY AUTOINCREMENT,
    ProcID INTEGER NOT NULL,
    ProcDtlHeader TEXT,
    ProcDtlDesc TEXT NOT NULL,
    StepNumber INTEGER,
    DocLoc TEXT,
    SortOrder INTEGER,
    FOREIGN KEY (ProcID) REFERENCES tProc(ProcID) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tProcExplain (
    ProcExplainID INTEGER PRIMARY KEY AUTOINCREMENT,
    ProcID INTEGER NOT NULL,
    ProcExplainHeader TEXT,
    ProcExplainDesc TEXT,
    DocLoc TEXT,
    SortOrder INTEGER,
    FOREIGN KEY (ProcID) REFERENCES tProc(ProcID) ON DELETE CASCADE
);

-- Process-Institution relationship (many-to-many)
CREATE TABLE IF NOT EXISTS tProcInstitution (
    ProcInstID INTEGER PRIMARY KEY AUTOINCREMENT,
    ProcID INTEGER NOT NULL,
    InstitutionID INTEGER NOT NULL,
    RelationshipType TEXT CHECK(RelationshipType IN ('Primary', 'Secondary', 'Oversight', 'Support')),
    FOREIGN KEY (ProcID) REFERENCES tProc(ProcID) ON DELETE CASCADE,
    FOREIGN KEY (InstitutionID) REFERENCES tInstitution(InstitutionID) ON DELETE CASCADE,
    UNIQUE(ProcID, InstitutionID)
);

-- ==============================================================================
-- GLOSSARY TERMS
-- ==============================================================================

CREATE TABLE IF NOT EXISTS tGlossary (
    GlossaryID INTEGER PRIMARY KEY AUTOINCREMENT,
    Term TEXT NOT NULL UNIQUE,
    ShortDef TEXT NOT NULL,
    LongDef TEXT,
    Category TEXT CHECK(Category IN ('Role', 'Institution', 'Branch', 'Tier', 'Process', 'General')),
    RelatedID INTEGER,
    DocLoc TEXT,
    SortOrder INTEGER
);

-- ==============================================================================
-- USEFUL VIEWS
-- ==============================================================================

-- Full role view with hierarchy
CREATE VIEW IF NOT EXISTS vRoleFull AS
SELECT 
    r.RoleID,
    r.RoleName,
    r.RoleTitle,
    r.RoleDesc,
    r.TermLengthYears,
    r.HasTermLimit,
    r.TermLimitYears,
    r.MaxConsecutiveTerms,
    r.ElectionMethod,
    i.InstitutionName,
    i.TierName,
    i.BranchName,
    r.DocLoc,
    r.IsExample
FROM tRole r
JOIN tInstitution i ON r.InstitutionID = i.InstitutionID
ORDER BY i.TierName, i.BranchName, i.InstitutionName, r.SortOrder;

-- Full institution view
CREATE VIEW IF NOT EXISTS vInstitutionFull AS
SELECT 
    i.InstitutionID,
    i.InstitutionName,
    i.TierName,
    i.BranchName,
    i.InstitutionHeader,
    i.InstitutionDesc,
    i.DocLoc,
    i.IsExample,
    COUNT(DISTINCT r.RoleID) as RoleCount
FROM tInstitution i
LEFT JOIN tRole r ON i.InstitutionID = r.InstitutionID
GROUP BY i.InstitutionID
ORDER BY i.TierName, i.BranchName, i.SortOrder;

-- Process with institutions
CREATE VIEW IF NOT EXISTS vProcFull AS
SELECT 
    p.ProcID,
    p.ProcName,
    p.ProcScope,
    p.ProcHeader,
    p.ProcDesc,
    GROUP_CONCAT(DISTINCT i.InstitutionName, ', ') as Institutions,
    p.DocLoc,
    p.IsExample
FROM tProc p
LEFT JOIN tProcInstitution pi ON p.ProcID = pi.ProcID
LEFT JOIN tInstitution i ON pi.InstitutionID = i.InstitutionID
GROUP BY p.ProcID
ORDER BY p.SortOrder;

-- ==============================================================================
-- INDEXES FOR PERFORMANCE
-- ==============================================================================

CREATE INDEX IF NOT EXISTS idx_institution_tier_branch ON tInstitution(TierName, BranchName);
CREATE INDEX IF NOT EXISTS idx_role_institution ON tRole(InstitutionID);
CREATE INDEX IF NOT EXISTS idx_role_duty_role ON tRoleDuty(RoleID);
CREATE INDEX IF NOT EXISTS idx_proc_dtl_proc ON tProcDtl(ProcID);
CREATE INDEX IF NOT EXISTS idx_proc_inst_proc ON tProcInstitution(ProcID);
CREATE INDEX IF NOT EXISTS idx_proc_inst_institution ON tProcInstitution(InstitutionID);
CREATE INDEX IF NOT EXISTS idx_glossary_term ON tGlossary(Term);
CREATE INDEX IF NOT EXISTS idx_glossary_category ON tGlossary(Category);
