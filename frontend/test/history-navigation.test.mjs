import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'

test('completed history runs open the simulation run/report flow', async () => {
  const source = await readFile(new URL('../src/components/HistoryDatabase.vue', import.meta.url), 'utf8')
  assert.match(source, /runner_status === 'completed'/)
  assert.match(source, /name: isCompleted \? 'SimulationRun' : 'Simulation'/)
})
