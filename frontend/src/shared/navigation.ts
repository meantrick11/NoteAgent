/**
 * 顶部导航的唯一来源：顺序固定，页面与 Home 快捷入口都从这里取。
 * 顺序是 2026-09-28 用户确定的产品约束，不要按字母或路由表顺序重排。
 */
export interface NavItem {
  name: string
  label: string
  path: string
}

export const NAV_ITEMS: readonly NavItem[] = [
  { name: 'home', label: 'Home', path: '/' },
  { name: 'assistant', label: 'Assistant', path: '/assistant' },
  { name: 'records', label: 'Records', path: '/records' },
  { name: 'library', label: 'Library', path: '/library' },
  { name: 'settings', label: 'Settings', path: '/settings' },
]

/** 旧地址兼容：/documents 不再有独立实现，统一落到 Library。 */
export const LEGACY_DOCUMENTS_PATH = '/documents'
