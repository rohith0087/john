param([Parameter(Mandatory=$true)][string]$Url)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 18 -MaximumRedirection 0 -UserAgent 'IDNWatch/0.2 (local research prototype)'
    if ($response.RawContentLength -gt 2500000) { throw 'Source exceeds the 2.5 MB collection limit.' }
    $sourceBytes = $response.RawContentStream.ToArray()
    try { $sourceHtml = [System.Text.UTF8Encoding]::new($false,$true).GetString($sourceBytes) }
    catch { $sourceHtml = [System.Text.Encoding]::GetEncoding(1252).GetString($sourceBytes) }
    @{status=[int]$response.StatusCode;url=$Url;html=$sourceHtml} | ConvertTo-Json -Compress -Depth 3
} catch {
    @{error=$_.Exception.Message;url=$Url} | ConvertTo-Json -Compress
    exit 1
}
