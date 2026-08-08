const isTerminalStatus = (status) => status === 'completed' || status === 'stopped'

const allEnabledPlatformsCompleted = (runStatus) => {
  const twitterCompleted = runStatus.twitter_completed === true
  const redditCompleted = runStatus.reddit_completed === true
  const twitterEnabled = runStatus.twitter_actions_count > 0 || runStatus.twitter_running || twitterCompleted
  const redditEnabled = runStatus.reddit_actions_count > 0 || runStatus.reddit_running || redditCompleted

  if (!twitterEnabled && !redditEnabled) return false
  return (!twitterEnabled || twitterCompleted) && (!redditEnabled || redditCompleted)
}

export const getSimulationCompletionState = (runStatus = {}) => {
  if (runStatus.runner_status === 'idle') return 'not_started'
  if (runStatus.runner_status === 'failed') return 'failed'
  if (isTerminalStatus(runStatus.runner_status)) return 'report_ready'
  if (runStatus.runner_status === 'stopping') return 'finishing'
  if (allEnabledPlatformsCompleted(runStatus)) return 'awaiting_finish'
  return 'running'
}
