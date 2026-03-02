import Foundation

struct CohortDefinition {
    let key: String
    let label: String
    let members: Set<String>
}

let MHIResearchersSourceURL = "https://uwaterloo.ca/public-health-sciences/our-people/health-informatics-researchers"
let MHIProgramLaunchYear = 2013

// Optional alternative cohort for sensitivity analysis.
// Populate using the same "SURNAME, GIVEN NAME" convention as other lists.
let BiasConcernFacultyNames: [String] = [
]

// Primary analysis cohort: MHI core faculty hired in/after MHI launch era.
// This intentionally excludes legacy HI-roster names (e.g., LIU, LILI; HIRDES, JOHN).
let FocusedMHIFacultyNamesSince2013: [String] = [
    "CHAURASIA, ASHOK",
    "CHEN, HELEN H.",
    "LEE, JOON",
    "LEE, JOON H.",
    "LUO, HAO",
    "MORITA, PLINIO",
    "TORRES ESPIN, ABEL",
    "WALLACE, JAMES R."
]

// Optional full-roster sensitivity cohort from the public UW HI page.
let IncludeFullRosterMHISensitivity = false

func canonicalFacultyName(_ raw: String) -> String {
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    return trimmed.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
}

func canonicalNameSet(_ names: [String]) -> Set<String> {
    Set(names.map(canonicalFacultyName))
}

let primaryMHICohort = CohortDefinition(
    key: "mhi_post2013_core",
    label: "MHI (Post-2013 Core Cohort)",
    members: canonicalNameSet(FocusedMHIFacultyNamesSince2013)
)

let fullRosterMHICohort = CohortDefinition(
    key: "mhi_uw_hi_researchers_full",
    label: "MHI (UW Health Informatics Researchers, Full Roster)",
    members: canonicalNameSet(MHIFacultyNames)
)

let biasConcernCohort = CohortDefinition(
    key: "bias_concern_sensitivity",
    label: "Bias-Concern Sensitivity Cohort",
    members: canonicalNameSet(BiasConcernFacultyNames)
)

var analysisCohorts: [CohortDefinition] {
    var cohorts = [primaryMHICohort]
    if IncludeFullRosterMHISensitivity {
        cohorts.append(fullRosterMHICohort)
    }
    if !biasConcernCohort.members.isEmpty {
        cohorts.append(biasConcernCohort)
    }
    return cohorts
}

func isInPrimaryMHICohort(_ fullName: String) -> Bool {
    primaryMHICohort.members.contains(canonicalFacultyName(fullName))
}
