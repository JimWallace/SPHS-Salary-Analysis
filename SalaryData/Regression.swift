//
//  Regression.swift
//  SalaryData
//
//  Created by Jim Wallace on 2025-02-19.
//

import Foundation

func linearRegressionContinuous(for records: [SalaryRecord]) -> (slope: Double, intercept: Double)? {
    // Sort records by year.
    let sortedRecords = records.sorted { $0.year < $1.year }
    guard !sortedRecords.isEmpty else { return nil }
    
    // Partition into continuous segments (consecutive years).
    var segments: [[SalaryRecord]] = []
    var currentSegment: [SalaryRecord] = [sortedRecords[0]]
    
    for record in sortedRecords.dropFirst() {
        if record.year == currentSegment.last!.year + 1 {
            currentSegment.append(record)
        } else {
            segments.append(currentSegment)
            currentSegment = [record]
        }
    }
    segments.append(currentSegment)
    
    // Choose the longest continuous segment.
    guard let longestSegment = segments.max(by: { $0.count < $1.count }),
          longestSegment.count >= 2 else { return nil }
    
    let n = Double(longestSegment.count)
    let sumX = longestSegment.reduce(0.0) { $0 + Double($1.year) }
    let sumY = longestSegment.reduce(0.0) { $0 + $1.salary }
    let sumXY = longestSegment.reduce(0.0) { $0 + Double($1.year) * $1.salary }
    let sumXX = longestSegment.reduce(0.0) { $0 + pow(Double($1.year), 2) }
    
    let denominator = n * sumXX - pow(sumX, 2)
    guard denominator != 0 else { return nil }
    
    let slope = (n * sumXY - sumX * sumY) / denominator
    let intercept = (sumY - slope * sumX) / n
    
    return (slope, intercept)
}

func analyzeSalaries(records: [SalaryRecord], for targetFullName: String) {
    // Group records by full name.
    let groupedRecords = Dictionary(grouping: records, by: { $0.fullName })
    
    var regressionResults: [String: (slope: Double, intercept: Double)] = [:]
    for (name, recs) in groupedRecords {
        let sortedRecords = recs.sorted { $0.year < $1.year }
        if let regression = linearRegressionContinuous(for: sortedRecords) {
            regressionResults[name] = regression
        }
    }
    
    guard let targetRegression = regressionResults[targetFullName] else {
        print("No data found for \(targetFullName).")
        for r in regressionResults {
            print(r)
        }
        return
    }
    
    print("Regression for \(targetFullName): Slope = \(targetRegression.slope), Intercept = \(targetRegression.intercept)")
    
    for (name, regression) in regressionResults where name != targetFullName {
        print("Regression for \(name): Slope = \(regression.slope), Intercept = \(regression.intercept)")
        if regression.slope > targetRegression.slope {
            print("\(name)'s salary is growing faster than \(targetFullName)'s.\n")
        } else if regression.slope < targetRegression.slope {
            print("\(name)'s salary is growing slower than \(targetFullName)'s.\n")
        } else {
            print("\(name)'s salary growth rate is similar to \(targetFullName)'s.\n")
        }
    }
}
