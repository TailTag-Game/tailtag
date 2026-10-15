# Dot-source this in a step so the rest of the step runs without POSIX tools.
# It removes Git Bash directories from PATH and fails if any sh or bash remains.
# System32\bash.exe is the WSL launcher that ships with Windows; nothing calls it.
$env:PATH = ($env:PATH -split ';' | Where-Object {
    $_ -and $_ -notmatch '\\Git\\(usr\\)?bin\\?$' -and $_ -notmatch '\\Git\\mingw64\\bin\\?$'
  }) -join ';'
$posix = Get-Command sh, bash -All -ErrorAction SilentlyContinue |
  Where-Object { $_.Source -ne "$env:SystemRoot\system32\bash.exe" }
if ($posix) {
  $posix | Format-Table Name, Source -AutoSize | Out-String | Write-Host
  throw 'sh or bash is on PATH; this would not be a native Windows run'
}
