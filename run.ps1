# run.ps1 — Launch Claude Code inside Docker for this project
# Usage: .\run.ps1

$projectPath = $PSScriptRoot
$claudeConfigPath = "$env:USERPROFILE\.claude"

docker run -it --rm `
    -v "${projectPath}:/workspace" `
    -v "${claudeConfigPath}:/home/claude-user/.claude" `
    --env-file "$projectPath\.env" `
    --name job-tracker-claude `
    job-tracker-claude `
    claude
