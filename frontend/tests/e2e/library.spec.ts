import { expect, test, type Page } from '@playwright/test'

/**
 * Library（原 Documents）的用户行为回归：目录树、编辑预览、CRUD、
 * 拖拽移动、索引补建与未保存保护。接口用固定响应拦截。
 */

const NOTES = {
  files: [
    { file_name: 'Go.md', folder: '', mtime: 1758998400, indexed: true },
    { file_name: 'Draft.md', folder: '', mtime: 1758998400, indexed: false },
    { file_name: 'bak/context.md', folder: 'bak', mtime: 1758998400, indexed: true },
  ],
  folders: ['bak'],
}

const BODIES: Record<string, string> = {
  'Go.md': '# Go\n\ngoroutine 是 Go 的并发单元。\n',
  'Draft.md': '# 草稿\n',
  'bak/context.md': '# 上下文\n',
}

const MODEL_SETTINGS = {
  revision: 7,
  chat_profiles: [],
  active_chat: null,
  active_embedding: null,
  retrieval_available: true,
  retrieval_problem: null,
  retrieval_state: 'ok',
  indexed_files: 2,
  corpus_files: 3,
  busy: false,
  embedding_job: null,
}

function readBody(request: { postData: () => string | null }): unknown {
  const raw = request.postData()
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return raw
  }
}

async function stubApi(page: Page) {
  const calls: Array<{ method: string; url: string; body: unknown }> = []
  const record = (route: {
    request: () => { method: () => string; url: () => string; postData: () => string | null }
  }) => {
    const request = route.request()
    calls.push({ method: request.method(), url: request.url(), body: readBody(request) })
  }

  await page.route(
    (url) => url.pathname === '/notes' && true,
    async (route) => {
      const request = route.request()
      record(route)
      if (request.method() === 'GET') return route.fulfill({ json: NOTES })
      // 新建笔记：返回补了 .md 的路径。
      const body = readBody(request) as { file_name: string } | null
      const name = body?.file_name ?? 'New.md'
      const fileName = name.endsWith('.md') ? name : `${name}.md`
      BODIES[fileName] = ''
      return route.fulfill({ json: { file_name: fileName, indexed: false } })
    },
  )

  await page.route(
    (url) => url.pathname.startsWith('/notes/'),
    async (route) => {
      const request = route.request()
      record(route)
      const path = decodeURIComponent(request.url().split('/notes/')[1].split('?')[0])

      if (path.endsWith('/index')) {
        return route.fulfill({ json: { file_name: path.replace(/\/index$/, ''), indexed: true } })
      }
      if (path === 'move') {
        return route.fulfill({
          json: { file_name: (readBody(request) as { to: string }).to, indexed: false },
        })
      }
      if (path === 'folders' || path.startsWith('folders')) {
        return route.fulfill({ json: { name: 'bak2', to_name: 'bak2', files: [] } })
      }
      if (request.method() === 'PUT') {
        const body = readBody(request) as { content: string }
        BODIES[path] = body.content
        return route.fulfill({ json: { file_name: path, indexed: true } })
      }
      if (request.method() === 'DELETE') {
        return route.fulfill({ json: { file_name: path, indexed: false } })
      }
      return route.fulfill({ json: { file_name: path, content: BODIES[path] ?? '' } })
    },
  )

  await page.route(
    (url) => url.pathname.startsWith('/model-settings'),
    (route) => route.fulfill({ json: MODEL_SETTINGS }),
  )
  await page.route(
    (url) => url.pathname.startsWith('/conversations'),
    (route) => {
      const url = route.request().url()
      if (/\/conversations$/.test(url)) return route.fulfill({ json: [] })
      if (url.includes('/messages')) return route.fulfill({ json: [] })
      return route.fulfill({ json: { id: 'c-1', title: 't', updated_at: '', pending_draft: null } })
    },
  )

  return calls
}

test('目录树显示一级目录、根笔记与索引状态', async ({ page }) => {
  await stubApi(page)
  await page.goto('/library')

  const tree = page.locator('[data-notes-tree]')
  await expect(tree.getByText('bak')).toBeVisible()
  await expect(tree.getByText('context.md')).toBeVisible()
  await expect(tree.getByText('Go.md')).toBeVisible()
  await expect(tree.getByText('Draft.md')).toBeVisible()

  // 已索引／未索引分别可见；未索引的那个可点。
  await expect(tree.locator('.index-chip.on')).toHaveCount(2)
  await expect(tree.locator('.index-chip.clickable')).toHaveCount(1)
})

test('点击未索引的笔记补建索引', async ({ page }) => {
  const calls = await stubApi(page)
  await page.goto('/library')

  await page.locator('.index-chip.clickable').click()
  await expect
    .poll(() => calls.some((call) => call.url.includes('/Draft.md/index')))
    .toBe(true)
})

test('打开笔记后编辑、保存，未保存标记随之出现与消失', async ({ page }) => {
  const calls = await stubApi(page)
  await page.goto('/library')

  await page.locator('.docs-row', { hasText: 'Go.md' }).click()
  const editor = page.getByRole('textbox', { name: 'Markdown 正文' })
  await expect(editor).toHaveValue(BODIES['Go.md'])
  // 预览同时渲染 Markdown。
  await expect(page.locator('.markdown-preview h1')).toHaveText('Go')

  await editor.fill('# Go\n\n改过一遍。\n')
  await expect(page.locator('.dirty-dot')).toBeVisible()

  await page.getByRole('button', { name: '保存' }).click()
  await expect(page.getByRole('status').filter({ hasText: '文件已保存' })).toBeVisible()
  await expect(page.locator('.dirty-dot')).toHaveCount(0)

  const save = calls.find((call) => call.method === 'PUT' && call.url.includes('/notes/Go.md'))
  expect(save?.body).toEqual({ content: '# Go\n\n改过一遍。\n' })
  await expect(page.locator('.markdown-preview')).toContainText('改过一遍。')
})

test('Ctrl+S 保存', async ({ page }) => {
  const calls = await stubApi(page)
  await page.goto('/library')

  await page.locator('.docs-row', { hasText: 'Go.md' }).click()
  await page.getByRole('textbox', { name: 'Markdown 正文' }).fill('# 快捷键保存\n')
  await page.keyboard.press('Control+s')

  await expect
    .poll(() =>
      calls.some(
        (call) =>
          call.method === 'PUT' && (call.body as { content?: string })?.content === '# 快捷键保存\n',
      ),
    )
    .toBe(true)
})

test('新建目录与新建笔记，笔记落在选中的目录下', async ({ page }) => {
  const calls = await stubApi(page)
  await page.goto('/library')

  await page.getByRole('button', { name: '＋ 新建文件夹' }).click()
  const folderPrompt = page.getByRole('dialog', { name: '新建文件夹' })
  await folderPrompt.locator('input').fill('bak2')
  await folderPrompt.getByRole('button', { name: '确认' }).click()
  await expect
    .poll(() => calls.some((call) => call.url.endsWith('/notes/folders')))
    .toBe(true)

  // 选中目录后再新建笔记，路径要带目录前缀。
  await page.locator('.docs-row', { hasText: 'bak' }).first().click()
  await page.getByRole('button', { name: '＋ 新建笔记' }).click()
  const notePrompt = page.getByRole('dialog', { name: '新建笔记' })
  await expect(notePrompt).toContainText('将创建在「bak」下')
  await notePrompt.locator('input').fill('新的.md')
  await notePrompt.getByRole('button', { name: '确认' }).click()
  await expect
    .poll(() => calls.some((call) => call.url.endsWith('/notes') && call.method === 'POST'))
    .toBe(true)
  const create = calls.find((call) => call.method === 'POST' && call.url.endsWith('/notes'))
  expect(create?.body).toEqual({ file_name: 'bak/新的.md' })
})

test('重命名走移动接口，JSON 键是 from/to', async ({ page }) => {
  const calls = await stubApi(page)
  await page.goto('/library')

  const row = page.locator('.docs-row', { hasText: 'Go.md' }).first()
  await row.getByRole('button', { name: '更多' }).click()
  await page.getByRole('menuitem', { name: '重命名' }).click()

  const prompt = page.getByRole('dialog', { name: '重命名笔记' })
  await prompt.locator('input').fill('Golang')
  await prompt.getByRole('button', { name: '确认' }).click()

  await expect
    .poll(() => calls.some((call) => call.url.endsWith('/notes/move')))
    .toBe(true)
  const move = calls.find((call) => call.url.endsWith('/notes/move'))
  /* 重命名不加后缀：服务端自己规范化，与旧页面一致。 */
  expect(move?.body).toEqual({ from: 'Go.md', to: 'Golang' })
})

test('删除笔记先确认，取消则不删', async ({ page }) => {
  const calls = await stubApi(page)
  await page.goto('/library')

  await page.locator('.docs-row', { hasText: 'Go.md' }).click()
  await page.getByRole('button', { name: '删除' }).click()
  const dialog = page.getByRole('dialog', { name: '删除笔记' })
  await expect(dialog).toContainText('确定删除「Go.md」？')
  await dialog.getByRole('button', { name: '取消' }).click()
  expect(calls.some((call) => call.method === 'DELETE')).toBe(false)

  await page.getByRole('button', { name: '删除' }).click()
  await page.getByRole('dialog', { name: '删除笔记' }).getByRole('button', { name: '确认' }).click()
  await expect.poll(() => calls.some((call) => call.method === 'DELETE')).toBe(true)
})

test('展开折叠目录', async ({ page }) => {
  await stubApi(page)
  await page.goto('/library')

  await expect(page.locator('.docs-row', { hasText: 'context.md' })).toBeVisible()
  await page.getByRole('button', { name: '展开或折叠' }).click()
  await expect(page.locator('.docs-row', { hasText: 'context.md' })).toHaveCount(0)
})

test('拖动笔记到目录上会先确认再移动', async ({ page }) => {
  const calls = await stubApi(page)
  await page.goto('/library')

  const source = page.locator('.docs-row', { hasText: 'Draft.md' }).first()
  const target = page.locator('[data-folder-group]').first()
  const sourceBox = (await source.boundingBox())!
  const targetBox = (await target.boundingBox())!

  // 用显式坐标分步移动：拖动阈值与落点判定都依赖真实的 mousemove 序列。
  await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2)
  await page.mouse.down()
  await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + targetBox.height / 2, {
    steps: 8,
  })
  await page.mouse.up()

  const dialog = page.getByRole('dialog', { name: '移动笔记' })
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText('将「Draft.md」移动到「bak」？')
  await dialog.getByRole('button', { name: '确认' }).click()

  await expect.poll(() => calls.some((call) => call.url.endsWith('/notes/move'))).toBe(true)
  const move = calls.find((call) => call.url.endsWith('/notes/move'))
  expect(move?.body).toEqual({ from: 'Draft.md', to: 'bak/Draft.md' })
})

test('未保存时离开 Library 会先问，取消则留在原处', async ({ page }) => {
  await stubApi(page)
  await page.goto('/library')
  await page.locator('.docs-row', { hasText: 'Go.md' }).click()
  await page.getByRole('textbox', { name: 'Markdown 正文' }).fill('改过但没保存')

  await page.getByRole('link', { name: '设置' }).click()
  const dialog = page.getByRole('dialog', { name: '未保存修改' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: '取消' }).click()

  await expect(page).toHaveURL(/\/library$/)
  await expect(page.getByRole('textbox', { name: 'Markdown 正文' })).toHaveValue('改过但没保存')

  // 换成另一个入口再试一次：确认放弃之后才真的走。
  await page.getByRole('link', { name: 'Records', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '未保存修改' })).toBeVisible()
  await page.getByRole('dialog', { name: '未保存修改' }).getByRole('button', { name: '确认' }).click()
  await expect(page).toHaveURL(/\/records$/)
})

test('旧地址 /documents 打开的就是 Library', async ({ page }) => {
  await stubApi(page)
  await page.goto('/documents')

  await expect(page).toHaveURL(/\/library$/)
  await expect(page.locator('[data-notes-tree]')).toBeVisible()
  await expect(page.getByRole('button', { name: '＋ 新建笔记' })).toBeVisible()
})
