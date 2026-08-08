import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'

const component = new URL('../src/components/Step3Simulation.vue', import.meta.url)
const runView = new URL('../src/views/SimulationRunView.vue', import.meta.url)

test('Step 3 switches from a split timeline to a single-column mobile monitor', async () => {
  const source = await readFile(component, 'utf8')

  assert.match(source, /@media \(max-width: 767px\)/)
  assert.match(source, /\.control-bar\s*\{[\s\S]*flex-direction: column/)
  assert.match(source, /\.timeline-axis\s*\{[\s\S]*display: none/)
  assert.match(source, /\.timeline-item\.twitter,[\s\S]*\.timeline-item\.reddit\s*\{[\s\S]*padding: 0/)
  assert.match(source, /\.timeline-card\s*\{[\s\S]*width: 100%/)
})

test('SimulationRunView gives the workbench a full-width mobile panel', async () => {
  const source = await readFile(runView, 'utf8')

  assert.match(source, /@media \(max-width: 767px\)/)
  assert.match(source, /\.panel-wrapper\.left,[\s\S]*\.panel-wrapper\.right\s*\{[\s\S]*width: 100%/)
  assert.match(source, /\.header-right\s*\{[\s\S]*flex-wrap: wrap/)
})
