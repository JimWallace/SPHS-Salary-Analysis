import Foundation

struct SegmentedModelSummaryRow {
    let breakYear: Int
    let model: String
    let preGrowthGap: Double
    let after2014GrowthGap: Double
    let afterK2GrowthGap: Double
    let phi2014: Double
    let phiK2: Double
    let phi2014SE: Double
    let phi2014CILow: Double
    let phi2014CIHigh: Double
    let phiK2SE: Double
    let phiK2CILow: Double
    let phiK2CIHigh: Double
    let nObs: Int
    let nClusters: Int
}

struct SegmentedPermutationRow {
    let breakYear: Int
    let model: String
    let term: String
    let observed: Double
    let nullMean: Double
    let nullStdDev: Double
    let nullQ025: Double
    let nullQ975: Double
    let pTwoSided: Double
    let nPermutations: Int
    let inferenceMethod: String
}

struct SegmentedSensitivityRow {
    let breakYear: Int
    let model: String
    let phi2014: Double
    let pPhi2014: Double
    let phiK2: Double
    let pPhiK2: Double
    let gapPre2014: Double
    let gap2014ToK2Minus1: Double
    let gapPostK2: Double
}

private func hinge(_ year: Int, knot: Int) -> Double {
    max(0.0, Double(year - knot))
}

private func pooledSegmentedGrowthModel(
    rows: [AnalysisRow],
    knot2014: Int,
    knot2: Int
) -> OLSResult? {
    let X = rows.map { row -> [Double] in
        let yc = row.yearCentered
        let m = row.mhi
        let k2014 = hinge(row.year, knot: knot2014)
        let kK2 = hinge(row.year, knot: knot2)
        return [
            1.0,
            yc,
            k2014,
            kK2,
            m,
            yc * m,
            k2014 * m,
            kK2 * m
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
            "K2014",
            "KK2",
            "MHI",
            "YearCenteredXMHI",
            "K2014XMHI",
            "KK2XMHI"
        ]
    )
}

private func fixedEffectsSegmentedGrowthModel(
    rows: [AnalysisRow],
    knot2014: Int,
    knot2: Int
) -> OLSResult? {
    let grouped = Dictionary(grouping: rows, by: \.personID)
    var transformedX: [[Double]] = []
    var transformedY: [Double] = []
    var transformedClusterIDs: [String] = []

    for (personID, personRows) in grouped {
        guard personRows.count >= 2 else { continue }
        let meanY = personRows.map(\.salary).reduce(0.0, +) / Double(personRows.count)

        let rawX = personRows.map { row -> [Double] in
            let yc = row.yearCentered
            let m = row.mhi
            let k2014 = hinge(row.year, knot: knot2014)
            let kK2 = hinge(row.year, knot: knot2)
            return [
                yc,
                k2014,
                kK2,
                yc * m,
                k2014 * m,
                kK2 * m
            ]
        }
        let means = (0..<6).map { col in
            rawX.map { $0[col] }.reduce(0.0, +) / Double(rawX.count)
        }

        for (idx, row) in personRows.enumerated() {
            let demeaned = (0..<6).map { col in rawX[idx][col] - means[col] }
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
            "K2014",
            "KK2",
            "YearCenteredXMHI",
            "K2014XMHI",
            "KK2XMHI"
        ]
    )
}

private func segmentedSummaryFromResult(
    result: OLSResult,
    model: String,
    breakYear: Int
) -> SegmentedModelSummaryRow? {
    guard let preIdx = result.variableNames.firstIndex(of: "YearCenteredXMHI"),
          let phi2014Idx = result.variableNames.firstIndex(of: "K2014XMHI"),
          let phiK2Idx = result.variableNames.firstIndex(of: "KK2XMHI") else {
        return nil
    }

    let pre = result.coefficients[preIdx]
    let phi2014 = result.coefficients[phi2014Idx]
    let phiK2 = result.coefficients[phiK2Idx]

    let gapAfter2014 = pre + phi2014
    let gapAfterK2 = pre + phi2014 + phiK2

    let sePhi2014 = result.standardErrors[phi2014Idx]
    let ciPhi2014 = confidenceInterval95(estimate: phi2014, standardError: sePhi2014)
    let sePhiK2 = result.standardErrors[phiK2Idx]
    let ciPhiK2 = confidenceInterval95(estimate: phiK2, standardError: sePhiK2)

    return SegmentedModelSummaryRow(
        breakYear: breakYear,
        model: model,
        preGrowthGap: pre,
        after2014GrowthGap: gapAfter2014,
        afterK2GrowthGap: gapAfterK2,
        phi2014: phi2014,
        phiK2: phiK2,
        phi2014SE: sePhi2014,
        phi2014CILow: ciPhi2014.0,
        phi2014CIHigh: ciPhi2014.1,
        phiK2SE: sePhiK2,
        phiK2CILow: ciPhiK2.0,
        phiK2CIHigh: ciPhiK2.1,
        nObs: result.nObs,
        nClusters: result.nClusters
    )
}

private func writeSegmentedModelSummary(rows: [SegmentedModelSummaryRow], fileStem: String) {
    let fm = FileManager.default
    let outDir = URL(fileURLWithPath: fm.currentDirectoryPath, isDirectory: true)
        .appendingPathComponent("analysis_output", isDirectory: true)
    do {
        try fm.createDirectory(at: outDir, withIntermediateDirectories: true, attributes: nil)
        var csv = "breakYear,model,preGrowthGap,after2014GrowthGap,afterK2GrowthGap,phi2014,phiK2,phi2014SE,phi2014CILow,phi2014CIHigh,phiK2SE,phiK2CILow,phiK2CIHigh,nObs,nClusters\n"
        for r in rows {
            csv += [
                "\(r.breakYear)",
                csvEscaped(r.model),
                format(r.preGrowthGap),
                format(r.after2014GrowthGap),
                format(r.afterK2GrowthGap),
                format(r.phi2014),
                format(r.phiK2),
                format(r.phi2014SE),
                format(r.phi2014CILow),
                format(r.phi2014CIHigh),
                format(r.phiK2SE),
                format(r.phiK2CILow),
                format(r.phiK2CIHigh),
                "\(r.nObs)",
                "\(r.nClusters)"
            ].joined(separator: ",") + "\n"
        }
        let url = outDir.appendingPathComponent("\(fileStem).csv")
        try csv.write(to: url, atomically: true, encoding: .utf8)
        print("Wrote segmented-model CSV summary: \(url.path)")
    } catch {
        print("Failed to write segmented-model summary: \(error)")
    }
}

private func writeSegmentedPermutationSummary(rows: [SegmentedPermutationRow], fileStem: String) {
    let fm = FileManager.default
    let outDir = URL(fileURLWithPath: fm.currentDirectoryPath, isDirectory: true)
        .appendingPathComponent("analysis_output", isDirectory: true)
    do {
        try fm.createDirectory(at: outDir, withIntermediateDirectories: true, attributes: nil)
        var csv = "breakYear,model,term,observed,nullMean,nullStdDev,nullQ025,nullQ975,pTwoSided,nPermutations,inferenceMethod\n"
        for r in rows {
            csv += [
                "\(r.breakYear)",
                csvEscaped(r.model),
                csvEscaped(r.term),
                format(r.observed),
                format(r.nullMean),
                format(r.nullStdDev),
                format(r.nullQ025),
                format(r.nullQ975),
                format(r.pTwoSided),
                "\(r.nPermutations)",
                csvEscaped(r.inferenceMethod.replacingOccurrences(of: "_", with: "-"))
            ].joined(separator: ",") + "\n"
        }
        let url = outDir.appendingPathComponent("\(fileStem).csv")
        try csv.write(to: url, atomically: true, encoding: .utf8)
        print("Wrote segmented-permutation CSV summary: \(url.path)")
    } catch {
        print("Failed to write segmented-permutation summary: \(error)")
    }
}

private func writeSegmentedSensitivity(rows: [SegmentedSensitivityRow], fileStem: String) {
    let fm = FileManager.default
    let outDir = URL(fileURLWithPath: fm.currentDirectoryPath, isDirectory: true)
        .appendingPathComponent("analysis_output", isDirectory: true)
    do {
        try fm.createDirectory(at: outDir, withIntermediateDirectories: true, attributes: nil)
        var csv = "breakYear,model,phi2014,p_phi2014,phiK2,p_phiK2,gap_pre2014,gap_2014_to_k2minus1,gap_postk2\n"
        for r in rows {
            csv += [
                "\(r.breakYear)",
                csvEscaped(r.model),
                format(r.phi2014),
                format(r.pPhi2014),
                format(r.phiK2),
                format(r.pPhiK2),
                format(r.gapPre2014),
                format(r.gap2014ToK2Minus1),
                format(r.gapPostK2)
            ].joined(separator: ",") + "\n"
        }
        let url = outDir.appendingPathComponent("\(fileStem).csv")
        try csv.write(to: url, atomically: true, encoding: .utf8)
        print("Wrote segmented-sensitivity CSV summary: \(url.path)")
    } catch {
        print("Failed to write segmented-sensitivity summary: \(error)")
    }
}

private func writeSegmentedMarkerPlot(rows: [AnalysisRow], knot2Year: Int) {
    let years = Array(Set(rows.map(\.year))).sorted()
    guard !years.isEmpty else { return }

    var meanA: [Int: Double] = [:]
    var meanB: [Int: Double] = [:]
    for year in years {
        let yrRows = rows.filter { $0.year == year }
        let a = yrRows.filter { $0.mhi == 1.0 }.map(\.salary)
        let b = yrRows.filter { $0.mhi == 0.0 }.map(\.salary)
        if !a.isEmpty { meanA[year] = a.reduce(0.0, +) / Double(a.count) }
        if !b.isEmpty { meanB[year] = b.reduce(0.0, +) / Double(b.count) }
    }
    let allY = Array(meanA.values) + Array(meanB.values)
    guard let minY = allY.min(), let maxY = allY.max(), maxY > minY else { return }

    let width = 1100.0
    let height = 650.0
    let left = 90.0
    let right = 40.0
    let top = 40.0
    let bottom = 70.0
    let plotW = width - left - right
    let plotH = height - top - bottom
    let minYear = Double(years.min()!)
    let maxYear = Double(years.max()!)

    func x(_ year: Int) -> Double {
        left + (Double(year) - minYear) / max(1.0, (maxYear - minYear)) * plotW
    }
    func y(_ value: Double) -> Double {
        top + (maxY - value) / (maxY - minY) * plotH
    }
    func polyline(_ dict: [Int: Double]) -> String {
        years.compactMap { yr in
            dict[yr].map { "\(x(yr)),\(y($0))" }
        }.joined(separator: " ")
    }

    let x2014 = x(2014)
    let xK2 = x(knot2Year)
    let svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="\(Int(width))" height="\(Int(height))">
      <rect x="0" y="0" width="100%" height="100%" fill="white"/>
      <line x1="\(left)" y1="\(top + plotH)" x2="\(left + plotW)" y2="\(top + plotH)" stroke="#333" stroke-width="1.2"/>
      <line x1="\(left)" y1="\(top)" x2="\(left)" y2="\(top + plotH)" stroke="#333" stroke-width="1.2"/>
      <line x1="\(x2014)" y1="\(top)" x2="\(x2014)" y2="\(top + plotH)" stroke="#666" stroke-dasharray="6,6" stroke-width="1.3"/>
      <line x1="\(xK2)" y1="\(top)" x2="\(xK2)" y2="\(top + plotH)" stroke="#111" stroke-dasharray="6,6" stroke-width="1.3"/>
      <polyline fill="none" stroke="#C44E52" stroke-width="2.8" points="\(polyline(meanA))"/>
      <polyline fill="none" stroke="#4C72B0" stroke-width="2.8" points="\(polyline(meanB))"/>
      <text x="\(left)" y="24" font-size="16" font-family="Times New Roman">Mean Salary by Group with Regime Knots</text>
      <text x="\(x2014 + 5)" y="\(top + 18)" font-size="12" font-family="Times New Roman">2014 knot</text>
      <text x="\(xK2 + 5)" y="\(top + 34)" font-size="12" font-family="Times New Roman">\(knot2Year) knot</text>
      <text x="\(left + plotW - 170)" y="\(top + 22)" font-size="12" fill="#C44E52" font-family="Times New Roman">Group A</text>
      <text x="\(left + plotW - 170)" y="\(top + 40)" font-size="12" fill="#4C72B0" font-family="Times New Roman">Group B</text>
    </svg>
    """

    let fm = FileManager.default
    let figDir = URL(fileURLWithPath: fm.currentDirectoryPath, isDirectory: true)
        .appendingPathComponent("figures", isDirectory: true)
    do {
        try fm.createDirectory(at: figDir, withIntermediateDirectories: true, attributes: nil)
        let outURL = figDir.appendingPathComponent("segmented_trajectory_markers.svg")
        try svg.write(to: outURL, atomically: true, encoding: .utf8)
        print("Wrote segmented marker plot: \(outURL.path)")
    } catch {
        print("Failed to write segmented marker plot: \(error)")
    }
}

func runSegmentedGrowthAnalysis(
    rows: [AnalysisRow],
    cohort: CohortDefinition,
    config: RegressionAnalysisConfig
) {
    if !config.runPermutationInference {
        print("Skipping segmented permutation inference for cohort: \(cohort.label)")
    }
    let knot2014 = config.knotsFixed.first ?? 2014
    let knotYears = Array(Set(config.knot2SensitivityYears + [config.knot2SalaryYear])).sorted()
    let feRows = rowsWithAtLeastTwoObservations(rows)

    var modelRows: [SegmentedModelSummaryRow] = []
    var permRows: [SegmentedPermutationRow] = []
    var sensitivityRows: [SegmentedSensitivityRow] = []

    for knot2 in knotYears {
        let pooled = pooledSegmentedGrowthModel(rows: rows, knot2014: knot2014, knot2: knot2)
        let fe = fixedEffectsSegmentedGrowthModel(rows: feRows, knot2014: knot2014, knot2: knot2)

        if let pooled, let summary = segmentedSummaryFromResult(result: pooled, model: "Pooled OLS (Segmented)", breakYear: knot2) {
            modelRows.append(summary)

            var pPhi2014: PermutationSummaryRow?
            var pPhiK2: PermutationSummaryRow?
            if config.runPermutationInference {
                pPhi2014 = permutationSummaryForSelectedCoefficient(
                    rows: rows,
                    modelName: "Pooled OLS (Segmented)",
                    slopeGapTerm: "K2014XMHI",
                    fitModel: { pooledSegmentedGrowthModel(rows: $0, knot2014: knot2014, knot2: knot2) },
                    coefficientIndexResolver: { result in result.variableNames.firstIndex(of: "K2014XMHI") },
                    randomDraws: config.permutationDraws,
                    exactCombinationLimit: config.permutationExactCombinationLimit,
                    seed: config.permutationSeedBase + 100 + UInt64(knot2)
                )
                pPhiK2 = permutationSummaryForSelectedCoefficient(
                    rows: rows,
                    modelName: "Pooled OLS (Segmented)",
                    slopeGapTerm: "KK2XMHI",
                    fitModel: { pooledSegmentedGrowthModel(rows: $0, knot2014: knot2014, knot2: knot2) },
                    coefficientIndexResolver: { result in result.variableNames.firstIndex(of: "KK2XMHI") },
                    randomDraws: config.permutationDraws,
                    exactCombinationLimit: config.permutationExactCombinationLimit,
                    seed: config.permutationSeedBase + 200 + UInt64(knot2)
                )
            }

            if let perm = pPhi2014 {
                permRows.append(
                    SegmentedPermutationRow(
                        breakYear: knot2,
                        model: perm.model,
                        term: perm.term,
                        observed: perm.observedEstimate,
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
            if let perm = pPhiK2 {
                permRows.append(
                    SegmentedPermutationRow(
                        breakYear: knot2,
                        model: perm.model,
                        term: perm.term,
                        observed: perm.observedEstimate,
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

            sensitivityRows.append(
                SegmentedSensitivityRow(
                    breakYear: knot2,
                    model: "Pooled OLS (Segmented)",
                    phi2014: summary.phi2014,
                    pPhi2014: pPhi2014?.pTwoSided ?? Double.nan,
                    phiK2: summary.phiK2,
                    pPhiK2: pPhiK2?.pTwoSided ?? Double.nan,
                    gapPre2014: summary.preGrowthGap,
                    gap2014ToK2Minus1: summary.after2014GrowthGap,
                    gapPostK2: summary.afterK2GrowthGap
                )
            )
        }

        if let fe, let summary = segmentedSummaryFromResult(result: fe, model: "Person FE (Segmented)", breakYear: knot2) {
            modelRows.append(summary)

            var pPhi2014: PermutationSummaryRow?
            var pPhiK2: PermutationSummaryRow?
            if config.runPermutationInference {
                pPhi2014 = permutationSummaryForSelectedCoefficient(
                    rows: feRows,
                    modelName: "Person FE (Segmented)",
                    slopeGapTerm: "K2014XMHI",
                    fitModel: { fixedEffectsSegmentedGrowthModel(rows: $0, knot2014: knot2014, knot2: knot2) },
                    coefficientIndexResolver: { result in result.variableNames.firstIndex(of: "K2014XMHI") },
                    randomDraws: config.permutationDraws,
                    exactCombinationLimit: config.permutationExactCombinationLimit,
                    seed: config.permutationSeedBase + 300 + UInt64(knot2)
                )
                pPhiK2 = permutationSummaryForSelectedCoefficient(
                    rows: feRows,
                    modelName: "Person FE (Segmented)",
                    slopeGapTerm: "KK2XMHI",
                    fitModel: { fixedEffectsSegmentedGrowthModel(rows: $0, knot2014: knot2014, knot2: knot2) },
                    coefficientIndexResolver: { result in result.variableNames.firstIndex(of: "KK2XMHI") },
                    randomDraws: config.permutationDraws,
                    exactCombinationLimit: config.permutationExactCombinationLimit,
                    seed: config.permutationSeedBase + 400 + UInt64(knot2)
                )
            }

            if let perm = pPhi2014 {
                permRows.append(
                    SegmentedPermutationRow(
                        breakYear: knot2,
                        model: perm.model,
                        term: perm.term,
                        observed: perm.observedEstimate,
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
            if let perm = pPhiK2 {
                permRows.append(
                    SegmentedPermutationRow(
                        breakYear: knot2,
                        model: perm.model,
                        term: perm.term,
                        observed: perm.observedEstimate,
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

            sensitivityRows.append(
                SegmentedSensitivityRow(
                    breakYear: knot2,
                    model: "Person FE (Segmented)",
                    phi2014: summary.phi2014,
                    pPhi2014: pPhi2014?.pTwoSided ?? Double.nan,
                    phiK2: summary.phiK2,
                    pPhiK2: pPhiK2?.pTwoSided ?? Double.nan,
                    gapPre2014: summary.preGrowthGap,
                    gap2014ToK2Minus1: summary.after2014GrowthGap,
                    gapPostK2: summary.afterK2GrowthGap
                )
            )
        }
    }

    let modelStem = cohort.key == primaryMHICohort.key ? "segmented_model_summary" : "segmented_model_summary_\(cohort.key)"
    let permStem = cohort.key == primaryMHICohort.key ? "segmented_permutation_summary" : "segmented_permutation_summary_\(cohort.key)"
    let sensitivityStem = cohort.key == primaryMHICohort.key ? "segmented_sensitivity" : "segmented_sensitivity_\(cohort.key)"

    writeSegmentedModelSummary(rows: modelRows, fileStem: modelStem)
    writeSegmentedPermutationSummary(rows: permRows, fileStem: permStem)
    writeSegmentedSensitivity(rows: sensitivityRows, fileStem: sensitivityStem)

    if cohort.key == primaryMHICohort.key {
        writeSegmentedMarkerPlot(rows: rows, knot2Year: config.knot2SalaryYear)
    }
}
