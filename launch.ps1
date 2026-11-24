$ErrorActionPreference = 'Stop'
$taskArguments = @($args)
$taskRoot = $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskPrefix = @()
$taskLocalFile = Join-Path $taskRoot 'runtime.local.json'
$taskLocal = $null
if (Test-Path -LiteralPath $taskLocalFile) {
    $taskLocal = Get-Content -LiteralPath $taskLocalFile -Raw -Encoding UTF8 | ConvertFrom-Json
}
if (-not (Test-Path -LiteralPath $taskPython)) {
    if ($taskLocal -and (Test-Path -LiteralPath $taskLocal.python)) {
        $taskPython = $taskLocal.python
    } elseif (Get-Command py.exe -ErrorAction SilentlyContinue) {
        $taskPython = (Get-Command py.exe).Source
        $taskPrefix = @('-3')
    } else {
        $taskPython = (Get-Command python.exe).Source
    }
}
if (-not $env:TASK1_NODE -and -not (Get-Command node.exe -ErrorAction SilentlyContinue)) {
    if ($taskLocal -and (Test-Path -LiteralPath $taskLocal.node)) {
        $env:TASK1_NODE = $taskLocal.node
    }
}
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
& $taskPython @taskPrefix -c "import numpy, scipy, matplotlib, docx"
if ($LASTEXITCODE -ne 0) {
    throw 'Python dependencies are missing. Follow the setup commands in README.md, then reopen run.cmd.'
}
& $taskPython @taskPrefix (Join-Path $taskRoot 'prepare_backends.py')
if ($LASTEXITCODE -ne 0) {
    throw 'Backend setup failed. See the setup and offline options in README.md.'
}
if ($taskArguments.Count -eq 0) {
    $taskEntry = Join-Path $taskRoot 'local_web.py'
    if ($env:TASK1_NO_OPEN -eq '1') { $taskArguments = @('--no-browser') }
} else {
    $taskEntry = Join-Path $taskRoot 'inspect_room.py'
    if ($env:TASK1_NO_OPEN -ne '1') { $taskArguments += '--open-word' }
}
& $taskPython @taskPrefix $taskEntry @taskArguments
exit $LASTEXITCODE
