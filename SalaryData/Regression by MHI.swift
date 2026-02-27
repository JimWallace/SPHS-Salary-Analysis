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

struct AnalysisRow {
    let personID: String
    let yearCentered: Double
    let salary: Double
    let mhi: Double
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

func modelRowsFromRecords(_ records: [SalaryRecord]) -> [AnalysisRow] {
    guard let minYear = records.map(\.year).min() else { return [] }
    let baseYear = Double(minYear)
    return records.map { record in
        AnalysisRow(
            personID: "\(record.surname), \(record.givenName)",
            yearCentered: Double(record.year) - baseYear,
            salary: record.salary,
            mhi: record.mhi ? 1.0 : 0.0
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

func csvEscaped(_ field: String) -> String {
    if field.contains(",") || field.contains("\"") || field.contains("\n") {
        return "\"\(field.replacingOccurrences(of: "\"", with: "\"\""))\""
    }
    return field
}

func format(_ value: Double) -> String {
    String(format: "%.3f", value)
}

func writeSummaryOutputs(rows: [SummaryRow]) {
    let fileManager = FileManager.default
    let outputDirectory = URL(fileURLWithPath: fileManager.currentDirectoryPath, isDirectory: true)
        .appendingPathComponent("analysis_output", isDirectory: true)

    do {
        try fileManager.createDirectory(at: outputDirectory, withIntermediateDirectories: true, attributes: nil)

        var csv = "model,term,estimate,std_error,ci_lower,ci_upper,n_obs,n_clusters\n"
        var txt = "Regression summary (cluster-robust SE by person)\n\n"

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

        let csvURL = outputDirectory.appendingPathComponent("regression_summary.csv")
        let txtURL = outputDirectory.appendingPathComponent("regression_summary.txt")
        try csv.write(to: csvURL, atomically: true, encoding: .utf8)
        try txt.write(to: txtURL, atomically: true, encoding: .utf8)

        print("Wrote regression CSV summary: \(csvURL.path)")
        print("Wrote regression text summary: \(txtURL.path)")
    } catch {
        print("Failed to write regression summary outputs: \(error)")
    }
}

func regressionAnalysisMHI(records: [SalaryRecord]) {
    let rows = modelRowsFromRecords(records)
    guard !rows.isEmpty else {
        print("No records available for regression.")
        return
    }

    guard let pooled = pooledModel(rows) else {
        print("Pooled model failed.")
        return
    }
    guard let fixedEffects = fixedEffectsModel(rows) else {
        print("Fixed-effects model failed.")
        return
    }

    let pooledSummary = slopeSummaryRows(
        modelName: "Pooled OLS (cluster-robust)",
        result: pooled,
        slopeIndex: 1,
        interactionIndex: 3
    )
    let fixedEffectsSummary = slopeSummaryRows(
        modelName: "Person FE (cluster-robust)",
        result: fixedEffects,
        slopeIndex: 0,
        interactionIndex: 1
    )

    let allRows = pooledSummary + fixedEffectsSummary
    writeSummaryOutputs(rows: allRows)

    print("Regression Summary:")
    for row in allRows {
        print("\(row.model) | \(row.term) = \(format(row.estimate)) (SE \(format(row.standardError)))")
    }
}
