import Foundation

struct CohortDefinition {
    let key: String
    let label: String
    let members: Set<String>
}

let MHIResearchersSourceURL = "https://uwaterloo.ca/public-health-sciences/our-people/health-informatics-researchers"

// Optional alternative cohort for sensitivity analysis.
// Populate using the same "SURNAME, GIVEN NAME" convention as other lists.
let BiasConcernFacultyNames: [String] = [
]

func canonicalFacultyName(_ raw: String) -> String {
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    return trimmed.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
}

func canonicalNameSet(_ names: [String]) -> Set<String> {
    Set(names.map(canonicalFacultyName))
}

let primaryMHICohort = CohortDefinition(
    key: "mhi_uw_hi_researchers",
    label: "MHI (UW Health Informatics Researchers)",
    members: canonicalNameSet(MHIFacultyNames)
)

let biasConcernCohort = CohortDefinition(
    key: "bias_concern_sensitivity",
    label: "Bias-Concern Sensitivity Cohort",
    members: canonicalNameSet(BiasConcernFacultyNames)
)

var analysisCohorts: [CohortDefinition] {
    var cohorts = [primaryMHICohort]
    if !biasConcernCohort.members.isEmpty {
        cohorts.append(biasConcernCohort)
    }
    return cohorts
}

func isInPrimaryMHICohort(_ fullName: String) -> Bool {
    primaryMHICohort.members.contains(canonicalFacultyName(fullName))
}
