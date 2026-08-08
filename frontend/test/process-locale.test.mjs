import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const repoRoot = new URL('../..', import.meta.url)
const readRepoFile = (path) => readFile(new URL(path, repoRoot), 'utf8')

const flattenKeys = (value, prefix = '') => {
  if (Array.isArray(value) || typeof value !== 'object' || value === null) {
    return [prefix]
  }

  return Object.entries(value).flatMap(([key, child]) =>
    flattenKeys(child, prefix ? `${prefix}.${key}` : key)
  )
}

test('Thai locale provides every English interface message', async () => {
  const [english, thai] = await Promise.all([
    readRepoFile('locales/en.json').then(JSON.parse),
    readRepoFile('locales/th.json').then(JSON.parse)
  ])

  assert.deepEqual(flattenKeys(thai).sort(), flattenKeys(english).sort())
})

test('legacy process route has no Chinese interface copy', async () => {
  const processView = await readRepoFile('frontend/src/views/Process.vue')
  const renderedSource = processView
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/.*$/gm, '')

  assert.doesNotMatch(renderedSource, /[\u4E00-\u9FFF]/)
})
