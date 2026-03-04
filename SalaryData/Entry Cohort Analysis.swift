import Foundation

struct EntryCohortSummaryRow {
    let analysis: String
    let cohortBucket: String
    let estimate: Double
    let standardError: Double
    let ciLow: Double
    let ciHigh: Double
    let nObs: Int
    let nClusters: Int
    let nTreatedClusters: Int
}

struct EntryCohortPermutationRow {
    let analysis: String
    let cohortBucket: String
    let model: String
    let term: String
    let observedEstimate: Double
    let nullMean: Double
    let nullStdDev: Double
    let nullQ025: Double
    let nullQ975: Double
    let pTwoSided: Double
    let nPermutations: Int
    let inferenceMethod: String
}

struct MatchedPairRow {
    let mhiPersonID: String
    let mhiFirstYear: Int
    let nonMHIPersonID: String
    let nonMHIFirstYear: Int
    let yearGap: Int
}

private let entryCohortBuckets: [(label: String, start: Int, end: Int)] = [
    ("2011-2013", 2011, 2013),
    ("2014-2016", 2014, 2016),
    ("2017-2019", 2017, 2019),
    ("2020-2022", 2020, 2022)
]

// Disclosure data begin in 2011 in this project. A first observed disclosure
// at that boundary is left-censored and should not be treated as a true entry
// year unless a CV/manual override provides an earlier/later start.
private let disclosureLeftCensorYear = 2011

private func firstDisclosureYearByPerson(_ rows: [AnalysisRow]) -> [String: Int] {
    var map: [String: Int] = [:]
    for row in rows {
        if let existing = map[row.personID] {
            map[row.personID] = min(existing, row.year)
        } else {
            map[row.personID] = row.year
        }
    }
    return map
}

private func loadCVStartYearByCanonicalName(
    allowedConfidences: Set<String> = ["high", "medium"]
) -> [String: Int] {
    let fileManager = FileManager.default
    let csvURL = URL(fileURLWithPath: fileManager.currentDirectoryPath, isDirectory: true)
        .appendingPathComponent("analysis_output/cv_start_year_crosswalk.csv")
    guard fileManager.fileExists(atPath: csvURL.path) else {
        print("CV start-year crosswalk not found at \(csvURL.path). Skipping CV start-year sensitivity.")
        return [:]
    }

    do {
        let contents = try String(contentsOf: csvURL, encoding: .utf8)
        let lines = contents.split(whereSeparator: \.isNewline).map(String.init)
        guard let headerLine = lines.first else { return [:] }
        let headers = parseCSVLine(headerLine)
        guard let nameIndex = headers.firstIndex(of: "salary_name"),
              let yearIndex = headers.firstIndex(of: "cv_start_year"),
              let confidenceIndex = headers.firstIndex(of: "cv_start_confidence") else {
            print("CV start-year crosswalk missing expected columns. Skipping CV start-year sensitivity.")
            return [:]
        }

        var map: [String: Int] = [:]
        for line in lines.dropFirst() {
            let fields = parseCSVLine(line)
            guard nameIndex < fields.count, yearIndex < fields.count, confidenceIndex < fields.count else { continue }
            let confidence = fields[confidenceIndex].trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard allowedConfidences.contains(confidence) else { continue }
            guard let year = Int(fields[yearIndex].trimmingCharacters(in: .whitespacesAndNewlines)) else { continue }
            let canonicalName = canonicalFacultyName(fields[nameIndex])
            guard !canonicalName.isEmpty else { continue }
            map[canonicalName] = year
        }
        print("Loaded CV start years (confidence \(allowedConfidences.sorted().joined(separator: "/"))): \(map.count) faculty.")
        return map
    } catch {
        print("Failed reading CV start-year crosswalk: \(error). Skipping CV start-year sensitivity.")
        return [:]
    }
}

private func firstYearMapUsingCVOverrides(
    rows: [AnalysisRow],
    baseFirstYearMap: [String: Int],
    cvStartYearByCanonicalName: [String: Int]
) -> [String: Int] {
    var canonicalToPersonIDs: [String: Set<String>] = [:]
    for row in rows {
        let canonical = canonicalFacultyName(row.personID)
        canonicalToPersonIDs[canonical, default: []].insert(row.personID)
    }

    var merged = baseFirstYearMap
    var overrideCount = 0
    for (canonical, cvYear) in cvStartYearByCanonicalName {
        guard let personIDs = canonicalToPersonIDs[canonical] else { continue }
        for personID in personIDs {
            if merged[personID] != cvYear {
                merged[personID] = cvYear
                overrideCount += 1
            }
        }
    }
    print("Applied CV first-year overrides to \(overrideCount) person IDs (base: \(baseFirstYearMap.count), merged: \(merged.count)).")
    return merged
}

private func applyLeftCensorRule(
    firstYearMap: [String: Int],
    keepPersonIDs: Set<String>,
    censorYear: Int
) -> [String: Int] {
    var filtered: [String: Int] = [:]
    var dropped = 0
    for (personID, year) in firstYearMap {
        if year == censorYear && !keepPersonIDs.contains(personID) {
            dropped += 1
            continue
        }
        filtered[personID] = year
    }
    print("Applied left-censor rule at \(censorYear): dropped \(dropped) person IDs without override evidence.")
    return filtered
}

private func cohortBucketLabel(for firstYear: Int) -> String? {
    for bucket in entryCohortBuckets where firstYear >= bucket.start && firstYear <= bucket.end {
        return bucket.label
    }
    return nil
}

private func yearsSinceFirst(_ row: AnalysisRow, firstYearByPerson: [String: Int]) -> Double? {
    guard let firstYear = firstYearByPerson[row.personID] else { return nil }
    return Double(row.year - firstYear)
}

private func pooledYearsSinceModelWithCohortFE(
    rows: [AnalysisRow],
    firstYearByPerson: [String: Int]
) -> OLSResult? {
    let cohortByPerson = firstYearByPerson.compactMapValues(cohortBucketLabel)
    let cohortLevels = Array(Set(cohortByPerson.values)).sorted()
    guard cohortLevels.count >= 2 else { return nil }
    let baseline = cohortLevels[0]

    var X: [[Double]] = []
    var y: [Double] = []
    var clusterIDs: [String] = []

    for row in rows {
        guard cohortByPerson[row.personID] != nil,
              let ys = yearsSinceFirst(row, firstYearByPerson: firstYearByPerson) else {
            continue
        }
        let m = row.mhi
        var predictors: [Double] = [1.0, ys, m, ys * m]
        for level in cohortLevels where level != baseline {
            predictors.append(cohortByPerson[row.personID] == level ? 1.0 : 0.0)
        }
        X.append(predictors)
        y.append(row.salary)
        clusterIDs.append(row.personID)
    }

    let treatedClusters = Set(clusterIDs.filter { id in
        rows.first(where: { $0.personID == id })?.mhi == 1.0
    }).count
    guard treatedClusters > 1 else { return nil }

    var variableNames = ["Intercept", "YearsSinceFirst", "MHI", "YearsSinceFirstXMHI"]
    variableNames += cohortLevels.filter { $0 != baseline }.map { "CohortFE_\($0)" }

    return runClusterRobustOLS(X: X, y: y, clusterIDs: clusterIDs, variableNames: variableNames)
}

private func fixedEffectsYearsSinceModel(
    rows: [AnalysisRow],
    firstYearByPerson: [String: Int]
) -> OLSResult? {
    let grouped = Dictionary(grouping: rows, by: \.personID)
    var transformedX: [[Double]] = []
    var transformedY: [Double] = []
    var transformedClusterIDs: [String] = []

    for (personID, personRows) in grouped {
        guard personRows.count >= 2 else { continue }
        guard let firstYear = firstYearByPerson[personID] else { continue }

        let meanY = personRows.map(\.salary).reduce(0.0, +) / Double(personRows.count)
        let rawX = personRows.map { row -> [Double] in
            let ys = Double(row.year - firstYear)
            return [ys, ys * row.mhi]
        }
        let means = (0..<2).map { col in
            rawX.map { $0[col] }.reduce(0.0, +) / Double(rawX.count)
        }

        for (index, row) in personRows.enumerated() {
            let demeaned = (0..<2).map { col in rawX[index][col] - means[col] }
            transformedX.append(demeaned)
            transformedY.append(row.salary - meanY)
            transformedClusterIDs.append(personID)
        }
    }

    return runClusterRobustOLS(
        X: transformedX,
        y: transformedY,
        clusterIDs: transformedClusterIDs,
        variableNames: ["YearsSinceFirst", "YearsSinceFirstXMHI"]
    )
}

private func summaryRowFromResult(
    analysis: String,
    cohortBucket: String,
    result: OLSResult,
    interactionTerm: String,
    treatedClusterCount: Int
) -> EntryCohortSummaryRow? {
    guard let idx = result.variableNames.firstIndex(of: interactionTerm) else { return nil }
    let estimate = result.coefficients[idx]
    let se = result.standardErrors[idx]
    let ci = confidenceInterval95(estimate: estimate, standardError: se)
    return EntryCohortSummaryRow(
        analysis: analysis,
        cohortBucket: cohortBucket,
        estimate: estimate,
        standardError: se,
        ciLow: ci.0,
        ciHigh: ci.1,
        nObs: result.nObs,
        nClusters: result.nClusters,
        nTreatedClusters: treatedClusterCount
    )
}

private func writeEntryCohortSummary(
    rows: [EntryCohortSummaryRow],
    fileStem: String
) {
    let fileManager = FileManager.default
    let outputDirectory = URL(fileURLWithPath: fileManager.currentDirectoryPath, isDirectory: true)
        .appendingPathComponent("analysis_output", isDirectory: true)
    do {
        try fileManager.createDirectory(at: outputDirectory, withIntermediateDirectories: true, attributes: nil)
        var csv = "analysis,cohort_bucket,estimate,std_error,ci_low,ci_high,n_obs,n_clusters,n_treated_clusters\n"
        for row in rows {
            csv += [
                csvEscaped(row.analysis),
                csvEscaped(row.cohortBucket),
                format(row.estimate),
                format(row.standardError),
                format(row.ciLow),
                format(row.ciHigh),
                "\(row.nObs)",
                "\(row.nClusters)",
                "\(row.nTreatedClusters)"
            ].joined(separator: ",") + "\n"
        }
        try csv.write(to: outputDirectory.appendingPathComponent("\(fileStem).csv"), atomically: true, encoding: .utf8)
        print("Wrote entry-cohort summary CSV: \(outputDirectory.appendingPathComponent("\(fileStem).csv").path)")
    } catch {
        print("Failed to write entry-cohort summary CSV: \(error)")
    }
}

private func writeEntryCohortPermutation(
    rows: [EntryCohortPermutationRow],
    fileStem: String
) {
    let fileManager = FileManager.default
    let outputDirectory = URL(fileURLWithPath: fileManager.currentDirectoryPath, isDirectory: true)
        .appendingPathComponent("analysis_output", isDirectory: true)
    do {
        try fileManager.createDirectory(at: outputDirectory, withIntermediateDirectories: true, attributes: nil)
        var csv = "analysis,cohort_bucket,model,term,observed_estimate,null_mean,null_std_dev,null_q025,null_q975,p_two_sided,n_permutations,inference_method\n"
        for row in rows {
            csv += [
                csvEscaped(row.analysis),
                csvEscaped(row.cohortBucket),
                csvEscaped(row.model),
                csvEscaped(row.term),
                format(row.observedEstimate),
                format(row.nullMean),
                format(row.nullStdDev),
                format(row.nullQ025),
                format(row.nullQ975),
                format(row.pTwoSided),
                "\(row.nPermutations)",
                csvEscaped(row.inferenceMethod.replacingOccurrences(of: "_", with: "-"))
            ].joined(separator: ",") + "\n"
        }
        try csv.write(to: outputDirectory.appendingPathComponent("\(fileStem).csv"), atomically: true, encoding: .utf8)
        print("Wrote entry-cohort permutation CSV: \(outputDirectory.appendingPathComponent("\(fileStem).csv").path)")
    } catch {
        print("Failed to write entry-cohort permutation CSV: \(error)")
    }
}

private func writeMatchedPairs(
    rows: [MatchedPairRow],
    fileStem: String
) {
    let fileManager = FileManager.default
    let outputDirectory = URL(fileURLWithPath: fileManager.currentDirectoryPath, isDirectory: true)
        .appendingPathComponent("analysis_output", isDirectory: true)
    do {
        try fileManager.createDirectory(at: outputDirectory, withIntermediateDirectories: true, attributes: nil)
        var csv = "mhi_person,mhi_first_year,non_mhi_person,non_mhi_first_year,year_gap\n"
        for row in rows {
            csv += [
                csvEscaped(row.mhiPersonID),
                "\(row.mhiFirstYear)",
                csvEscaped(row.nonMHIPersonID),
                "\(row.nonMHIFirstYear)",
                "\(row.yearGap)"
            ].joined(separator: ",") + "\n"
        }
        try csv.write(to: outputDirectory.appendingPathComponent("\(fileStem).csv"), atomically: true, encoding: .utf8)
        print("Wrote matched pairs CSV: \(outputDirectory.appendingPathComponent("\(fileStem).csv").path)")
    } catch {
        print("Failed to write matched pairs CSV: \(error)")
    }
}

private func buildMatchedPairs(
    rows: [AnalysisRow],
    firstYearByPerson: [String: Int],
    yearWindow: Int
) -> [MatchedPairRow] {
    let personToMHI = Dictionary(grouping: rows, by: \.personID).compactMapValues { $0.first?.mhi }
    let mhiPeople = firstYearByPerson.keys.filter { personToMHI[$0] == 1.0 }.sorted()
    let nonPeople = firstYearByPerson.keys.filter { personToMHI[$0] == 0.0 }.sorted()

    var availableNon = Set(nonPeople)
    var pairs: [MatchedPairRow] = []

    for mhiPerson in mhiPeople {
        guard let mhiYear = firstYearByPerson[mhiPerson] else { continue }
        let candidates = availableNon.compactMap { non -> (String, Int, Int)? in
            guard let nonYear = firstYearByPerson[non] else { return nil }
            let gap = abs(nonYear - mhiYear)
            guard gap <= yearWindow else { return nil }
            return (non, nonYear, gap)
        }
        .sorted { lhs, rhs in
            if lhs.2 != rhs.2 { return lhs.2 < rhs.2 }
            if lhs.1 != rhs.1 { return lhs.1 < rhs.1 }
            return lhs.0 < rhs.0
        }

        guard let best = candidates.first else { continue }
        availableNon.remove(best.0)
        pairs.append(
            MatchedPairRow(
                mhiPersonID: mhiPerson,
                mhiFirstYear: mhiYear,
                nonMHIPersonID: best.0,
                nonMHIFirstYear: best.1,
                yearGap: best.2
            )
        )
    }

    return pairs
}

private func simpleSlope(_ x: [Double], _ y: [Double]) -> Double? {
    guard x.count == y.count, x.count >= 2 else { return nil }
    let xMean = x.reduce(0.0, +) / Double(x.count)
    let yMean = y.reduce(0.0, +) / Double(y.count)
    var numer = 0.0
    var denom = 0.0
    for i in x.indices {
        let dx = x[i] - xMean
        numer += dx * (y[i] - yMean)
        denom += dx * dx
    }
    guard denom > 0 else { return nil }
    return numer / denom
}

private func matchedAverageSlopeGap(
    rows: [AnalysisRow],
    matchedPeople: Set<String>,
    firstYearByPerson: [String: Int],
    horizonYears: Int
) -> EntryCohortSummaryRow? {
    let grouped = Dictionary(grouping: rows.filter { matchedPeople.contains($0.personID) }, by: \.personID)
    var mhiSlopes: [Double] = []
    var nonSlopes: [Double] = []

    for (personID, personRows) in grouped {
        guard let firstYear = firstYearByPerson[personID] else { continue }
        let inHorizon = personRows.filter { $0.year - firstYear <= horizonYears }.sorted { $0.year < $1.year }
        let x = inHorizon.map { Double($0.year - firstYear) }
        let y = inHorizon.map(\.salary)
        guard let slope = simpleSlope(x, y) else { continue }
        if inHorizon.first?.mhi == 1.0 {
            mhiSlopes.append(slope)
        } else {
            nonSlopes.append(slope)
        }
    }

    guard !mhiSlopes.isEmpty, !nonSlopes.isEmpty else { return nil }

    let meanMHI = mhiSlopes.reduce(0.0, +) / Double(mhiSlopes.count)
    let meanNon = nonSlopes.reduce(0.0, +) / Double(nonSlopes.count)
    let gap = meanMHI - meanNon

    func sampleVariance(_ values: [Double]) -> Double {
        guard values.count >= 2 else { return 0.0 }
        let mean = values.reduce(0.0, +) / Double(values.count)
        return values.reduce(0.0) { partial, value in
            let d = value - mean
            return partial + d * d
        } / Double(values.count - 1)
    }

    let se = sqrt(sampleVariance(mhiSlopes) / Double(mhiSlopes.count) + sampleVariance(nonSlopes) / Double(nonSlopes.count))
    let ci = confidenceInterval95(estimate: gap, standardError: se)

    return EntryCohortSummaryRow(
        analysis: "Matched average slope gap (first \(horizonYears) years)",
        cohortBucket: "Matched ±1 year",
        estimate: gap,
        standardError: se,
        ciLow: ci.0,
        ciHigh: ci.1,
        nObs: mhiSlopes.count + nonSlopes.count,
        nClusters: mhiSlopes.count + nonSlopes.count,
        nTreatedClusters: mhiSlopes.count
    )
}

func runEntryCohortAnalysis(
    rows: [AnalysisRow],
    cohort: CohortDefinition,
    config: RegressionAnalysisConfig
) {
    if !config.runPermutationInference {
        print("Skipping entry-cohort permutation inference for cohort: \(cohort.label)")
    }
    func runWithFirstYearMap(_ firstYearMap: [String: Int], outputSuffix: String?) {
        var summaryRows: [EntryCohortSummaryRow] = []
        var permutationRows: [EntryCohortPermutationRow] = []

        // 1) Full-sample years-since model with entry-cohort FE.
        if let pooledWithCohort = pooledYearsSinceModelWithCohortFE(rows: rows, firstYearByPerson: firstYearMap),
           let treatedClusters = Set(rows.filter { $0.mhi == 1.0 }.map(\.personID)).count as Int? {
            if let summary = summaryRowFromResult(
                analysis: "Pooled with entry-cohort FE",
                cohortBucket: "All cohorts",
                result: pooledWithCohort,
                interactionTerm: "YearsSinceFirstXMHI",
                treatedClusterCount: treatedClusters
            ) {
                summaryRows.append(summary)
            }

            if config.runPermutationInference, let perm = permutationSummaryForSelectedCoefficient(
                rows: rows,
                modelName: "Pooled with entry-cohort FE",
                slopeGapTerm: "YearsSinceFirstXMHI",
                fitModel: { pooledYearsSinceModelWithCohortFE(rows: $0, firstYearByPerson: firstYearMap) },
                coefficientIndexResolver: { result in
                    result.variableNames.firstIndex(of: "YearsSinceFirstXMHI")
                },
                randomDraws: config.permutationDraws,
                exactCombinationLimit: config.permutationExactCombinationLimit,
                seed: config.permutationSeedBase + 501
            ) {
                permutationRows.append(
                    EntryCohortPermutationRow(
                        analysis: "Pooled with entry-cohort FE",
                        cohortBucket: "All cohorts",
                        model: perm.model,
                        term: perm.term,
                        observedEstimate: perm.observedEstimate,
                        nullMean: perm.nullMean,
                        nullStdDev: perm.nullStdDev,
                        nullQ025: perm.nullQ025,
                        nullQ975: perm.nullQ975,
                        pTwoSided: perm.pTwoSided,
                        nPermutations: perm.nPermutations,
                        inferenceMethod: perm.inferenceMethod
                    )
                )
            }
        }

        // 2) Within-entry-cohort FE growth differences.
        let personToBucket = firstYearMap.compactMapValues(cohortBucketLabel)
        for bucket in entryCohortBuckets.map(\.label) {
            let personIDs = Set(personToBucket.filter { $0.value == bucket }.map(\.key))
            let subset = rows.filter { personIDs.contains($0.personID) }
            let feSubset = rowsWithAtLeastTwoObservations(subset)
            let treatedClusters = Set(feSubset.filter { $0.mhi == 1.0 }.map(\.personID)).count
            let controlClusters = Set(feSubset.filter { $0.mhi == 0.0 }.map(\.personID)).count
            guard treatedClusters > 1, controlClusters > 1 else { continue }

            let fePersonIDs = Set(feSubset.map(\.personID))
            let firstSubsetMap = Dictionary(uniqueKeysWithValues: fePersonIDs.compactMap { id in
                firstYearMap[id].map { (id, $0) }
            })
            guard let feResult = fixedEffectsYearsSinceModel(rows: feSubset, firstYearByPerson: firstSubsetMap) else { continue }
            if let summary = summaryRowFromResult(
                analysis: "Within-cohort FE",
                cohortBucket: bucket,
                result: feResult,
                interactionTerm: "YearsSinceFirstXMHI",
                treatedClusterCount: treatedClusters
            ) {
                summaryRows.append(summary)
            }

            if config.runPermutationInference, let perm = permutationSummaryForSelectedCoefficient(
                rows: feSubset,
                modelName: "Within-cohort FE",
                slopeGapTerm: "YearsSinceFirstXMHI",
                fitModel: { fixedEffectsYearsSinceModel(rows: $0, firstYearByPerson: firstSubsetMap) },
                coefficientIndexResolver: { result in result.variableNames.firstIndex(of: "YearsSinceFirstXMHI") },
                randomDraws: config.permutationDraws,
                exactCombinationLimit: config.permutationExactCombinationLimit,
                seed: config.permutationSeedBase + UInt64(600 + (entryCohortBuckets.firstIndex { $0.label == bucket } ?? 0))
            ) {
                permutationRows.append(
                    EntryCohortPermutationRow(
                        analysis: "Within-cohort FE",
                        cohortBucket: bucket,
                        model: perm.model,
                        term: perm.term,
                        observedEstimate: perm.observedEstimate,
                        nullMean: perm.nullMean,
                        nullStdDev: perm.nullStdDev,
                        nullQ025: perm.nullQ025,
                        nullQ975: perm.nullQ975,
                        pTwoSided: perm.pTwoSided,
                        nPermutations: perm.nPermutations,
                        inferenceMethod: perm.inferenceMethod
                    )
                )
            }
        }

        // 3) Matched comparison within ±1 year first disclosure/CV.
        let pairs = buildMatchedPairs(rows: rows, firstYearByPerson: firstYearMap, yearWindow: config.matchingYearWindow)
        let matchedPeople = Set(pairs.flatMap { [$0.mhiPersonID, $0.nonMHIPersonID] })
        if !matchedPeople.isEmpty {
            let matchedRows = rows.filter { matchedPeople.contains($0.personID) }
            let matchedFirstMap = Dictionary(uniqueKeysWithValues: matchedPeople.compactMap { id in
                firstYearMap[id].map { (id, $0) }
            })
            let matchedFERows = rowsWithAtLeastTwoObservations(matchedRows)

            if let feMatched = fixedEffectsYearsSinceModel(rows: matchedFERows, firstYearByPerson: matchedFirstMap),
               let treatedClusters = Set(matchedFERows.filter { $0.mhi == 1.0 }.map(\.personID)).count as Int?,
               let summary = summaryRowFromResult(
                    analysis: "Matched FE (±\(config.matchingYearWindow) year)",
                    cohortBucket: "Matched set",
                    result: feMatched,
                    interactionTerm: "YearsSinceFirstXMHI",
                    treatedClusterCount: treatedClusters
               ) {
                summaryRows.append(summary)

                if config.runPermutationInference, let perm = permutationSummaryForSelectedCoefficient(
                    rows: matchedFERows,
                    modelName: "Matched FE",
                    slopeGapTerm: "YearsSinceFirstXMHI",
                    fitModel: { fixedEffectsYearsSinceModel(rows: $0, firstYearByPerson: matchedFirstMap) },
                    coefficientIndexResolver: { result in result.variableNames.firstIndex(of: "YearsSinceFirstXMHI") },
                    randomDraws: config.permutationDraws,
                    exactCombinationLimit: config.permutationExactCombinationLimit,
                    seed: config.permutationSeedBase + 700
                ) {
                    permutationRows.append(
                        EntryCohortPermutationRow(
                            analysis: "Matched FE (±\(config.matchingYearWindow) year)",
                            cohortBucket: "Matched set",
                            model: perm.model,
                            term: perm.term,
                            observedEstimate: perm.observedEstimate,
                            nullMean: perm.nullMean,
                            nullStdDev: perm.nullStdDev,
                            nullQ025: perm.nullQ025,
                            nullQ975: perm.nullQ975,
                            pTwoSided: perm.pTwoSided,
                            nPermutations: perm.nPermutations,
                            inferenceMethod: perm.inferenceMethod
                        )
                    )
                }
            }

            if let slopeSummary = matchedAverageSlopeGap(
                rows: matchedRows,
                matchedPeople: matchedPeople,
                firstYearByPerson: matchedFirstMap,
                horizonYears: config.matchedSlopeHorizonYears
            ) {
                summaryRows.append(slopeSummary)
            }
        }

        func fileStem(_ base: String) -> String {
            var stem = cohort.key == primaryMHICohort.key ? base : "\(base)_\(cohort.key)"
            if let suffix = outputSuffix, !suffix.isEmpty {
                stem += "_\(suffix)"
            }
            return stem
        }

        writeEntryCohortSummary(rows: summaryRows, fileStem: fileStem("entry_cohort_growth_summary"))
        writeEntryCohortPermutation(rows: permutationRows, fileStem: fileStem("entry_cohort_permutation_summary"))
        writeMatchedPairs(rows: pairs, fileStem: fileStem("entry_cohort_matched_pairs"))
    }

    let disclosureFirstYearMap = firstDisclosureYearByPerson(rows)
    if cohort.key == primaryMHICohort.key {
        let cvStartYearByCanonicalName = loadCVStartYearByCanonicalName()
        if !cvStartYearByCanonicalName.isEmpty {
            let cvFirstYearMap = firstYearMapUsingCVOverrides(
                rows: rows,
                baseFirstYearMap: disclosureFirstYearMap,
                cvStartYearByCanonicalName: cvStartYearByCanonicalName
            )
            let canonicalToPersonIDs = Dictionary(grouping: rows, by: { canonicalFacultyName($0.personID) })
            let overridePersonIDs = Set(cvStartYearByCanonicalName.keys.flatMap { canonical in
                (canonicalToPersonIDs[canonical] ?? []).map(\.personID)
            })
            let cvFirstYearMapCensored = applyLeftCensorRule(
                firstYearMap: cvFirstYearMap,
                keepPersonIDs: overridePersonIDs,
                censorYear: disclosureLeftCensorYear
            )
            let disclosureFirstYearMapCensored = applyLeftCensorRule(
                firstYearMap: disclosureFirstYearMap,
                keepPersonIDs: [],
                censorYear: disclosureLeftCensorYear
            )
            // Main outputs use CV-derived starts with disclosure fallback.
            runWithFirstYearMap(cvFirstYearMapCensored, outputSuffix: nil)
            // Keep disclosure-only outputs for traceability/sensitivity checks.
            runWithFirstYearMap(disclosureFirstYearMapCensored, outputSuffix: "disclosure_start")
            return
        }
    }
    let disclosureFirstYearMapCensored = applyLeftCensorRule(
        firstYearMap: disclosureFirstYearMap,
        keepPersonIDs: [],
        censorYear: disclosureLeftCensorYear
    )
    runWithFirstYearMap(disclosureFirstYearMapCensored, outputSuffix: nil)
}
