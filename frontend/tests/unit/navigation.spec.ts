// @vitest-environment jsdom
// 需要 DOM：router.ts 在模块加载时就 createWebHistory()。
import { describe, expect, it } from 'vitest'

import { PAGE_ROUTES, router } from '@/router'
import {
  HOME_SHORTCUTS,
  LEGACY_DOCUMENTS_PATH,
  PRIMARY_NAV_ITEMS,
  SETTINGS_ENTRY,
} from '@/shared/navigation'

describe('顶部导航与路由的一致性', () => {
  it('主导航顺序固定为 Home → Assistant → Records → Library', () => {
    expect(PRIMARY_NAV_ITEMS.map((item) => item.label)).toEqual([
      'Home',
      'Assistant',
      'Records',
      'Library',
    ])
  })

  it('设置是独立入口，不进主导航', () => {
    expect(SETTINGS_ENTRY).toEqual({ name: 'settings', label: 'Settings', path: '/settings' })
    expect(PRIMARY_NAV_ITEMS.some((item) => item.name === 'settings')).toBe(false)
  })

  it('四个主导航加设置入口覆盖全部五个页面路由，路径完全一致', () => {
    const entries = [...PRIMARY_NAV_ITEMS, SETTINGS_ENTRY]
    expect(PAGE_ROUTES.map((route) => route.path)).toEqual(entries.map((item) => item.path))
    expect(PAGE_ROUTES.map((route) => route.name)).toEqual(entries.map((item) => item.name))
  })

  it('Home 快捷入口仍是四项，且含设置', () => {
    expect(HOME_SHORTCUTS.map((item) => item.label)).toEqual([
      'Assistant',
      'Records',
      'Library',
      'Settings',
    ])
    expect(HOME_SHORTCUTS.some((item) => item.path === SETTINGS_ENTRY.path)).toBe(true)
    expect(HOME_SHORTCUTS.some((item) => item.name === 'home')).toBe(false)
  })

  it('兼容地址不占用导航入口，且重定向仍然存在', () => {
    const entries = [...PRIMARY_NAV_ITEMS, SETTINGS_ENTRY]
    expect(entries.some((item) => item.path === LEGACY_DOCUMENTS_PATH)).toBe(false)
    expect(
      router.options.routes.some(
        (route) => route.path === LEGACY_DOCUMENTS_PATH && route.redirect === '/library',
      ),
    ).toBe(true)
  })
})
