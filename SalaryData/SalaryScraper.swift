//
//  main.swift
//  SalaryData
//
//  Created by Jim Wallace on 2024-12-12.
//

import Foundation
import SwiftSoup





@main
struct SalaryScraper {
    static let earliestDisclosureYear = 2011
    static var defaultLatestDisclosureYear: Int {
        // Public disclosure pages are typically available up to the previous salary year.
        Calendar.current.component(.year, from: Date()) - 1
    }

    static func disclosureYears(latestYear: Int? = nil) -> [Int] {
        let upper = max(earliestDisclosureYear, latestYear ?? defaultLatestDisclosureYear)
        return Array(earliestDisclosureYear...upper)
    }
    
    static func main() async {
        
        let candidateYears = disclosureYears()
        let urls = candidateYears.map { "https://uwaterloo.ca/about/accountability/salary-disclosure-\($0)" }
        
        
        var results: [SalaryRecord] = []
        if let cachedRecords = loadCachedSalaryRecords(), !cachedRecords.isEmpty {
            results = cachedRecords
            print("Loaded \(results.count) salary rows from local cache.")
        } else {
            await withTaskGroup(of: [SalaryRecord].self) { taskGroup in
                for urlString in urls {
                    taskGroup.addTask {
                        return await parseHTML(urlString)
                    }
                }
                
                for await records in taskGroup {
                    results.append(contentsOf: records)
                }
            }
            print("Local cache unavailable; fetched \(results.count) salary rows from remote disclosures.")
        }
        let normalizedResults = results.compactMap(normalizeToSPHSFacultyRecord(_:))
        let droppedCount = results.count - normalizedResults.count
        if droppedCount > 0 {
            print("Dropped \(droppedCount) non-SPHS or ambiguous disclosure rows after canonical name matching.")
        }
        results = normalizedResults
        
        let salaryDictionary: [ String : [(year: Int, salary: Double)] ] = results.reduce(into: [:]) { dict, record in
            dict["\(record.surname), \(record.givenName)", default: []].append( (year: record.year, salary: record.salary) )
        }
        
        // Write data to file
        let downloadsDirectory = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first!
        let fileURL = downloadsDirectory.appendingPathComponent("sphs_dictionary.csv")

        // Prepare CSV content
        do {
            
            let observedYears = Array(Set(results.map(\.year))).sorted()
            let years = {
                guard let minObserved = observedYears.first, let maxObserved = observedYears.last else { return candidateYears }
                return Array(minObserved...maxObserved)
            }()

            var csvContent = "Surname,Given name,MHI," + years.map { "\($0)" }.joined(separator: ",") + "\n"
            for (name, records) in salaryDictionary {
                var salaryByYear = [Int: Double]() // Map year to salary for quick lookup
                for record in records {
                    salaryByYear[record.year] = record.salary
                }
                
                let nameParts = name.split(separator: ",", maxSplits: 1, omittingEmptySubsequences: false)
                let surname = nameParts.count > 0 ? String(nameParts[0]).trimmingCharacters(in: .whitespaces) : ""
                let givenName = nameParts.count > 1 ? String(nameParts[1]).trimmingCharacters(in: .whitespaces) : ""
                
                // Add name and salaries for each year
                let row = [surname, givenName, isInPrimaryMHICohort(name).description] + years.map { year in
                    if let salary = salaryByYear[year] {
                        return "\(salary)"
                    } else {
                        return "" // Empty cell if no salary data for the year
                    }
                }
                
                if SPHSFacultyNames.contains(name) {
                    csvContent += row.map(escapeCSVField).joined(separator: ",") + "\n"
                }
            }
            
            // Write CSV to the file
            try csvContent.write(to: fileURL, atomically: true, encoding: .utf8)
            print("Dictionary written to: \(fileURL.path)")
        } catch {
            print("Error writing dictionary to file: \(error)")
        }
            

        //analyzeSalaries(records: results, for: "JAMES R. WALLACE")
        regressionAnalysisMHI(records: results)
        
    }

    private struct FacultyNameRef {
        let canonicalFullName: String
        let surname: String
        let given: String
        let surnameTokens: [String]
        let givenTokens: [String]
    }

    private static let facultyNameRefs: [FacultyNameRef] = SPHSFacultyNames.compactMap { name in
        let parts = name.split(separator: ",", maxSplits: 1, omittingEmptySubsequences: false)
        guard parts.count == 2 else { return nil }
        let surname = String(parts[0]).trimmingCharacters(in: .whitespacesAndNewlines)
        let given = String(parts[1]).trimmingCharacters(in: .whitespacesAndNewlines)
        let surnameTokens = tokenizeName(surname)
        let givenTokens = tokenizeName(given)
        guard !surnameTokens.isEmpty, !givenTokens.isEmpty else { return nil }
        return FacultyNameRef(
            canonicalFullName: "\(surname), \(given)",
            surname: surname,
            given: given,
            surnameTokens: surnameTokens,
            givenTokens: givenTokens
        )
    }

    private static func tokenizeName(_ value: String) -> [String] {
        value
            .uppercased()
            .components(separatedBy: CharacterSet.letters.inverted)
            .filter { !$0.isEmpty }
    }

    private static func givenNamesCompatible(_ canonicalGiven: [String], _ scrapedGiven: [String]) -> Bool {
        guard let canonicalPrimary = canonicalGiven.first,
              let scrapedPrimary = scrapedGiven.first else { return false }
        if canonicalPrimary == scrapedPrimary { return true }
        if canonicalPrimary.count == 1 && scrapedPrimary.hasPrefix(canonicalPrimary) { return true }
        if scrapedPrimary.count == 1 && canonicalPrimary.hasPrefix(scrapedPrimary) { return true }
        return false
    }

    private static func isEditDistanceAtMostOne(_ a: String, _ b: String) -> Bool {
        if a == b { return true }
        let aChars = Array(a)
        let bChars = Array(b)
        if abs(aChars.count - bChars.count) > 1 { return false }

        var i = 0
        var j = 0
        var edits = 0

        while i < aChars.count && j < bChars.count {
            if aChars[i] == bChars[j] {
                i += 1
                j += 1
                continue
            }
            edits += 1
            if edits > 1 { return false }
            if aChars.count > bChars.count {
                i += 1
            } else if bChars.count > aChars.count {
                j += 1
            } else {
                i += 1
                j += 1
            }
        }

        if i < aChars.count || j < bChars.count {
            edits += 1
        }
        return edits <= 1
    }

    private static func surnameTokensCompatible(_ canonical: [String], _ scraped: [String]) -> Bool {
        let canonicalSet = Set(canonical)
        if !canonicalSet.isDisjoint(with: Set(scraped)) {
            return true
        }

        for c in canonical {
            for s in scraped where isEditDistanceAtMostOne(c, s) {
                return true
            }
        }
        return false
    }

    private static func resolveCanonicalFacultyName(surname: String, givenName: String) -> FacultyNameRef? {
        let surnameTokens = tokenizeName(surname)
        let givenTokens = tokenizeName(givenName)
        guard !surnameTokens.isEmpty, !givenTokens.isEmpty else { return nil }

        var candidates: [FacultyNameRef] = []
        for ref in facultyNameRefs {
            if !givenNamesCompatible(ref.givenTokens, givenTokens) { continue }
            if !surnameTokensCompatible(ref.surnameTokens, surnameTokens) { continue }
            candidates.append(ref)
        }

        guard !candidates.isEmpty else { return nil }
        if candidates.count == 1 { return candidates[0] }

        let rowFirst = surnameTokens.first ?? ""
        let rowLast = surnameTokens.last ?? ""
        let ranked = candidates.map { candidate -> (score: Int, ref: FacultyNameRef) in
            var score = 0
            if candidate.surnameTokens.last == rowLast { score += 2 }
            if candidate.surnameTokens.first == rowFirst { score += 1 }
            return (score: score, ref: candidate)
        }.sorted { lhs, rhs in
            lhs.score > rhs.score
        }

        guard let best = ranked.first else { return nil }
        if ranked.count > 1 && best.score == ranked[1].score { return nil }
        return best.ref
    }

    private static func normalizeToSPHSFacultyRecord(_ record: SalaryRecord) -> SalaryRecord? {
        guard let resolved = resolveCanonicalFacultyName(surname: record.surname, givenName: record.givenName) else {
            return nil
        }

        let mhi = isInPrimaryMHICohort(resolved.canonicalFullName)
        return SalaryRecord(
            surname: resolved.surname,
            givenName: resolved.given,
            position: record.position,
            salary: record.salary,
            taxableBenefits: record.taxableBenefits,
            year: record.year,
            mhi: mhi
        )
    }

    static func loadCachedSalaryRecords() -> [SalaryRecord]? {
        let fileManager = FileManager.default
        let baseURL = URL(fileURLWithPath: fileManager.currentDirectoryPath, isDirectory: true)
        let candidates = [
            baseURL.appendingPathComponent("data/sphs.csv"),
            fileManager.urls(for: .downloadsDirectory, in: .userDomainMask).first?.appendingPathComponent("sphs_dictionary.csv")
        ].compactMap { $0 }

        for csvURL in candidates where fileManager.fileExists(atPath: csvURL.path) {
            guard let records = parseCachedSalaryMatrix(from: csvURL), !records.isEmpty else { continue }
            print("Using local salary cache: \(csvURL.path)")
            return records
        }
        return nil
    }

    static func parseCachedSalaryMatrix(from csvURL: URL) -> [SalaryRecord]? {
        let content: String
        do {
            content = try String(contentsOf: csvURL, encoding: .utf8)
        } catch {
            print("Failed reading cached salary CSV at \(csvURL.path): \(error)")
            return nil
        }

        let lines = content
            .split(whereSeparator: \.isNewline)
            .map(String.init)
            .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

        guard let headerLine = lines.first else { return nil }
        let headers = parseCSVLine(headerLine).map { normalizeHeader($0) }
        guard let surnameIndex = headers.firstIndex(where: { $0 == "surname" || $0 == "surame" }),
              let givenIndex = headers.firstIndex(where: { $0 == "givenname" }),
              let mhiIndex = headers.firstIndex(where: { $0 == "mhi" }) else {
            print("Cached salary CSV missing required columns at \(csvURL.path)")
            return nil
        }

        var yearByColumn: [Int: Int] = [:]
        for (index, header) in headers.enumerated() {
            if let year = Int(header), year >= earliestDisclosureYear, year <= 2100 {
                yearByColumn[index] = year
            }
        }
        guard !yearByColumn.isEmpty else { return nil }

        var records: [SalaryRecord] = []
        for line in lines.dropFirst() {
            let fields = parseCSVLine(line)
            guard surnameIndex < fields.count, givenIndex < fields.count, mhiIndex < fields.count else { continue }

            let surname = fields[surnameIndex].trimmingCharacters(in: .whitespacesAndNewlines)
            let givenName = fields[givenIndex].trimmingCharacters(in: .whitespacesAndNewlines)
            if surname.isEmpty || givenName.isEmpty { continue }
            let mhi = parseCSVBool(fields[mhiIndex])

            for (columnIndex, year) in yearByColumn {
                guard columnIndex < fields.count else { continue }
                let rawSalary = fields[columnIndex].trimmingCharacters(in: .whitespacesAndNewlines)
                if rawSalary.isEmpty { continue }
                let cleaned = rawSalary.replacingOccurrences(of: "[$,]", with: "", options: .regularExpression)
                guard let salary = Double(cleaned) else { continue }
                records.append(
                    SalaryRecord(
                        surname: surname,
                        givenName: givenName,
                        position: "",
                        salary: salary,
                        taxableBenefits: 0.0,
                        year: year,
                        mhi: mhi
                    )
                )
            }
        }

        return records
    }

    static func normalizeHeader(_ value: String) -> String {
        value
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: " ", with: "")
    }

    static func parseCSVBool(_ value: String) -> Bool {
        let normalized = value
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        return normalized == "true" || normalized == "1" || normalized == "yes"
    }
    
    
    static func parseHTML(_ html: String) async -> [SalaryRecord] {
                
        guard let url = URL(string: html) else {
            return []
        }
        
        let data: Data
        do {
            let (fetchedData, response) = try await URLSession.shared.data(from: url)
            if let httpResponse = response as? HTTPURLResponse,
               !(200...299).contains(httpResponse.statusCode) {
                print("Request failed for \(html) with status \(httpResponse.statusCode)")
                return []
            }
            data = fetchedData
        } catch {
            print("Network request failed for \(html): \(error)")
            return []
        }
        
        guard let htmlContent = String(data: data, encoding: .utf8) else {
            return []
        }
        
        var results: [SalaryRecord] = []
        
        let year = extractYear(from: html) ?? 0
        
        do {
            let document = try SwiftSoup.parse(htmlContent)
                        
            let rows = try document.select("table tr")
            
            for row in rows {
                
                // Skip header rows (rows containing <th> in the first row)
                if try row.select("th").count == row.childNodeSize() {
                    continue
                }
                
                let columns = try row.select("th, td")
                guard columns.count >= 5 else { continue }
                
                let surname = try columns[0].text()
                let givenName = try columns[1].text()
                let position = try columns[2].text()
                
                let salary = try Double(columns[3].text().replacingOccurrences(of: "[$,\\s]", with: "", options: .regularExpression)) ?? -1.0

                let taxableBenefits = try Double(columns[4].text().replacingOccurrences(of: "[$,\\s]", with: "", options: .regularExpression)) ?? -1.0
                
                let mhi = isInPrimaryMHICohort(surname + ", " + givenName)

                let record = SalaryRecord(surname: surname, givenName: givenName, position: position, salary: salary, taxableBenefits: taxableBenefits, year: year, mhi: mhi)
                //print(record)                
                results.append(record)
            }
        } catch {
            print("Error parsing HTML: \(error)")
        }
        
        return results
    }


    static func extractYear(from urlString: String) -> Int? {
        let regex = try? NSRegularExpression(pattern: "salary-disclosure-(\\d{4})")
        let range = NSRange(location: 0, length: urlString.utf16.count)
        if let match = regex?.firstMatch(in: urlString, options: [], range: range),
           let yearRange = Range(match.range(at: 1), in: urlString) {
            return Int(urlString[yearRange])
        }
        return nil
    }

    static func escapeCSVField(_ field: String) -> String {
        if field.contains(",") || field.contains("\"") || field.contains("\n") {
            return "\"\(field.replacingOccurrences(of: "\"", with: "\"\""))\""
        }
        return field
    }
    
}
