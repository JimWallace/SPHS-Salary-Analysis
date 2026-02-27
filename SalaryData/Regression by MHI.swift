import Foundation

// Helper functions for matrix operations.
func multiply(_ A: [[Double]], _ B: [[Double]]) -> [[Double]] {
    let m = A.count, n = A[0].count, p = B[0].count
    var result = Array(repeating: Array(repeating: 0.0, count: p), count: m)
    for i in 0..<m {
        for j in 0..<p {
            for k in 0..<n {
                result[i][j] += A[i][k] * B[k][j]
            }
        }
    }
    return result
}

func transpose(_ A: [[Double]]) -> [[Double]] {
    let m = A.count, n = A[0].count
    var result = Array(repeating: Array(repeating: 0.0, count: m), count: n)
    for i in 0..<m {
        for j in 0..<n {
            result[j][i] = A[i][j]
        }
    }
    return result
}

func invertMatrix(_ A: [[Double]]) -> [[Double]]? {
    let n = A.count
    var A = A  // mutable copy
    var inv = Array(repeating: Array(repeating: 0.0, count: n), count: n)
    for i in 0..<n { inv[i][i] = 1.0 }
    
    for i in 0..<n {
        var pivot = A[i][i]
        if abs(pivot) < 1e-10 {
            var swapRow = i + 1
            while swapRow < n && abs(A[swapRow][i]) < 1e-10 { swapRow += 1 }
            if swapRow == n { return nil }
            A.swapAt(i, swapRow)
            inv.swapAt(i, swapRow)
            pivot = A[i][i]
        }
        
        for j in 0..<n {
            A[i][j] /= pivot
            inv[i][j] /= pivot
        }
        
        for k in 0..<n where k != i {
            let factor = A[k][i]
            for j in 0..<n {
                A[k][j] -= factor * A[i][j]
                inv[k][j] -= factor * inv[i][j]
            }
        }
    }
    return inv
}

// Perform regression across MHI and non-MHI faculty.
func regressionAnalysisMHI(records: [SalaryRecord]) {
    let n = records.count
    guard n > 0 else { return }
    
    // Construct the design matrix X with columns:
    // [1, Year, mhiIndicator, Year * mhiIndicator]
    var X = [[Double]](repeating: [Double](repeating: 0.0, count: 4), count: n)
    var y = [Double](repeating: 0.0, count: n)
    
    for (i, record) in records.enumerated() {
        let mhiIndicator = record.mhi ? 1.0 : 0.0
        X[i][0] = 1.0
        X[i][1] = Double(record.year)
        X[i][2] = mhiIndicator
        X[i][3] = Double(record.year) * mhiIndicator
        y[i] = record.salary
    }
    
    let Xt = transpose(X)
    let XtX = multiply(Xt, X)
    
    guard let XtXInv = invertMatrix(XtX) else {
        print("Matrix inversion failed.")
        return
    }
    
    // Compute Xᵀy
    var Xty = [Double](repeating: 0.0, count: 4)
    for i in 0..<4 {
        for j in 0..<n {
            Xty[i] += Xt[i][j] * y[j]
        }
    }
    
    // Calculate beta = (XᵀX)⁻¹ Xᵀy
    var beta = [Double](repeating: 0.0, count: 4)
    for i in 0..<4 {
        for j in 0..<4 {
            beta[i] += XtXInv[i][j] * Xty[j]
        }
    }
    
    // Output regression coefficients.
    print("Regression Coefficients:")
    print("Intercept: \(beta[0])")
    print("Year: \(beta[1])")
    print("MHI Indicator: \(beta[2])")
    print("Interaction (Year * MHI): \(beta[3])")
    
    // Interpretation:
    // For non-MHI faculty: salary = beta[0] + beta[1]*year.
    // For MHI faculty: salary = (beta[0] + beta[2]) + (beta[1] + beta[3])*year.
    // Here, beta[3] quantifies the difference in the annual salary growth rate between MHI and non-MHI faculty.
}

