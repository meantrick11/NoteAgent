/**
 * 导航定义的唯一来源，分三层：
 *   - PRIMARY_NAV_ITEMS：顶部主导航，四项工作入口；
 *   - SETTINGS_ENTRY：右上角齿轮，单独指向设置页；
 *   - HOME_SHORTCUTS：Home 的快捷入口，等于四项减去 Home 再加设置。
 * 顺序是 2026-09-28 用户确定的产品约束，不要按字母或路由表顺序重排。
 */
export interface NavItem {
  name: string
  label: string
  path: string
}

export const PRIMARY_NAV_ITEMS: readonly NavItem[] = [
  { name: 'home', label: 'Home', path: '/' },
  { name: 'assistant', label: 'Assistant', path: '/assistant' },
  { name: 'records', label: 'Records', path: '/records' },
  { name: 'library', label: 'Library', path: '/library' },
]

/** 设置不再是顶部文字项，而是右上角齿轮；路由仍是 /settings。 */
export const SETTINGS_ENTRY: NavItem = {
  name: 'settings',
  label: 'Settings',
  path: '/settings',
}

/** Home 的四个快捷入口：四个工作入口去掉 Home 自己，再补上设置。 */
export const HOME_SHORTCUTS: readonly NavItem[] = [
  ...PRIMARY_NAV_ITEMS.filter((item) => item.name !== 'home'),
  SETTINGS_ENTRY,
]

/** 旧地址兼容：/documents 不再有独立实现，统一落到 Library。 */
export const LEGACY_DOCUMENTS_PATH = '/documents'
