import { expect, test } from '@playwright/test'

test('Library shows independent source files and parsed text preview', async ({ page }) => {
  await page.route(url => url.pathname.startsWith('/model-settings'), route => route.fulfill({ json: {
    embedding_revision: 0, models: [], active_model: null, active_embedding: null,
    retrieval_available: false, retrieval_state: 'unavailable', indexed_files: 0,
    corpus_files: 0, busy: false, embedding_job: null,
  } }))
  await page.route('**/notes', route => route.fulfill({ json: { files: [], folders: [] } }))
  await page.route('**/source-files/folders', route => route.fulfill({ json: { folders: ['study'] } }))
  await page.route('**/source-files', route => route.fulfill({ json: [{
    id: '00000000-0000-4000-8000-000000000001', original_filename: 'lesson.txt',
    storage_path: '00000000-0000-4000-8000-000000000001', display_name: 'lesson.txt', folder: 'study',
    media_type: 'text/plain', size_bytes: 5, sha256: '0'.repeat(64), status: 'ready', error: null,
    created_at: '2026-10-16T00:00:00Z', updated_at: '2026-10-16T00:00:00Z',
  }] }))
  await page.route('**/source-files/00000000-0000-4000-8000-000000000001/preview', route => route.fulfill({ json: {
    fragments: [{ ordinal: 0, locator: 'paragraph 1', text: 'hello' }],
  } }))
  await page.goto('/library')
  await page.getByRole('button', { name: '文件', exact: true }).click()
  await expect(page.getByText('lesson.txt')).toBeVisible()
  await page.getByRole('button', { name: /lesson.txt/ }).click()
  await expect(page.locator('.source-library pre')).toContainText('hello')
})

test('chat composer uploads and waits for parsing readiness', async ({ page }) => {
  const id = '00000000-0000-4000-8000-000000000002'
  await page.route('**/model-settings', route => route.fulfill({ json: {
    embedding_revision: 0, models: [], active_model: null, active_embedding: null,
    retrieval_available: false, retrieval_state: 'unavailable', indexed_files: 0,
    corpus_files: 0, busy: false, embedding_job: null,
  } }))
  await page.route('**/conversations', route => route.fulfill({ json: [] }))
  await page.route('**/source-files', route => route.fulfill({ json: {
    id, original_filename: 'lesson.txt', storage_path: id, display_name: 'lesson.txt', folder: '',
    media_type: 'text/plain', size_bytes: 5, sha256: '0'.repeat(64),
    status: 'queued', error: null, created_at: '', updated_at: '',
  } }))
  await page.route(`**/source-files/${id}`, route => route.fulfill({ json: {
    id, original_filename: 'lesson.txt', storage_path: id, display_name: 'lesson.txt', folder: '',
    media_type: 'text/plain', size_bytes: 5, sha256: '0'.repeat(64),
    status: 'ready', error: null, created_at: '', updated_at: '',
  } }))
  await page.goto('/assistant')
  await page.locator('input[type="file"]').setInputFiles({
    name: 'lesson.txt', mimeType: 'text/plain', buffer: Buffer.from('hello'),
  })
  await expect(page.locator('.attachment-chip')).toContainText('lesson.txt')
  await expect(page.locator('.attachment-chip')).toContainText('ready')
  await page.getByRole('button', { name: '移除附件' }).click()
  await expect(page.locator('.attachment-chip')).toHaveCount(0)
})

test('Library accepts an arbitrary file as a stored record', async ({ page }) => {
  const id = '00000000-0000-4000-8000-000000000003'
  const record = { id, original_filename: 'archive.xyz', storage_path: id,
    display_name: 'archive.xyz', folder: '', media_type: 'application/octet-stream',
    size_bytes: 4, sha256: 'a'.repeat(64), status: 'stored', error: null,
    created_at: '', updated_at: '' }
  let files: typeof record[] = []
  await page.route(url => url.pathname.startsWith('/model-settings'), route => route.fulfill({ json: {
    embedding_revision: 0, models: [], active_model: null, active_embedding: null,
    retrieval_available: false, retrieval_state: 'unavailable', indexed_files: 0,
    corpus_files: 0, busy: false, embedding_job: null,
  } }))
  await page.route('**/notes', route => route.fulfill({ json: { files: [], folders: [] } }))
  await page.route('**/source-files/folders', route => route.fulfill({ json: { folders: [] } }))
  await page.route('**/source-files', route => {
    if (route.request().method() === 'POST') {
      files = [record]
      return route.fulfill({ status: 201, json: record })
    }
    return route.fulfill({ json: files })
  })
  await page.goto('/library')
  await page.getByRole('button', { name: '文件', exact: true }).click()
  await page.locator('.source-library input[type="file"]').setInputFiles({
    name: 'archive.xyz', mimeType: 'application/x-custom', buffer: Buffer.from('data'),
  })
  await expect(page.locator('.source-library .file-row')).toContainText('archive.xyz')
  await expect(page.locator('.source-library .file-row')).toContainText('stored')
})

test('Library continues a batch after one upload is rejected', async ({ page }) => {
  const id = '00000000-0000-4000-8000-000000000004'
  const record = { id, original_filename: 'good.xyz', storage_path: id,
    display_name: 'good.xyz', folder: '', media_type: 'application/octet-stream',
    size_bytes: 4, sha256: 'b'.repeat(64), status: 'stored', error: null,
    created_at: '', updated_at: '' }
  let uploaded = false
  let attempts = 0
  await page.route(url => url.pathname.startsWith('/model-settings'), route => route.fulfill({ json: {
    embedding_revision: 0, models: [], active_model: null, active_embedding: null,
    retrieval_available: false, retrieval_state: 'unavailable', indexed_files: 0,
    corpus_files: 0, busy: false, embedding_job: null,
  } }))
  await page.route('**/notes', route => route.fulfill({ json: { files: [], folders: [] } }))
  await page.route('**/source-files/folders', route => route.fulfill({ json: { folders: [] } }))
  await page.route('**/source-files', route => {
    if (route.request().method() === 'POST') {
      attempts += 1
      if (attempts === 1) return route.fulfill({ status: 400, json: { detail: '格式错误' } })
      uploaded = true
      return route.fulfill({ status: 201, json: record })
    }
    return route.fulfill({ json: uploaded ? [record] : [] })
  })
  await page.goto('/library')
  await page.getByRole('button', { name: '文件', exact: true }).click()
  await page.locator('.source-library input[type="file"]').setInputFiles([
    { name: 'bad.xyz', mimeType: 'application/x-custom', buffer: Buffer.from('bad') },
    { name: 'good.xyz', mimeType: 'application/x-custom', buffer: Buffer.from('good') },
  ])
  await expect(page.locator('.source-library .file-row')).toContainText('good.xyz')
  expect(attempts).toBe(2)
})

test('Enter cannot send a stored file as a chat attachment', async ({ page }) => {
  const id = '00000000-0000-4000-8000-000000000005'
  const record = { id, original_filename: 'data.xyz', storage_path: id,
    display_name: 'data.xyz', folder: '', media_type: 'application/octet-stream',
    size_bytes: 4, sha256: 'c'.repeat(64), status: 'stored', error: null,
    created_at: '', updated_at: '' }
  let chatRequests = 0
  await page.route(url => url.pathname.startsWith('/model-settings'), route => route.fulfill({ json: {
    embedding_revision: 0, models: [], active_model: null, active_embedding: null,
    retrieval_available: false, retrieval_state: 'unavailable', indexed_files: 0,
    corpus_files: 0, busy: false, embedding_job: null,
  } }))
  await page.route('**/conversations', route => route.fulfill({ json: [] }))
  await page.route('**/source-files', route => route.fulfill({ status: 201, json: record }))
  await page.route(`**/source-files/${id}`, route => route.fulfill({ json: record }))
  await page.route('**/chat', route => { chatRequests += 1; return route.fulfill({ status: 400, json: { detail: 'not ready' } }) })
  await page.goto('/assistant')
  await page.locator('.input-area input[type="file"]').setInputFiles({
    name: 'data.xyz', mimeType: 'application/x-custom', buffer: Buffer.from('data'),
  })
  await expect(page.locator('.attachment-chip')).toContainText('stored')
  await page.locator('.input-area textarea').fill('Explain')
  await page.locator('.input-area textarea').press('Enter')
  await page.waitForTimeout(250)
  expect(chatRequests).toBe(0)
})

test('chat attachment resumes status polling after a transient query failure', async ({ page }) => {
  const id = '00000000-0000-4000-8000-000000000006'
  const record = { id, original_filename: 'lesson.txt', storage_path: id,
    display_name: 'lesson.txt', folder: '', media_type: 'text/plain',
    size_bytes: 5, sha256: 'd'.repeat(64), status: 'queued', error: null,
    created_at: '', updated_at: '' }
  let queries = 0
  let parseRetries = 0
  await page.route(url => url.pathname.startsWith('/model-settings'), route => route.fulfill({ json: {
    embedding_revision: 0, models: [], active_model: null, active_embedding: null,
    retrieval_available: false, retrieval_state: 'unavailable', indexed_files: 0,
    corpus_files: 0, busy: false, embedding_job: null,
  } }))
  await page.route('**/conversations', route => route.fulfill({ json: [] }))
  await page.route('**/source-files', route => route.fulfill({ status: 201, json: record }))
  await page.route(`**/source-files/${id}`, route => {
    queries += 1
    if (queries === 1) return route.fulfill({ status: 503, json: { detail: 'temporary outage' } })
    return route.fulfill({ json: { ...record, status: 'ready' } })
  })
  await page.route(`**/source-files/${id}/retry`, route => {
    parseRetries += 1
    return route.fulfill({ status: 400, json: { detail: 'not failed' } })
  })
  await page.goto('/assistant')
  await page.locator('.input-area input[type="file"]').setInputFiles({
    name: 'lesson.txt', mimeType: 'text/plain', buffer: Buffer.from('hello'),
  })
  await expect(page.locator('.attachment-chip')).toContainText('temporary outage')
  await page.locator('.attachment-chip button').first().click()
  await expect(page.locator('.attachment-chip')).toContainText('ready')
  expect(parseRetries).toBe(0)
})
