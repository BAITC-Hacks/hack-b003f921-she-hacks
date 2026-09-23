# Questions for the organizers

Prepared for Kamila / User 2. Not sent.

1. Which timezone applies to SCADA timestamps, and which timezone defines February 1 through February 28, 2026 in the test period? Please confirm both separately, preferably with an IANA identifier or explicit UTC offset.
2. Does each SCADA timestamp mark the start or end of its 10-minute interval? How should those intervals be assigned to an hourly production target and labelled at the February boundaries?
3. During the simulated February evaluation, may the system access actual measured power as it becomes available? If yes, with what publication/arrival delay, and may it be used for lag features or model updates? Or are all February measurements scoring-only holdout data?
4. Is Open-Meteo Single Runs ECMWF IFS acceptable if the provider's `49R1 hindcasts` wording leaves original operational versus retrospective origin unresolved? If not, what provenance evidence or alternative archive is required, and is a documented 12-hour availability assumption acceptable when historical publication times are unavailable?

Context for question 4: [official excerpts and unresolved finding](weather_archive_provenance.md). The checks cover only initializations 2026-01-31 00:00 UTC and 2026-02-14 00:00 UTC. HTTP 200 and a `run` parameter are not proof of historical publication.
