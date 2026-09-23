# ECMWF Single Runs provenance review

Reviewed 2026-09-23. Scope: `ecmwf_ifs`, initializations `2026-01-31T00:00Z` and `2026-02-14T00:00Z`, used in the saved weather examples.

## Finding: unresolved for these two releases

Public official sources do not unambiguously identify these two responses as either original operational forecasts published on those dates or forecasts recomputed later. Do not classify them as confirmed operational archives or as confirmed retrospective recomputations. Their current status is `unresolved_operational_vs_retrospective`.

In ECMWF terminology, a hindcast/re-forecast is a retrospective calculation, not merely another name for downloading an old operational forecast. However, that general definition alone does not establish which production stream Open-Meteo used for either selected release. Successful retrieval, `run`, valid times, plausible values and the operational model cycle are insufficient evidence of historical availability.

## Official evidence and short excerpts

All links were checked on the review date. Excerpts are intentionally short; interpretations below are ours.

1. [Open-Meteo Single Runs documentation, Data Sources](https://open-meteo.com/en/docs/single-runs-api#data-sources):

   > IFS Cycle 49R1 hindcasts

   The phrase describes coverage beginning in March 2024. The page does not identify which dates, if any, switch from retrospective production to original operational output, nor specify production dates for our two releases. Its generic description says individual runs are preserved; that does not resolve the narrower hindcast qualification.

2. [Open-Meteo announcement, 2026-05-15, comparison with historical APIs](https://openmeteo.substack.com/p/single-runs-api):

   > The complete forecast horizon of one specific run, unmodified.

   This supports preservation of a run's horizon, but “unmodified” does not establish when the underlying computation took place. The announcement describes historical coverage using cycles 49R1/50R1 and current operational processing, without a release-specific provenance attestation.

3. [ECMWF, Use of ERA5 reanalysis to initialise re-forecasts proves beneficial, Autumn 2019](https://www.ecmwf.int/en/newsletter/161/meteorology/use-era5-reanalysis-initialise-re-forecasts-proves-beneficial):

   > Re-forecasts are forecasts produced at the current time but starting from some point in the past.

   This distinguishes computation time from simulated initialization. The article concerns ECMWF re-forecast methodology; it does not classify the Open-Meteo responses. A re-forecast is not identical to a reanalysis time series, even when a reanalysis supplies initial conditions.

4. [ECMWF, How can I access Hindcast Data from ECMWF?, updated 2026-09-02](https://confluence.ecmwf.int/spaces/DAC/pages/600769480/How%2Bcan%2BI%2Baccess%2BHindcast%2BData%2Bfrom%2BECMWF):

   > The hindcasts are produced in the same way as the real-time forecasts but for past dates.

   ECMWF distinguishes reforecast dates, production dates and schedule/publication dates. An initialization date alone is therefore not enough. The page's ensemble hindcast workflow must not be assumed to be Open-Meteo's exact upstream workflow.

5. [ECMWF operational IFS cycle history](https://www.ecmwf.int/en/forecasts/documentation-and-support/changes-ecmwf-model):

   > Cycle 49r1

   > 12 November 2024

   The table places 49r1 into operation on that date and 50r1 on 12 May 2026. Both selected dates fall within 49r1's operational period. This is consistent with operational origin, but also with later reuse of the same cycle. It proves neither alternative. Conversely, March 2024 coverage predates 49r1's operational introduction, so the earliest part cannot simply be assumed to be contemporaneous operational 49r1 output; that inference does not classify January/February 2026.

## Consequences for the handoff

The sample CSV is suitable for interface development with explicit unresolved provenance. It is not certification of a leakage-free historical experiment. Keep `weather_publication_time_utc` and `historical_api_availability_time_utc` null. The simulated issue at initialization +12 hours remains an assumption about availability, not a production/publication timestamp and not a remedy for retrospective provenance. See [the source check](weather_source_check.md) for the delay rationale.

Evidence needed to close the question: a provider statement or upstream records identifying the original stream/experiment, model cycle, actual production and dissemination times for both exact initializations; confirmation whether any retrospective recomputation or reanalysis-based initialization replaced the original operational data. Later download/ingestion of an unchanged original forecast is distinct from later recomputation and is not itself evidence of leakage.

No provider or organizer was contacted. Archive expansion remains outside this task; organizer acceptance is a separate decision from scientific provenance verification.
