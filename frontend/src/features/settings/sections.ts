/**
 * 设置分类的静态定义。七个 ID 与标题来自产品设计 §3，顺序即展示顺序。
 *
 * 只有 `available` 的分类会进入界面与导航；`reserved` 只是后续实现的锚点，
 * 现在不渲染空菜单、假数值或不可用的保存按钮。这里不引入通用配置 schema，
 * 也不做远程注册——分类是编译期常量。
 */
export type SettingsSectionId =
  | 'models'
  | 'retrieval'
  | 'general'
  | 'editor'
  | 'data'
  | 'recording'
  | 'organization'

export type SettingsSectionStatus = 'available' | 'reserved'

export interface SettingsSection {
  id: SettingsSectionId
  title: string
  status: SettingsSectionStatus
}

/** 首轮已实现的两个分类。 */
export type AvailableSettingsSectionId = 'models' | 'retrieval'

export const SETTINGS_SECTIONS: readonly SettingsSection[] = [
  { id: 'models', title: '模型与连接', status: 'available' },
  { id: 'retrieval', title: '检索与索引', status: 'available' },
  { id: 'general', title: '通用与外观', status: 'reserved' },
  { id: 'editor', title: '编辑与阅读', status: 'reserved' },
  { id: 'data', title: '数据与存储', status: 'reserved' },
  { id: 'recording', title: '记录与采集', status: 'reserved' },
  { id: 'organization', title: '整理偏好', status: 'reserved' },
]

export const DEFAULT_SETTINGS_SECTION: AvailableSettingsSectionId = 'models'

export const AVAILABLE_SETTINGS_SECTIONS: readonly SettingsSection[] =
  SETTINGS_SECTIONS.filter((section) => section.status === 'available')

const AVAILABLE_IDS = new Set<string>(AVAILABLE_SETTINGS_SECTIONS.map((section) => section.id))

/**
 * 解析 `?section=` 的值。未提供、未知值、未开放分类与数组一律回默认分类，
 * 只有已开放分类的字符串才被接受，所以 URL 不会把界面带进不存在的分类。
 */
export function resolveSettingsSection(value: unknown): AvailableSettingsSectionId {
  if (typeof value !== 'string' || !AVAILABLE_IDS.has(value)) return DEFAULT_SETTINGS_SECTION
  return value as AvailableSettingsSectionId
}
