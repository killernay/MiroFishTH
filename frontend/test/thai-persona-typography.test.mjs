import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const repoRoot = new URL('../..', import.meta.url)

test('Thai persona cards use a Thai-capable font with space for combining marks', async () => {
  const [component, indexHtml] = await Promise.all([
    readFile(new URL('frontend/src/components/Step2EnvSetup.vue', repoRoot), 'utf8'),
    readFile(new URL('frontend/index.html', repoRoot), 'utf8')
  ])

  const representativePersona = {
    name: 'ผู้เรียนที่มีวินัย',
    profession: 'อาจารย์ผู้เชี่ยวชาญ',
    bio: 'มีความตั้งใจในการศึกษาธรรมะอย่างลึกซึ้ง'
  }

  for (const value of Object.values(representativePersona)) {
    assert.match(value, /[่้ิี]/)
  }

  assert.match(component, /html\[lang=['"]th['"]\][\s\S]*\.profile-card/)
  assert.match(component, /font-family:\s*'Noto Sans Thai'/)
  assert.match(indexHtml, /family=Noto\+Sans\+Thai/)
  assert.match(component, /\.profile-realname[\s\S]*line-height:\s*1\.6/)
  assert.match(component, /\.profile-profession[\s\S]*line-height:\s*1\.6/)
  assert.match(component, /html\[lang=['"]th['"]\][\s\S]*\.profile-bio[\s\S]*font-family:/)
  assert.match(component, /Tahoma, ['"]Leelawadee UI['"], system-ui/)
})
