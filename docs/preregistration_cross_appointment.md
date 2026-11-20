# Pre-registration (draft): cross-appointment and annual salary increases at the University of Waterloo

*Draft for posting on OSF before the confirmatory analysis is run. Written on 2026-11-20, after the
university-wide roster and salary panel were assembled but before any university-wide outcome was
computed.*

## Background and origin of the hypothesis

In an exploratory analysis of the School of Public Health Sciences (SPHS), all eight faculty with a
cross- or joint appointment to another University of Waterloo unit had below-median average annual
raises, and cross-appointment accounted for much of an apparent gap affecting Master of Health
Informatics faculty. That analysis was not pre-specified. This study tests the hypothesis on new data.

**Conflict of interest.** The author is an SPHS faculty member with a cross-appointment and is
therefore in the group that generated the hypothesis. SPHS is excluded from the confirmatory sample.

## Hypothesis

**H1.** Faculty who hold a cross- or joint appointment with another University of Waterloo academic
unit receive smaller annual salary increases than faculty in the same home unit who do not.

Directional; tested one-sided.

## Data (all public)

1. **Salaries:** University of Waterloo public salary disclosures, calendar years 2011–2025
   (individuals paid $100,000 or more). Disclosed title gives academic rank.
2. **Roster and cross-appointments:** public faculty listings (`/<unit>/contacts`) and profile pages
   of 41 main-campus academic units, retrieved November 2026.

## Sample

- People listed as faculty (professorial or lecturer positions; adjunct, emeritus, visiting,
  research-only and externally affiliated positions excluded) by at least one unit, and linked to
  the disclosures by surname and first given name. Names shared by two disclosed people in any year
  are dropped.
- **SPHS faculty (home unit SPHS) are excluded** from the confirmatory test.
- People whose home unit cannot be determined are excluded.
- Annual raises in calendar years **2016–2025** (before 2016 the $100,000 threshold leaves too few
  faculty per unit).

## Variables

- **Exposure (primary): cross-appointed** = listed as faculty by two or more units, **or** the
  person's profile states a cross- or joint appointment with another UW unit.
  - Secondary definitions: listing-based only; profile-based only; joint appointments only.
- **Home unit:** the unit listing the person with a plain title (no other unit named in the
  position); if ambiguous, the unit whose profile states the appointment *with* another unit.
- **Outcome:** annual raise = disclosed salary in year *t* minus year *t−1*, minus the median raise
  among included faculty in the same home unit and year (the **residual raise**). Excluded raises:
  a person's second disclosed year (possible partial first year), the year of a change in disclosed
  rank and the year after. Units with fewer than 5 included faculty in a year contribute no
  residuals for that year.

## Analysis

- **Primary test:** each person's mean residual raise; difference in means between cross-appointed
  and other faculty, weighting people equally. p-value from 10,000 permutations that reassign
  cross-appointment status among people **within the same home unit**. Reject the null if
  one-sided p < 0.05.
- **Primary estimate:** the same difference with a 95% interval from a person-level bootstrap
  stratified by home unit.
- **Secondary (reported regardless of result):**
  - person-year regression with year and home-unit fixed effects, errors clustered by person;
  - the result by Faculty (Arts, Engineering, Environment, Health, Mathematics, Science);
  - joint vs cross-appointments;
  - restricted to tenured/tenure-track ranks;
  - percentage raises instead of dollars.
- **Not tested here:** causal direction. Cross-appointment status is a current snapshot, so a
  difference could reflect who takes cross-appointments rather than their effect.

## Deviations

Any change to these definitions after outcome data are examined will be reported as a deviation,
with both the pre-registered and revised results.
