import Foundation

struct OLSResult {
    let variableNames: [String]
    let coefficients: [Double]
    let covariance: [[Double]]
    let standardErrors: [Double]
    let nObs: Int
    let nClusters: Int
}

struct SummaryRow {
    let model: String
    let term: String
    let estimate: Double
    let standardError: Double
    let ciLower: Double
    let ciUpper: Double
    let nObs: Int
    let nClusters: Int
}

struct PermutationSummaryRow {
    let model: String
    let term: String
    let observedEstimate: Double
    let ciLower: Double
    let ciUpper: Double
    let nullMean: Double
    let nullStdDev: Double
    let nullQ025: Double
    let nullQ975: Double
    let pTwoSided: Double
    let nPermutations: Int
    let inferenceMethod: String
    let nObs: Int
    let nClusters: Int
    let nTreatedClusters: Int
}

struct AnalysisRow {
    let personID: String
    let year: Int
    let yearCentered: Double
    let salary: Double
    let mhi: Double
    let nonHealthTerminal: Double?
}

struct RegressionAnalysisConfig {
    var knotsFixed: [Int] = [2014]
    var knot2SalaryYear: Int = 2022
    var knot2SensitivityYears: [Int] = [2021, 2022, 2023]
    var matchingYearWindow: Int = 1
    var matchedSlopeHorizonYears: Int = 5
    var runPermutationInference: Bool = true
    var permutationDraws: Int = 20_000
    var permutationExactCombinationLimit: Double = 200_000
    var permutationSeedBase: UInt64 = 20240300
}

let regressionAnalysisConfig = RegressionAnalysisConfig()

struct SeededGenerator: RandomNumberGenerator {
    private var state: UInt64

    init(seed: UInt64) {
        self.state = seed == 0 ? 0xA341316C : seed
    }

    mutating func next() -> UInt64 {
        state &+= 0x9E3779B97F4A7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58476D1CE4E5B9
        z = (z ^ (z >> 27)) &* 0x94D049BB133111EB
        return z ^ (z >> 31)
    }
}

func transpose(_ matrix: [[Double]]) -> [[Double]] {
    guard let columnCount = matrix.first?.count else { return [] }
    var output = Array(repeating: Array(repeating: 0.0, count: matrix.count), count: columnCount)
    for rowIndex in matrix.indices {
        for colIndex in matrix[rowIndex].indices {
            output[colIndex][rowIndex] = matrix[rowIndex][colIndex]
        }
    }
    return output
}

func multiply(_ lhs: [[Double]], _ rhs: [[Double]]) -> [[Double]] {
    guard let sharedCount = lhs.first?.count,
          let rhsColumnCount = rhs.first?.count,
          sharedCount == rhs.count else {
        return []
    }

    var output = Array(repeating: Array(repeating: 0.0, count: rhsColumnCount), count: lhs.count)
    for i in 0..<lhs.count {
        for j in 0..<rhsColumnCount {
            var sum = 0.0
            for k in 0..<sharedCount {
                sum += lhs[i][k] * rhs[k][j]
            }
            output[i][j] = sum
        }
    }
    return output
}

func matrixVectorMultiply(_ matrix: [[Double]], _ vector: [Double]) -> [Double] {
    guard let columnCount = matrix.first?.count, columnCount == vector.count else { return [] }
    var output = Array(repeating: 0.0, count: matrix.count)
    for i in matrix.indices {
        var sum = 0.0
        for j in 0..<columnCount {
            sum += matrix[i][j] * vector[j]
        }
        output[i] = sum
    }
    return output
}

func invertMatrix(_ input: [[Double]]) -> [[Double]]? {
    let n = input.count
    guard n > 0, input.allSatisfy({ $0.count == n }) else { return nil }

    var matrix = input
    var inverse = Array(repeating: Array(repeating: 0.0, count: n), count: n)
    for i in 0..<n { inverse[i][i] = 1.0 }

    for i in 0..<n {
        var pivotRow = i
        for candidate in i..<n {
            if abs(matrix[candidate][i]) > abs(matrix[pivotRow][i]) {
                pivotRow = candidate
            }
        }

        if abs(matrix[pivotRow][i]) < 1e-12 { return nil }
        if pivotRow != i {
            matrix.swapAt(i, pivotRow)
            inverse.swapAt(i, pivotRow)
        }

        let pivot = matrix[i][i]
        for j in 0..<n {
            matrix[i][j] /= pivot
            inverse[i][j] /= pivot
        }

        for row in 0..<n where row != i {
            let factor = matrix[row][i]
            for col in 0..<n {
                matrix[row][col] -= factor * matrix[i][col]
                inverse[row][col] -= factor * inverse[i][col]
            }
        }
    }
    return inverse
}

func outerProduct(_ lhs: [Double], _ rhs: [Double]) -> [[Double]] {
    var output = Array(repeating: Array(repeating: 0.0, count: rhs.count), count: lhs.count)
    for i in lhs.indices {
        for j in rhs.indices {
            output[i][j] = lhs[i] * rhs[j]
        }
    }
    return output
}

func addInPlace(_ lhs: inout [[Double]], _ rhs: [[Double]]) {
    guard lhs.count == rhs.count else { return }
    for i in lhs.indices {
        guard lhs[i].count == rhs[i].count else { return }
        for j in lhs[i].indices {
            lhs[i][j] += rhs[i][j]
        }
    }
}

func scaleMatrix(_ matrix: [[Double]], by factor: Double) -> [[Double]] {
    var output = matrix
    for i in output.indices {
        for j in output[i].indices {
            output[i][j] *= factor
        }
    }
    return output
}

func runClusterRobustOLS(
    X: [[Double]],
    y: [Double],
    clusterIDs: [String],
    variableNames: [String]
) -> OLSResult? {
    let n = X.count
    guard n > 0, y.count == n, clusterIDs.count == n else { return nil }
    guard let k = X.first?.count, k > 0, variableNames.count == k else { return nil }
    guard X.allSatisfy({ $0.count == k }) else { return nil }

    let Xt = transpose(X)
    let XtX = multiply(Xt, X)
    guard let XtXInv = invertMatrix(XtX) else { return nil }

    var Xty = Array(repeating: 0.0, count: k)
    for i in 0..<k {
        var sum = 0.0
        for row in 0..<n {
            sum += Xt[i][row] * y[row]
        }
        Xty[i] = sum
    }
    let coefficients = matrixVectorMultiply(XtXInv, Xty)

    var residuals = Array(repeating: 0.0, count: n)
    for row in 0..<n {
        var fitted = 0.0
        for col in 0..<k {
            fitted += X[row][col] * coefficients[col]
        }
        residuals[row] = y[row] - fitted
    }

    var clusterToIndices: [String: [Int]] = [:]
    for (index, clusterID) in clusterIDs.enumerated() {
        clusterToIndices[clusterID, default: []].append(index)
    }
    let clusterCount = clusterToIndices.count
    guard clusterCount > 1 else { return nil }

    var meat = Array(repeating: Array(repeating: 0.0, count: k), count: k)
    for indices in clusterToIndices.values {
        var score = Array(repeating: 0.0, count: k)
        for row in indices {
            for col in 0..<k {
                score[col] += X[row][col] * residuals[row]
            }
        }
        addInPlace(&meat, outerProduct(score, score))
    }

    let nDouble = Double(n)
    let kDouble = Double(k)
    let gDouble = Double(clusterCount)
    let correction = (gDouble / (gDouble - 1.0)) * ((nDouble - 1.0) / (nDouble - kDouble))

    let covariance = scaleMatrix(multiply(multiply(XtXInv, meat), XtXInv), by: correction)
    let standardErrors = (0..<k).map { sqrt(max(covariance[$0][$0], 0.0)) }

    return OLSResult(
        variableNames: variableNames,
        coefficients: coefficients,
        covariance: covariance,
        standardErrors: standardErrors,
        nObs: n,
        nClusters: clusterCount
    )
}

func confidenceInterval95(estimate: Double, standardError: Double) -> (Double, Double) {
    let margin = 1.96 * standardError
    return (estimate - margin, estimate + margin)
}

func parseCSVLine(_ line: String) -> [String] {
    var fields: [String] = []
    var current = ""
    var inQuotes = false
    var index = line.startIndex

    while index < line.endIndex {
        let char = line[index]
        if char == "\"" {
            let next = line.index(after: index)
            if inQuotes, next < line.endIndex, line[next] == "\"" {
                current.append("\"")
                index = line.index(after: next)
                continue
            }
            inQuotes.toggle()
            index = line.index(after: index)
            continue
        }
        if char == ",", !inQuotes {
            fields.append(current)
            current = ""
            index = line.index(after: index)
            continue
        }
        current.append(char)
        index = line.index(after: index)
    }
    fields.append(current)
    return fields
}

func loadTerminalDegreeDomainLookup() -> [String: Double] {
    let fileManager = FileManager.default
    let baseURL = URL(fileURLWithPath: fileManager.currentDirectoryPath, isDirectory: true)
    let candidateRelativePaths = [
        "data/private_terminal_degree_domain.csv",
        "data/terminal_degree_domain.csv"
    ]

    for relativePath in candidateRelativePaths {
        let csvURL = baseURL.appendingPathComponent(relativePath)
        guard fileManager.fileExists(atPath: csvURL.path) else { continue }

        do {
            let contents = try String(contentsOf: csvURL, encoding: .utf8)
            let rawLines = contents.split(whereSeparator: \.isNewline).map(String.init)
            guard let header = rawLines.first else { continue }
            let columns = parseCSVLine(header)
            guard let salaryNameIndex = columns.firstIndex(of: "salary_name"),
                  let nonHealthIndex = columns.firstIndex(of: "is_non_health_terminal") else {
                continue
            }

            var lookup: [String: Double] = [:]
            for line in rawLines.dropFirst() where !line.trimmingCharacters(in: .whitespaces).isEmpty {
                let fields = parseCSVLine(line)
                guard salaryNameIndex < fields.count, nonHealthIndex < fields.count else { continue }
                let rawName = fields[salaryNameIndex]
                let rawFlag = fields[nonHealthIndex].trimmingCharacters(in: .whitespaces)
                guard rawFlag == "0" || rawFlag == "1" else { continue }
                lookup[canonicalFacultyName(rawName)] = rawFlag == "1" ? 1.0 : 0.0
            }

            print("Loaded terminal-degree domains from \(relativePath): \(lookup.count) faculty with known classifications.")
            return lookup
        } catch {
            print("Failed reading terminal-degree domains from \(relativePath): \(error)")
        }
    }

    print("No terminal-degree domain CSV found. Continuing without that covariate.")
    return [:]
}

func modelRowsFromRecords(
    _ records: [SalaryRecord],
    cohort: CohortDefinition,
    nonHealthTerminalByName: [String: Double]
) -> [AnalysisRow] {
    guard let minYear = records.map(\.year).min() else { return [] }
    let baseYear = Double(minYear)
    return records.map { record in
        let fullName = "\(record.surname), \(record.givenName)"
        let canonicalName = canonicalFacultyName(fullName)
        return AnalysisRow(
            personID: fullName,
            year: record.year,
            yearCentered: Double(record.year) - baseYear,
            salary: record.salary,
            mhi: cohort.members.contains(canonicalName) ? 1.0 : 0.0,
            nonHealthTerminal: nonHealthTerminalByName[canonicalName]
        )
    }
}

func pooledModel(_ rows: [AnalysisRow]) -> OLSResult? {
    let X = rows.map { row in
        [1.0, row.yearCentered, row.mhi, row.yearCentered * row.mhi]
    }
    let y = rows.map(\.salary)
    let clusterIDs = rows.map(\.personID)
    return runClusterRobustOLS(
        X: X,
        y: y,
        clusterIDs: clusterIDs,
        variableNames: ["Intercept", "YearCentered", "MHI", "YearCenteredXMHI"]
    )
}

func fixedEffectsModel(_ rows: [AnalysisRow]) -> OLSResult? {
    let grouped = Dictionary(grouping: rows, by: \.personID)
    var transformedX: [[Double]] = []
    var transformedY: [Double] = []
    var transformedClusterIDs: [String] = []

    for (personID, personRows) in grouped {
        guard personRows.count >= 2 else { continue }

        let meanY = personRows.map(\.salary).reduce(0.0, +) / Double(personRows.count)
        let meanYear = personRows.map(\.yearCentered).reduce(0.0, +) / Double(personRows.count)
        let interactions = personRows.map { $0.yearCentered * $0.mhi }
        let meanInteraction = interactions.reduce(0.0, +) / Double(personRows.count)

        for row in personRows {
            let x1 = row.yearCentered - meanYear
            let x2 = (row.yearCentered * row.mhi) - meanInteraction
            transformedX.append([x1, x2])
            transformedY.append(row.salary - meanY)
            transformedClusterIDs.append(personID)
        }
    }

    return runClusterRobustOLS(
        X: transformedX,
        y: transformedY,
        clusterIDs: transformedClusterIDs,
        variableNames: ["YearCentered", "YearCenteredXMHI"]
    )
}

func rowsWithKnownTerminalDomain(_ rows: [AnalysisRow]) -> [AnalysisRow] {
    rows.filter { $0.nonHealthTerminal != nil }
}

func rowsWithAtLeastTwoObservations(_ rows: [AnalysisRow]) -> [AnalysisRow] {
    let grouped = Dictionary(grouping: rows, by: \.personID)
    return grouped.values.filter { $0.count >= 2 }.flatMap { $0 }
}

func pooledModelWithTerminalDomain(_ rows: [AnalysisRow]) -> OLSResult? {
    guard rows.allSatisfy({ $0.nonHealthTerminal != nil }) else { return nil }
    let X = rows.map { row in
        let nonHealth = row.nonHealthTerminal ?? 0.0
        return [
            1.0,
            row.yearCentered,
            row.mhi,
            nonHealth,
            row.yearCentered * row.mhi,
            row.yearCentered * nonHealth
        ]
    }
    let y = rows.map(\.salary)
    let clusterIDs = rows.map(\.personID)
    return runClusterRobustOLS(
        X: X,
        y: y,
        clusterIDs: clusterIDs,
        variableNames: [
            "Intercept",
            "YearCentered",
            "MHI",
            "NonHealthTerminal",
            "YearCenteredXMHI",
            "YearCenteredXNonHealthTerminal"
        ]
    )
}

func fixedEffectsModelWithTerminalDomain(_ rows: [AnalysisRow]) -> OLSResult? {
    guard rows.allSatisfy({ $0.nonHealthTerminal != nil }) else { return nil }
    let grouped = Dictionary(grouping: rows, by: \.personID)
    var transformedX: [[Double]] = []
    var transformedY: [Double] = []
    var transformedClusterIDs: [String] = []

    for (personID, personRows) in grouped {
        guard personRows.count >= 2 else { continue }
        guard let nonHealth = personRows.first?.nonHealthTerminal else { continue }

        let meanY = personRows.map(\.salary).reduce(0.0, +) / Double(personRows.count)
        let rawX = personRows.map { row in
            [
                row.yearCentered,
                row.yearCentered * row.mhi,
                row.yearCentered * nonHealth
            ]
        }
        let means = (0..<3).map { column in
            rawX.map { $0[column] }.reduce(0.0, +) / Double(rawX.count)
        }

        for (index, row) in personRows.enumerated() {
            let demeaned = (0..<3).map { column in rawX[index][column] - means[column] }
            transformedX.append(demeaned)
            transformedY.append(row.salary - meanY)
            transformedClusterIDs.append(personID)
        }
    }

    return runClusterRobustOLS(
        X: transformedX,
        y: transformedY,
        clusterIDs: transformedClusterIDs,
        variableNames: [
            "YearCentered",
            "YearCenteredXMHI",
            "YearCenteredXNonHealthTerminal"
        ]
    )
}

func linearCombination(result: OLSResult, weights: [Double]) -> (estimate: Double, standardError: Double)? {
    guard weights.count == result.coefficients.count else { return nil }

    var estimate = 0.0
    for i in weights.indices {
        estimate += weights[i] * result.coefficients[i]
    }

    var variance = 0.0
    for i in weights.indices {
        for j in weights.indices {
            variance += weights[i] * weights[j] * result.covariance[i][j]
        }
    }
    return (estimate, sqrt(max(variance, 0.0)))
}

func slopeSummaryRows(modelName: String, result: OLSResult, slopeIndex: Int, interactionIndex: Int) -> [SummaryRow] {
    let nonMHISlope = result.coefficients[slopeIndex]
    let nonMHISE = result.standardErrors[slopeIndex]
    let nonMHICI = confidenceInterval95(estimate: nonMHISlope, standardError: nonMHISE)

    let interaction = result.coefficients[interactionIndex]
    let interactionSE = result.standardErrors[interactionIndex]
    let interactionCI = confidenceInterval95(estimate: interaction, standardError: interactionSE)

    let mhiSlope = nonMHISlope + interaction
    let mhiVar = result.covariance[slopeIndex][slopeIndex]
        + result.covariance[interactionIndex][interactionIndex]
        + 2.0 * result.covariance[slopeIndex][interactionIndex]
    let mhiSE = sqrt(max(mhiVar, 0.0))
    let mhiCI = confidenceInterval95(estimate: mhiSlope, standardError: mhiSE)

    return [
        SummaryRow(
            model: modelName,
            term: "Non-MHI annual slope",
            estimate: nonMHISlope,
            standardError: nonMHISE,
            ciLower: nonMHICI.0,
            ciUpper: nonMHICI.1,
            nObs: result.nObs,
            nClusters: result.nClusters
        ),
        SummaryRow(
            model: modelName,
            term: "MHI annual slope",
            estimate: mhiSlope,
            standardError: mhiSE,
            ciLower: mhiCI.0,
            ciUpper: mhiCI.1,
            nObs: result.nObs,
            nClusters: result.nClusters
        ),
        SummaryRow(
            model: modelName,
            term: "MHI - Non-MHI annual slope",
            estimate: interaction,
            standardError: interactionSE,
            ciLower: interactionCI.0,
            ciUpper: interactionCI.1,
            nObs: result.nObs,
            nClusters: result.nClusters
        )
    ]
}

func levelDifferenceSummaryRows(
    modelName: String,
    result: OLSResult,
    levelIndex: Int
) -> [SummaryRow] {
    guard levelIndex < result.coefficients.count else { return [] }
    let level = result.coefficients[levelIndex]
    let levelSE = result.standardErrors[levelIndex]
    let levelCI = confidenceInterval95(estimate: level, standardError: levelSE)

    return [
        SummaryRow(
            model: modelName,
            term: "MHI - Non-MHI level (centered year)",
            estimate: level,
            standardError: levelSE,
            ciLower: levelCI.0,
            ciUpper: levelCI.1,
            nObs: result.nObs,
            nClusters: result.nClusters
        )
    ]
}

func terminalDomainSlopeSummaryRows(
    modelName: String,
    result: OLSResult,
    yearNonHealthIndex: Int
) -> [SummaryRow] {
    var weights = Array(repeating: 0.0, count: result.coefficients.count)
    guard yearNonHealthIndex < weights.count else { return [] }
    weights[yearNonHealthIndex] = 1.0
    guard let nonHealthGap = linearCombination(result: result, weights: weights) else {
        return []
    }

    let nonHealthCI = confidenceInterval95(estimate: nonHealthGap.estimate, standardError: nonHealthGap.standardError)

    return [
        SummaryRow(
            model: modelName,
            term: "Non-health - Health annual slope",
            estimate: nonHealthGap.estimate,
            standardError: nonHealthGap.standardError,
            ciLower: nonHealthCI.0,
            ciUpper: nonHealthCI.1,
            nObs: result.nObs,
            nClusters: result.nClusters
        )
    ]
}

func csvEscaped(_ field: String) -> String {
    if field.contains(",") || field.contains("\"") || field.contains("\n") {
        return "\"\(field.replacingOccurrences(of: "\"", with: "\"\""))\""
    }
    return field
}

func format(_ value: Double) -> String {
    String(format: "%.3f", value)
}

func binomialCoefficient(_ n: Int, _ k: Int) -> Double {
    guard n >= 0, k >= 0, k <= n else { return 0.0 }
    if k == 0 || k == n { return 1.0 }
    let kEff = min(k, n - k)
    var result = 1.0
    for i in 1...kEff {
        result *= Double(n - kEff + i)
        result /= Double(i)
    }
    return result
}

func forEachCombination(n: Int, k: Int, _ body: ([Int]) -> Void) {
    guard k >= 0, k <= n else { return }
    if k == 0 {
        body([])
        return
    }

    var combo = Array(0..<k)
    while true {
        body(combo)

        var pivot = k - 1
        while pivot >= 0 && combo[pivot] == (n - k + pivot) {
            pivot -= 1
        }
        if pivot < 0 { break }

        combo[pivot] += 1
        if pivot < k - 1 {
            for idx in (pivot + 1)..<k {
                combo[idx] = combo[idx - 1] + 1
            }
        }
    }
}

func randomCombinationIndices(n: Int, k: Int, rng: inout SeededGenerator) -> [Int] {
    guard k > 0 else { return [] }
    var values = Array(0..<n)
    for i in 0..<k {
        let j = Int.random(in: i..<n, using: &rng)
        if i != j {
            values.swapAt(i, j)
        }
    }
    return Array(values.prefix(k)).sorted()
}

func permutedRows(_ rows: [AnalysisRow], assignedMHIByPerson: [String: Double]) -> [AnalysisRow] {
    rows.map { row in
        AnalysisRow(
            personID: row.personID,
            year: row.year,
            yearCentered: row.yearCentered,
            salary: row.salary,
            mhi: assignedMHIByPerson[row.personID] ?? row.mhi,
            nonHealthTerminal: row.nonHealthTerminal
        )
    }
}

func permutationSummaryForSlopeGap(
    rows: [AnalysisRow],
    modelName: String,
    slopeGapTerm: String,
    fitModel: ([AnalysisRow]) -> OLSResult?,
    slopeGapCoefficientIndex: Int,
    randomDraws: Int,
    exactCombinationLimit: Double,
    seed: UInt64
) -> PermutationSummaryRow? {
    guard let observed = fitModel(rows),
          slopeGapCoefficientIndex < observed.coefficients.count else {
        return nil
    }
    let observedGap = observed.coefficients[slopeGapCoefficientIndex]
    let observedSE = observed.standardErrors[slopeGapCoefficientIndex]
    let observedCI = confidenceInterval95(estimate: observedGap, standardError: observedSE)

    let byPerson = Dictionary(grouping: rows, by: \.personID)
    let personIDs = byPerson.keys.sorted()
    let nClusters = personIDs.count
    guard nClusters > 1 else { return nil }

    var observedByPerson: [String: Double] = [:]
    for personID in personIDs {
        guard let first = byPerson[personID]?.first else { continue }
        observedByPerson[personID] = first.mhi
    }

    let nTreated = personIDs.filter { observedByPerson[$0] == 1.0 }.count
    guard nTreated > 0, nTreated < nClusters else { return nil }

    let totalCombinations = binomialCoefficient(nClusters, nTreated)
    let useExact = totalCombinations <= exactCombinationLimit
    let method = useExact ? "exact" : "monte_carlo"

    var nullEstimates: [Double] = []
    nullEstimates.reserveCapacity(useExact ? Int(totalCombinations) : randomDraws)
    var extremeCount = 0

    if useExact {
        forEachCombination(n: nClusters, k: nTreated) { combo in
            var assigned: [String: Double] = [:]
            assigned.reserveCapacity(nClusters)
            let treatedIDs = Set(combo.map { personIDs[$0] })
            for personID in personIDs {
                assigned[personID] = treatedIDs.contains(personID) ? 1.0 : 0.0
            }

            if let result = fitModel(permutedRows(rows, assignedMHIByPerson: assigned)),
               slopeGapCoefficientIndex < result.coefficients.count {
                let gap = result.coefficients[slopeGapCoefficientIndex]
                nullEstimates.append(gap)
                if abs(gap) >= abs(observedGap) - 1e-12 {
                    extremeCount += 1
                }
            }
        }
    } else {
        var rng = SeededGenerator(seed: seed)
        for _ in 0..<randomDraws {
            let treatedIndexSet = Set(randomCombinationIndices(n: nClusters, k: nTreated, rng: &rng))
            var assigned: [String: Double] = [:]
            assigned.reserveCapacity(nClusters)
            for (idx, personID) in personIDs.enumerated() {
                assigned[personID] = treatedIndexSet.contains(idx) ? 1.0 : 0.0
            }

            if let result = fitModel(permutedRows(rows, assignedMHIByPerson: assigned)),
               slopeGapCoefficientIndex < result.coefficients.count {
                let gap = result.coefficients[slopeGapCoefficientIndex]
                nullEstimates.append(gap)
                if abs(gap) >= abs(observedGap) - 1e-12 {
                    extremeCount += 1
                }
            }
        }
    }

    guard !nullEstimates.isEmpty else { return nil }

    let nPerm = nullEstimates.count
    let pTwoSided: Double
    if useExact {
        pTwoSided = Double(extremeCount) / Double(nPerm)
    } else {
        pTwoSided = Double(extremeCount + 1) / Double(nPerm + 1)
    }

    let nullMean = nullEstimates.reduce(0.0, +) / Double(nPerm)
    let nullVar = nullEstimates.reduce(0.0) { partial, value in
        let delta = value - nullMean
        return partial + delta * delta
    } / Double(max(nPerm - 1, 1))
    let nullStdDev = sqrt(max(nullVar, 0.0))

    let sortedNull = nullEstimates.sorted()
    let q025Index = Int(floor(0.025 * Double(nPerm - 1)))
    let q975Index = Int(floor(0.975 * Double(nPerm - 1)))
    let q025 = sortedNull[max(0, min(q025Index, nPerm - 1))]
    let q975 = sortedNull[max(0, min(q975Index, nPerm - 1))]

    return PermutationSummaryRow(
        model: modelName,
        term: slopeGapTerm,
        observedEstimate: observedGap,
        ciLower: observedCI.0,
        ciUpper: observedCI.1,
        nullMean: nullMean,
        nullStdDev: nullStdDev,
        nullQ025: q025,
        nullQ975: q975,
        pTwoSided: pTwoSided,
        nPermutations: nPerm,
        inferenceMethod: method,
        nObs: observed.nObs,
        nClusters: observed.nClusters,
        nTreatedClusters: nTreated
    )
}

func permutationSummaryForSelectedCoefficient(
    rows: [AnalysisRow],
    modelName: String,
    slopeGapTerm: String,
    fitModel: ([AnalysisRow]) -> OLSResult?,
    coefficientIndexResolver: (OLSResult) -> Int?,
    randomDraws: Int,
    exactCombinationLimit: Double,
    seed: UInt64
) -> PermutationSummaryRow? {
    guard let observed = fitModel(rows),
          let coefficientIndex = coefficientIndexResolver(observed) else {
        return nil
    }
    return permutationSummaryForSlopeGap(
        rows: rows,
        modelName: modelName,
        slopeGapTerm: slopeGapTerm,
        fitModel: fitModel,
        slopeGapCoefficientIndex: coefficientIndex,
        randomDraws: randomDraws,
        exactCombinationLimit: exactCombinationLimit,
        seed: seed
    )
}

func writeSummaryOutputs(rows: [SummaryRow], fileStem: String, cohortLabel: String) {
    let fileManager = FileManager.default
    let outputDirectory = URL(fileURLWithPath: fileManager.currentDirectoryPath, isDirectory: true)
        .appendingPathComponent("analysis_output", isDirectory: true)

    do {
        try fileManager.createDirectory(at: outputDirectory, withIntermediateDirectories: true, attributes: nil)

        var csv = "model,term,estimate,std_error,ci_lower,ci_upper,n_obs,n_clusters\n"
        var txt = "Regression summary (cluster-robust SE by person)\n"
        txt += "Cohort definition: \(cohortLabel)\n\n"

        for row in rows {
            csv += [
                row.model,
                row.term,
                format(row.estimate),
                format(row.standardError),
                format(row.ciLower),
                format(row.ciUpper),
                "\(row.nObs)",
                "\(row.nClusters)"
            ].map(csvEscaped).joined(separator: ",") + "\n"

            txt += "\(row.model) | \(row.term): "
            txt += "estimate=\(format(row.estimate)), "
            txt += "SE=\(format(row.standardError)), "
            txt += "95% CI [\(format(row.ciLower)), \(format(row.ciUpper))], "
            txt += "N=\(row.nObs), clusters=\(row.nClusters)\n"
        }

        let csvURL = outputDirectory.appendingPathComponent("\(fileStem).csv")
        let txtURL = outputDirectory.appendingPathComponent("\(fileStem).txt")
        try csv.write(to: csvURL, atomically: true, encoding: .utf8)
        try txt.write(to: txtURL, atomically: true, encoding: .utf8)

        print("Wrote regression CSV summary: \(csvURL.path)")
        print("Wrote regression text summary: \(txtURL.path)")
    } catch {
        print("Failed to write regression summary outputs: \(error)")
    }
}

func writePermutationOutputs(rows: [PermutationSummaryRow], fileStem: String, cohortLabel: String) {
    let fileManager = FileManager.default
    let outputDirectory = URL(fileURLWithPath: fileManager.currentDirectoryPath, isDirectory: true)
        .appendingPathComponent("analysis_output", isDirectory: true)

    do {
        try fileManager.createDirectory(at: outputDirectory, withIntermediateDirectories: true, attributes: nil)

        var csv = "model,term,observed_estimate,ci_lower,ci_upper,null_mean,null_std_dev,null_q025,null_q975,p_two_sided,n_permutations,inference_method,n_obs,n_clusters,n_treated_clusters\n"
        var txt = "Permutation/randomization inference summary\n"
        txt += "Cohort definition: \(cohortLabel)\n\n"

        for row in rows {
            let methodLabel = row.inferenceMethod.replacingOccurrences(of: "_", with: "-")
            csv += [
                row.model,
                row.term,
                format(row.observedEstimate),
                format(row.ciLower),
                format(row.ciUpper),
                format(row.nullMean),
                format(row.nullStdDev),
                format(row.nullQ025),
                format(row.nullQ975),
                format(row.pTwoSided),
                "\(row.nPermutations)",
                methodLabel,
                "\(row.nObs)",
                "\(row.nClusters)",
                "\(row.nTreatedClusters)"
            ].map(csvEscaped).joined(separator: ",") + "\n"

            txt += "\(row.model) | \(row.term): "
            txt += "observed=\(format(row.observedEstimate)), "
            txt += "95% CI [\(format(row.ciLower)), \(format(row.ciUpper))], "
            txt += "null mean=\(format(row.nullMean)), null SD=\(format(row.nullStdDev)), "
            txt += "null 2.5%-97.5% [\(format(row.nullQ025)), \(format(row.nullQ975))], "
            txt += "p(two-sided)=\(format(row.pTwoSided)), "
            txt += "permutations=\(row.nPermutations), method=\(methodLabel), "
            txt += "N=\(row.nObs), clusters=\(row.nClusters), treated clusters=\(row.nTreatedClusters)\n"
        }

        let csvURL = outputDirectory.appendingPathComponent("\(fileStem).csv")
        let txtURL = outputDirectory.appendingPathComponent("\(fileStem).txt")
        try csv.write(to: csvURL, atomically: true, encoding: .utf8)
        try txt.write(to: txtURL, atomically: true, encoding: .utf8)

        print("Wrote permutation CSV summary: \(csvURL.path)")
        print("Wrote permutation text summary: \(txtURL.path)")
    } catch {
        print("Failed to write permutation summary outputs: \(error)")
    }
}

func regressionAnalysisMHI(records: [SalaryRecord]) {
    guard !records.isEmpty else {
        print("No records available for regression.")
        return
    }

    let config = regressionAnalysisConfig
    let nonHealthTerminalByName = loadTerminalDegreeDomainLookup()

    for cohort in analysisCohorts {
        let rows = modelRowsFromRecords(
            records,
            cohort: cohort,
            nonHealthTerminalByName: nonHealthTerminalByName
        )
        let treatedCount = rows.filter { $0.mhi == 1.0 }.count
        let untreatedCount = rows.count - treatedCount
        guard treatedCount > 1, untreatedCount > 1 else {
            print("Skipping cohort '\(cohort.label)' because one group has too few observations.")
            continue
        }

        guard let pooled = pooledModel(rows) else {
            print("Pooled model failed for cohort: \(cohort.label)")
            continue
        }
        guard let fixedEffects = fixedEffectsModel(rows) else {
            print("Fixed-effects model failed for cohort: \(cohort.label)")
            continue
        }

        let pooledLevelSummary = levelDifferenceSummaryRows(
            modelName: "Pooled OLS",
            result: pooled,
            levelIndex: 2
        )
        let pooledSummary = slopeSummaryRows(
            modelName: "Pooled OLS",
            result: pooled,
            slopeIndex: 1,
            interactionIndex: 3
        )
        let fixedEffectsSummary = slopeSummaryRows(
            modelName: "Person FE",
            result: fixedEffects,
            slopeIndex: 0,
            interactionIndex: 1
        )

        var allRows = pooledLevelSummary + pooledSummary

        if !nonHealthTerminalByName.isEmpty {
            let knownRows = rowsWithKnownTerminalDomain(rows)
            let knownMHI = knownRows.filter { $0.mhi == 1.0 }.count
            let knownNonMHI = knownRows.count - knownMHI
            let knownNonHealth = knownRows.filter { $0.nonHealthTerminal == 1.0 }.count
            let knownHealth = knownRows.count - knownNonHealth

            if knownMHI > 1, knownNonMHI > 1, knownNonHealth > 1, knownHealth > 1,
               let pooledTerminal = pooledModelWithTerminalDomain(knownRows) {
                let pooledTerminalSummary = terminalDomainSlopeSummaryRows(
                    modelName: "Pooled OLS (Terminal Degree Domain)",
                    result: pooledTerminal,
                    yearNonHealthIndex: 5
                )
                allRows += pooledTerminalSummary
            } else {
                print("Skipping pooled terminal-degree domain model for cohort '\(cohort.label)' due to insufficient variation or singular design matrix.")
            }
        }

        allRows += fixedEffectsSummary

        if !nonHealthTerminalByName.isEmpty {
            let knownRows = rowsWithKnownTerminalDomain(rows)
            let knownMHI = knownRows.filter { $0.mhi == 1.0 }.count
            let knownNonMHI = knownRows.count - knownMHI
            let knownNonHealth = knownRows.filter { $0.nonHealthTerminal == 1.0 }.count
            let knownHealth = knownRows.count - knownNonHealth

            if knownMHI > 1, knownNonMHI > 1, knownNonHealth > 1, knownHealth > 1,
               let fixedEffectsTerminal = fixedEffectsModelWithTerminalDomain(knownRows) {
                let fixedEffectsTerminalSummary = terminalDomainSlopeSummaryRows(
                    modelName: "Person FE (Terminal Degree Domain)",
                    result: fixedEffectsTerminal,
                    yearNonHealthIndex: 2
                )
                allRows += fixedEffectsTerminalSummary
            } else {
                print("Skipping FE terminal-degree domain model for cohort '\(cohort.label)' due to insufficient variation or singular design matrix.")
            }
        }

        let fileStem = cohort.key == primaryMHICohort.key
            ? "regression_summary"
            : "regression_summary_\(cohort.key)"
        writeSummaryOutputs(rows: allRows, fileStem: fileStem, cohortLabel: cohort.label)

        let permutationFileStem = cohort.key == primaryMHICohort.key
            ? "permutation_inference_summary"
            : "permutation_inference_summary_\(cohort.key)"
        var permutationRows: [PermutationSummaryRow] = []
        if config.runPermutationInference {
            if let pooledLevelPermutation = permutationSummaryForSlopeGap(
                rows: rows,
                modelName: "Pooled OLS",
                slopeGapTerm: "MHI - Non-MHI level (centered year)",
                fitModel: pooledModel,
                slopeGapCoefficientIndex: 2,
                randomDraws: config.permutationDraws,
                exactCombinationLimit: config.permutationExactCombinationLimit,
                seed: config.permutationSeedBase
            ) {
                permutationRows.append(pooledLevelPermutation)
            }

            if let pooledPermutation = permutationSummaryForSlopeGap(
                rows: rows,
                modelName: "Pooled OLS",
                slopeGapTerm: "MHI - Non-MHI annual slope",
                fitModel: pooledModel,
                slopeGapCoefficientIndex: 3,
                randomDraws: config.permutationDraws,
                exactCombinationLimit: config.permutationExactCombinationLimit,
                seed: config.permutationSeedBase + 1
            ) {
                permutationRows.append(pooledPermutation)
            }

            let feRows = rowsWithAtLeastTwoObservations(rows)
            if let fixedEffectsPermutation = permutationSummaryForSlopeGap(
                rows: feRows,
                modelName: "Person FE",
                slopeGapTerm: "MHI - Non-MHI annual slope",
                fitModel: fixedEffectsModel,
                slopeGapCoefficientIndex: 1,
                randomDraws: config.permutationDraws,
                exactCombinationLimit: config.permutationExactCombinationLimit,
                seed: config.permutationSeedBase + 2
            ) {
                permutationRows.append(fixedEffectsPermutation)
            }
        } else {
            print("Skipping permutation inference for cohort: \(cohort.label)")
        }
        writePermutationOutputs(rows: permutationRows, fileStem: permutationFileStem, cohortLabel: cohort.label)

        runSegmentedGrowthAnalysis(
            rows: rows,
            cohort: cohort,
            config: regressionAnalysisConfig
        )
        runEntryCohortAnalysis(
            rows: rows,
            cohort: cohort,
            config: regressionAnalysisConfig
        )

        print("Regression Summary for \(cohort.label):")
        for row in allRows {
            print("\(row.model) | \(row.term) = \(format(row.estimate)) (SE \(format(row.standardError)))")
        }
    }
}
