# Pre-registration (draft): cross-appointment and annual salary increases at the University of Waterloo

*Draft for posting on OSF before the confirmatory analysis is run. Written on 2026-11-20, after the
university-wide roster and salary panel were assembled but before any university-wide outcome was
computed.*

**Assembled data (before outcomes):** 41 units; 1,525 faculty listings; 1,106 people linked to the
disclosures; 1,045 with a resolved home unit, of whom 130 are cross-appointed (Arts 12, Engineering
59, Environment 3, Health 17, Mathematics 17, Science 22). SPHS-home faculty (29) are excluded from
the test.

## Background and origin of the hypothesis

In an exploratory analysis of the School of Public Health Sciences (SPHS), 9 of the 10 faculty in the
salary sample with a cross- or joint appointment to another University of Waterloo unit had
below-median average annual raises (2012–2025; exact probability under no association 0.004). Most
Master of Health Informatics (MHI) faculty are cross-appointed, and with 29 people the two attributes
could not be separated: each was associated with raises about $1,000 a year below the School median
when both were modelled. That analysis was not pre-specified (an earlier version, using profile
wording only, identified 8 of the 11 cross-appointed faculty). This study tests the cross-appointment
hypothesis on new data.

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
- People whose home unit cannot be determined are excluded. In the assembled data this is 60 of the
  190 cross-appointed people, mostly joint appointments split evenly between two units; they are
  reported descriptively.
- Two-unit listings count as one person only with evidence of a cross-appointment (a position naming
  another unit, a profile statement, a shared profile page, or an identical full name that is unique in
  the disclosures); otherwise the name is treated as a possible collision and excluded.
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
