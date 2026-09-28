import { describe, expect, it } from 'vitest'

import {
  AVAILABLE_SETTINGS_SECTIONS,
  SETTINGS_SECTIONS,
  resolveSettingsSection,
} from '@/features/settings/sections'

describe('设置分类合同', () => {
  it('只开放已有能力', () => {
    expect(AVAILABLE_SETTINGS_SECTIONS.map((x) => x.id)).toEqual(['models', 'retrieval'])
  })

  it('未知及未开放分类回到默认', () => {
    for (const value of [undefined, null, '', 'general', 'account', ['retrieval']]) {
      expect(resolveSettingsSection(value)).toBe('models')
    }
    expect(resolveSettingsSection('retrieval')).toBe('retrieval')
  })

  it('七个分类的 ID 与标题固定，其余标记为预留', () => {
    expect(SETTINGS_SECTIONS.map((x) => x.id)).toEqual([
      'models',
      'retrieval',
      'general',
      'editor',
      'data',
      'recording',
      'organization',
    ])
    expect(SETTINGS_SECTIONS.map((x) => x.title)).toEqual([
      '模型与连接',
      '检索与索引',
      '通用与外观',
      '编辑与阅读',
      '数据与存储',
      '记录与采集',
      '整理偏好',
    ])
    expect(
      SETTINGS_SECTIONS.filter((x) => x.status === 'reserved').map((x) => x.id),
    ).toEqual(['general', 'editor', 'data', 'recording', 'organization'])
  })

  it('预留分类不能通过 URL 进入', () => {
    for (const id of ['general', 'editor', 'data', 'recording', 'organization']) {
      expect(resolveSettingsSection(id)).toBe('models')
    }
  })
})
