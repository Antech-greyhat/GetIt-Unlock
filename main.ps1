# Launch the shared CLI from PowerShell 5.1+ or PowerShell 7.
# Preserve the caller's directory, arguments, and the Python process exit code.

function Test-GetItPython {
    param([string]$Executable, [string[]]$PrefixArguments = @())
    try {
        & $Executable @PrefixArguments -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' *> $null
        return ($LASTEXITCODE -eq 0)
    }
    catch { return $false }
}

$getItPython = $null
$getItPrefix = @()
if ($env:GETIT_UNLOCK_PYTHON) {
    if (-not (Test-GetItPython $env:GETIT_UNLOCK_PYTHON)) {
        [Console]::Error.WriteLine('Error: GETIT_UNLOCK_PYTHON must point to a working Python 3.11+ executable.')
        exit 1
    }
    $getItPython = $env:GETIT_UNLOCK_PYTHON
}
else {
    $getItCandidates = @(
        (Join-Path $PSScriptRoot '.venv/Scripts/python.exe'),
        (Join-Path $PSScriptRoot '.venv/bin/python'),
        'python3', 'python'
    )
    foreach ($getItCandidate in $getItCandidates) {
        if (Test-GetItPython $getItCandidate) {
            $getItPython = $getItCandidate
            break
        }
    }
    if (-not $getItPython -and (Test-GetItPython 'py' @('-3'))) {
        $getItPython = 'py'
        $getItPrefix = @('-3')
    }
    if (-not $getItPython) {
        [Console]::Error.WriteLine('Error: Python 3.11 or newer is required by the PowerShell launcher.')
        [Console]::Error.WriteLine('Windows: install Python from https://www.python.org/downloads/windows/ and enable Add Python to PATH.')
        [Console]::Error.WriteLine('Select an existing interpreter with $env:GETIT_UNLOCK_PYTHON = "path/to/python.exe".')
        exit 1
    }
}

$getItOldBytecodeSetting = $env:PYTHONDONTWRITEBYTECODE
$getItExitCode = 1
try {
    $env:PYTHONDONTWRITEBYTECODE = '1'
    & $getItPython @getItPrefix -B (Join-Path $PSScriptRoot 'main.py') @args
    $getItExitCode = $LASTEXITCODE
}
finally {
    $env:PYTHONDONTWRITEBYTECODE = $getItOldBytecodeSetting
}
exit $getItExitCode
