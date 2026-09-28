// @vitest-environment jsdom
// 需要 DOM：router.ts 在模块加载时就 createWebHistory()。
import { describe, expect, it } from 'vitest'

import { PAGE_ROUTES } from '@/router'
import { LEGACY_DOCUMENTS_PATH, NAV_ITEMS } from '@/shared/navigation'

describe('顶部导航与路由的一致性', () => {
  it('顺序固定为 Home → Assistant → Records → Library → Settings', () => {
    expect(NAV_ITEMS.map((item) => item.label)).toEqual([
      'Home',
      'Assistant',
      'Records',
      'Library',
      'Settings',
    ])
  })

  it('每个入口都有对应的页面路由，路径完全一致', () => {
    expect(PAGE_ROUTES.map((route) => route.path)).toEqual(
      NAV_ITEMS.map((item) => item.path),
    )
    expect(PAGE_ROUTES.map((route) => route.name)).toEqual(
      NAV_ITEMS.map((item) => item.name),
    )
  })

  it('兼容地址不占用导航入口', () => {
    expect(NAV_ITEMS.some((item) => item.path === LEGACY_DOCUMENTS_PATH)).toBe(false)
  })
})
