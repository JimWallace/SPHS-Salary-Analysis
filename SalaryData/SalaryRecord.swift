//
//  SalaryRecord.swift
//  SalaryData
//
//  Created by Jim Wallace on 2024-12-12.
//

import Foundation

struct SalaryRecord: Codable {
    let surname: String
    let givenName: String
    let position: String
    let salary: Double
    let taxableBenefits: Double
    let year: Int
    let mhi: Bool

    var fullName: String {
        return "\(givenName) \(surname)"
    }
}
