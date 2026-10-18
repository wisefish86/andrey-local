param(
    [Parameter(Mandatory=$true)][string]$ObjectUrl
)
$ErrorActionPreference = 'Stop'
$diagnostic = Join-Path $env:TEMP 'Anytype-Export-error.txt'
Remove-Item -LiteralPath $diagnostic -ErrorAction SilentlyContinue
try {
$api = 'http://127.0.0.1:31009/v1'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class AnytypeCredential {
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
  public struct CREDENTIAL {
    public UInt32 Flags; public UInt32 Type;
    public string TargetName; public string Comment;
    public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
    public UInt32 CredentialBlobSize; public IntPtr CredentialBlob;
    public UInt32 Persist; public UInt32 AttributeCount;
    public IntPtr Attributes; public string TargetAlias; public string UserName;
  }
  [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  static extern bool CredRead(string target, int type, int flags, out IntPtr credential);
  [DllImport("advapi32.dll", SetLastError=true)]
  static extern void CredFree(IntPtr credential);
  public static string Read(string target) {
    IntPtr ptr;
    if (!CredRead(target, 1, 0, out ptr)) throw new Exception("Windows Credential Manager: Anytype-Local-API not found");
    try {
      var c = (CREDENTIAL)Marshal.PtrToStructure(ptr, typeof(CREDENTIAL));
      return Marshal.PtrToStringUni(c.CredentialBlob, (int)c.CredentialBlobSize / 2);
    } finally { CredFree(ptr); }
  }
}
'@
$uri = [uri]$ObjectUrl
if ($uri.Host -ne 'object.any.coop') { throw 'Not an Anytype object URL' }
$objectId = $uri.AbsolutePath.Trim('/')
$spaceId = [regex]::Match($uri.Query, '(?:^|[?&])spaceId=([^&]+)').Groups[1].Value
$spaceId = [uri]::UnescapeDataString($spaceId)
if (!$objectId -or !$spaceId) { throw 'Object ID or space ID missing' }
$key = [AnytypeCredential]::Read('Anytype-Local-API')
if ([string]::IsNullOrWhiteSpace($key)) { throw 'Empty Anytype API key' }
$headers = @{ Authorization = "Bearer $key"; 'Anytype-Version' = '2025-11-08' }
$props = Invoke-RestMethod -Uri "$api/spaces/$spaceId/properties" -Headers $headers -Method Get
$items = @($props.data)
if (!$items.Count) { $items = @($props.properties) }
$match = @($items | Where-Object { $_.name -eq ([string]([char]0x0412) + ' Notion') -and ($_.format -eq 'checkbox' -or $_.type -eq 'checkbox' -or $_.format -eq 'Checkbox') })
if ($match.Count -ne 1) { throw "Expected one checkbox property ([string]([char]0x0412) + ' Notion'), found $($match.Count)" }
$propertyKey = $match[0].key
if (!$propertyKey) { throw 'Property key missing' }
$payload = @{ properties = @(@{ key = $propertyKey; checkbox = $true }) } | ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri "$api/spaces/$spaceId/objects/$objectId" -Headers $headers -Method Patch -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($payload)) | Out-Null
$check = Invoke-RestMethod -Uri "$api/spaces/$spaceId/objects/$objectId" -Headers $headers -Method Get
$values = @($check.object.properties)
if (!$values.Count) { $values = @($check.data.properties) }
if (!(@($values | Where-Object { $_.key -eq $propertyKey -and $_.checkbox -eq $true }).Count)) {
  throw 'PATCH sent but checkbox verification failed'
}
Write-Output 'Checkbox verified'

} catch {
  $message = $_.Exception.Message
  if ($key) { $message = $message -replace [regex]::Escape($key), '[REDACTED]' }
  [System.IO.File]::WriteAllText($diagnostic, $message, [System.Text.Encoding]::UTF8)
  exit 1
}
