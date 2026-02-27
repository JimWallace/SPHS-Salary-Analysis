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
    
    static func main() async {
        
        let years = Array(2011...2024)
        
        let urls = [
            "https://uwaterloo.ca/about/accountability/salary-disclosure-2011",
            "https://uwaterloo.ca/about/accountability/salary-disclosure-2012",
            "https://uwaterloo.ca/about/accountability/salary-disclosure-2013",
            "https://uwaterloo.ca/about/accountability/salary-disclosure-2014",
            "https://uwaterloo.ca/about/accountability/salary-disclosure-2015",
            "https://uwaterloo.ca/about/accountability/salary-disclosure-2016",
            "https://uwaterloo.ca/about/accountability/salary-disclosure-2017",
            "https://uwaterloo.ca/about/accountability/salary-disclosure-2018",
            "https://uwaterloo.ca/about/accountability/salary-disclosure-2019",
            "https://uwaterloo.ca/about/accountability/salary-disclosure-2020",
            "https://uwaterloo.ca/about/accountability/salary-disclosure-2021",
            "https://uwaterloo.ca/about/accountability/salary-disclosure-2022",
            "https://uwaterloo.ca/about/accountability/salary-disclosure-2023",
            "https://uwaterloo.ca/about/accountability/salary-disclosure-2024"
        ]
        
        
        var results: [SalaryRecord] = []
        
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
        results = results.filter{ SPHSFacultyNames.contains($0.surname + ", " + $0.givenName) }
        
        let salaryDictionary: [ String : [(year: Int, salary: Double)] ] = results.reduce(into: [:]) { dict, record in
            dict["\(record.surname), \(record.givenName)", default: []].append( (year: record.year, salary: record.salary) )
        }
        
        // Write data to file
        let downloadsDirectory = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first!
        let fileURL = downloadsDirectory.appendingPathComponent("sphs_dictionary.csv")

        // Prepare CSV content
        do {
            
            var csvContent = "Surame, Given name, MHI," + years.map { "\($0)" }.joined(separator: ",") + "\n"
            for (name, records) in salaryDictionary {
                var salaryByYear = [Int: Double]() // Map year to salary for quick lookup
                for record in records {
                    salaryByYear[record.year] = record.salary
                }
                
                // Add name and salaries for each year
                let row = [name] + [ MHIFacultyNames.contains(name).description  ] + years.map { year in
                    if let salary = salaryByYear[year] {
                        return "\(salary)"
                    } else {
                        return "" // Empty cell if no salary data for the year
                    }
                }
                
                if SPHSFacultyNames.contains(name) {
                    csvContent += row.joined(separator: ",") + "\n"
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
    
    
    static func parseHTML(_ html: String) async -> [SalaryRecord] {
                
        guard let url = URL(string: html) else {
            return []
        }
        
        let (data, _) = try! await URLSession.shared.data(from: url)
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
                guard columns.count >= 3 else { continue }
                
                let surname = try columns[0].text()
                let givenName = try columns[1].text()
                let position = try columns[2].text()
                
                let salary = try Double(columns[3].text().replacingOccurrences(of: "[$,\\s]", with: "", options: .regularExpression)) ?? -1.0

                let taxableBenefits = try Double(columns[4].text().replacingOccurrences(of: "[$,\\s]", with: "", options: .regularExpression)) ?? -1.0
                
                let mhi = MHIFacultyNames.contains(surname + ", " + givenName)

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
    
}
