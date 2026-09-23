param(
    [string]$RawDirectory = (Join-Path $PSScriptRoot '../data/raw'),
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '../data/processed'),
    [double]$HighWindThreshold = 5.0
)
$ErrorActionPreference = 'Stop'
$culture = [Globalization.CultureInfo]::InvariantCulture
if ($HighWindThreshold -le 0) { throw 'HighWindThreshold must be positive.' }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

# These exact headers were inspected in the original UTF-8 CSVs.
$mapping = [ordered]@{
    timestamp = 'Статистическое время'
    normalized_power = 'Нормализованная активная мощность'
    wind_speed = 'Средняя скорость ветра(m/s)'
    temperature = 'Средняя температура окружающей среды(°C)'
}
function Is-Missing([string]$value) {
    return [string]::IsNullOrWhiteSpace($value) -or $value.Trim() -match '^(NA|N/A|NaN|null|None)$'
}
function Format-Number($value) {
    if ($null -eq $value) { return '' }
    return $value.ToString('G17', $culture)
}
function Get-Stats($values) {
    if ($values.Count -eq 0) { return [ordered]@{ count = 0; min = $null; max = $null; mean = $null } }
    $stats = $values | Measure-Object -Minimum -Maximum -Average
    return [ordered]@{ count = $values.Count; min = $stats.Minimum; max = $stats.Maximum; mean = $stats.Average }
}
$reports = [ordered]@{}
foreach ($turbine in 1, 2) {
    $candidates = @("turbine_$turbine.csv", "turbine $turbine.csv") | ForEach-Object { Join-Path $RawDirectory $_ } | Where-Object { Test-Path -LiteralPath $_ }
    if (@($candidates).Count -ne 1) { throw "Expected exactly one input file for turbine $turbine (space or underscore filename)." }
    $source = @($candidates)[0]
    $hashBefore = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    $rows = @(Import-Csv -LiteralPath $source -Encoding UTF8)
    if ($rows.Count -eq 0) { throw "Empty CSV: $source" }
    $headers = @($rows[0].PSObject.Properties.Name)
    foreach ($column in $mapping.Values) {
        if ($headers -cnotcontains $column) { throw "Missing required header: $column" }
    }
    $missing = [ordered]@{}
    foreach ($header in $headers) { $missing[$header] = 0 }
    $invalidNumeric = [ordered]@{}
    $series = @{}
    foreach ($field in 'normalized_power', 'wind_speed', 'temperature') {
        $series[$field] = [Collections.Generic.List[double]]::new()
        $invalidNumeric[$field] = 0
    }
    $times = @{}
    $hours = @{}
    $invalidTimestamps = 0; $zero = 0; $zeroNonzero = 0; $zeroHigh = 0; $outOfOrder = 0; $offGrid = 0
    $previous = $null
    foreach ($row in $rows) {
        foreach ($header in $headers) { if (Is-Missing $row.$header) { $missing[$header]++ } }
        $numbers = @{}
        foreach ($field in 'normalized_power', 'wind_speed', 'temperature') {
            $raw = $row.($mapping[$field])
            $number = 0.0
            if (Is-Missing $raw) { $numbers[$field] = $null }
            elseif ([double]::TryParse($raw, [Globalization.NumberStyles]::Float, $culture, [ref]$number) -and -not [double]::IsNaN($number) -and -not [double]::IsInfinity($number)) {
                $numbers[$field] = $number
                $series[$field].Add($number)
            } else { $invalidNumeric[$field]++; $numbers[$field] = $null }
        }
        if ($null -ne $numbers.normalized_power -and $numbers.normalized_power -eq 0) {
            $zero++
            if ($null -ne $numbers.wind_speed -and $numbers.wind_speed -ne 0) { $zeroNonzero++ }
            if ($null -ne $numbers.wind_speed -and $numbers.wind_speed -ge $HighWindThreshold) { $zeroHigh++ }
        }
        $timestamp = [datetime]::MinValue
        if (-not [datetime]::TryParseExact($row.($mapping.timestamp), 'yyyy-MM-dd H:mm:ss', $culture, [Globalization.DateTimeStyles]::None, [ref]$timestamp)) {
            $invalidTimestamps++; continue
        }
        if ($null -ne $previous -and $timestamp -lt $previous) { $outOfOrder++ }
        $previous = $timestamp
        if ($timestamp.Minute % 10 -ne 0 -or $timestamp.Second -ne 0) { $offGrid++ }
        $key = $timestamp.Ticks
        if (-not $times.ContainsKey($key)) { $times[$key] = 0 }
        $times[$key]++
        $hour = $timestamp.Date.AddHours($timestamp.Hour)
        if (-not $hours.ContainsKey($hour.Ticks)) {
            $hours[$hour.Ticks] = @{ count = 0; normalized_power = [Collections.Generic.List[double]]::new(); wind_speed = [Collections.Generic.List[double]]::new(); temperature = [Collections.Generic.List[double]]::new() }
        }
        $bucket = $hours[$hour.Ticks]
        $bucket.count++
        foreach ($field in 'normalized_power', 'wind_speed', 'temperature') {
            if ($null -ne $numbers[$field]) { $bucket[$field].Add($numbers[$field]) }
        }
    }
    if ($times.Count -eq 0) { throw "No valid timestamps: $source" }
    $sorted = @($times.Keys | Sort-Object)
    $intervals = @{}
    $gaps = [Collections.Generic.List[object]]::new()
    $duplicateExtra = 0; $duplicateGroups = 0
    foreach ($key in $sorted) {
        if ($times[$key] -gt 1) { $duplicateGroups++; $duplicateExtra += $times[$key] - 1 }
    }
    if ($duplicateExtra -gt 0) { $intervals['0'] = $duplicateExtra }
    for ($i = 1; $i -lt $sorted.Count; $i++) {
        $minutes = ($sorted[$i] - $sorted[$i - 1]) / [double][TimeSpan]::TicksPerMinute
        $label = Format-Number $minutes
        if (-not $intervals.ContainsKey($label)) { $intervals[$label] = 0 }
        $intervals[$label]++
        if ($minutes -gt 10) {
            $gaps.Add([pscustomobject]@{
                previous_timestamp = ([datetime]$sorted[$i - 1]).ToString('yyyy-MM-dd HH:mm:ss')
                next_timestamp = ([datetime]$sorted[$i]).ToString('yyyy-MM-dd HH:mm:ss')
                interval_minutes = $minutes
                missing_10_minute_slots = [math]::Max(0, [math]::Ceiling($minutes / 10) - 1)
            })
        }
    }
    $first = [datetime]$sorted[0]; $last = [datetime]$sorted[-1]
    $hourly = [Collections.Generic.List[object]]::new()
    $incomplete = 0; $emptyHours = 0
    for ($hour = $first.Date.AddHours($first.Hour); $hour -le $last; $hour = $hour.AddHours(1)) {
        $bucket = $hours[$hour.Ticks]
        $count = 0
        $means = @{}
        foreach ($field in 'normalized_power', 'wind_speed', 'temperature') { $means[$field] = '' }
        if ($null -ne $bucket) {
            $count = $bucket.count
            foreach ($field in 'normalized_power', 'wind_speed', 'temperature') {
                $means[$field] = Format-Number (Get-Stats $bucket[$field]).mean
            }
        }
        if ($count -ne 6) { $incomplete++ }
        if ($count -eq 0) { $emptyHours++ }
        $hourly.Add([pscustomobject][ordered]@{
            timestamp = $hour.ToString('yyyy-MM-dd HH:mm:ss')
            mean_normalized_power = $means.normalized_power
            mean_measured_wind_speed = $means.wind_speed
            mean_measured_temperature = $means.temperature
            observations_count = $count
            is_complete_hour = ($count -eq 6).ToString().ToLowerInvariant()
        })
    }
    $target = Join-Path $OutputDirectory "turbine_${turbine}_hourly.csv"
    $hourly | Export-Csv -LiteralPath $target -NoTypeInformation -Encoding UTF8
    $verified = @(Import-Csv -LiteralPath $target -Encoding UTF8)
    if ($verified.Count -ne $hourly.Count -or ($verified | Measure-Object observations_count -Sum).Sum -ne ($rows.Count - $invalidTimestamps)) { throw 'Hourly row/count verification failed.' }
    foreach ($record in $verified) {
        if ($record.is_complete_hour -cne (([int]$record.observations_count -eq 6).ToString().ToLowerInvariant())) { throw 'Completeness verification failed.' }
    }
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $hashBefore) { throw 'Raw file changed during processing.' }
    $reports["turbine_$turbine"] = [ordered]@{
        source_file = [IO.Path]::GetFileName($source); source_sha256 = $hashBefore
        rows = $rows.Count; columns = $headers; column_mapping = $mapping
        first_timestamp = $first.ToString('yyyy-MM-dd HH:mm:ss'); last_timestamp = $last.ToString('yyyy-MM-dd HH:mm:ss')
        duplicate_timestamp_groups = $duplicateGroups; duplicate_timestamp_extra_rows = $duplicateExtra
        missing_values = $missing; invalid_timestamps = $invalidTimestamps; invalid_numeric_values = $invalidNumeric
        out_of_order_transitions = $outOfOrder; off_10_minute_grid_rows = $offGrid
        sorted_timestamp_interval_minutes_distribution = $intervals
        gap_count = $gaps.Count; gaps = @($gaps.ToArray())
        normalized_power = Get-Stats $series.normalized_power
        wind_speed = Get-Stats $series.wind_speed
        temperature = Get-Stats $series.temperature
        zero_power_count = $zero; zero_power_percent_all_rows = 100.0 * $zero / $rows.Count
        zero_power_nonzero_wind_count = $zeroNonzero; zero_power_high_wind_count = $zeroHigh
        high_wind_threshold_m_s = $HighWindThreshold
        hourly_columns = @($hourly[0].PSObject.Properties.Name)
        hourly_rows = $hourly.Count; incomplete_hours = $incomplete; empty_hours = $emptyHours
        observed_incomplete_hours = $incomplete - $emptyHours
        verification = 'Passed: exported row counts, observation conservation, completeness flags, and unchanged raw SHA256.'
    }
    Write-Output "Turbine ${turbine}: $($rows.Count) observations, $($hourly.Count) hourly rows, $incomplete incomplete hours ($emptyHours empty)."
}
$reports | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'data_quality_report.json') -Encoding UTF8
