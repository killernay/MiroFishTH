import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'

import { getSimulationCompletionState } from '../src/utils/simulationCompletion.js'

const repoRoot = new URL('../..', import.meta.url)

test('shows an explicit finish-required state after every enabled platform completes', () => {
  assert.equal(
    getSimulationCompletionState({
      runner_status: 'running',
      twitter_completed: true,
      reddit_completed: true,
      twitter_actions_count: 224,
      reddit_actions_count: 180,
      total_rounds: 168
    }),
    'awaiting_finish'
  )
})

test('keeps a run in progress until every enabled platform completes', () => {
  assert.equal(
    getSimulationCompletionState({
      runner_status: 'running',
      twitter_completed: true,
      reddit_completed: false,
      twitter_actions_count: 224,
      reddit_actions_count: 180
    }),
    'running'
  )
})

test('unlocks report generation only after a terminal runner status', () => {
  assert.equal(
    getSimulationCompletionState({ runner_status: 'completed' }),
    'report_ready'
  )
})

test('shows finalization while an explicit finish request is closing the environment', () => {
  assert.equal(
    getSimulationCompletionState({
      runner_status: 'stopping',
      twitter_completed: true,
      reddit_completed: true
    }),
    'finishing'
  )
})

test('requires an explicit confirmation before closing the interview environment', async () => {
  const component = await readFile(
    new URL('frontend/src/components/Step3Simulation.vue', repoRoot),
    'utf8'
  )

  assert.match(component, /window\.confirm\(t\('step3\.confirmFinishSimulation'\)\)/)
})
