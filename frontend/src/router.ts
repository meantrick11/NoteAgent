import { createRouter, createWebHistory } from 'vue-router'

import AssistantPage from '@/pages/AssistantPage.vue'
import HomePage from '@/pages/HomePage.vue'
import LibraryPage from '@/pages/LibraryPage.vue'
import RecordsPage from '@/pages/RecordsPage.vue'
import SettingsPage from '@/pages/SettingsPage.vue'
import { LEGACY_DOCUMENTS_PATH } from '@/shared/navigation'

/**
 * 页面路由；路径必须与 shared/navigation.ts 的 PRIMARY_NAV_ITEMS（四项主入口）
 * 加 SETTINGS_ENTRY（右上角齿轮）一一对应（有单测钉住）。
 */
export const PAGE_ROUTES = [
  { path: '/', name: 'home', component: HomePage },
  { path: '/assistant', name: 'assistant', component: AssistantPage },
  { path: '/records', name: 'records', component: RecordsPage },
  { path: '/library', name: 'library', component: LibraryPage },
  { path: '/settings', name: 'settings', component: SettingsPage },
]

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    ...PAGE_ROUTES,
    // 旧地址兼容，不再承担独立实现。
    { path: LEGACY_DOCUMENTS_PATH, redirect: '/library' },
    // 首轮不定义会话／文件深链接：未知地址回到 Home。
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
