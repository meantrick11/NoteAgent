import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from '@/App.vue'
import { router } from '@/router'
import { installBeforeUnload, installUnsavedGuard } from '@/shared/unsaved-guard'
import '@/styles/tokens.css'
import '@/styles/base.css'

const app = createApp(App)
// 守卫要用 store，所以先装 pinia 再注册路由；未保存检查覆盖顶部导航、
// Home 快捷入口与浏览器前进后退三条路径。
installUnsavedGuard(router)
installBeforeUnload()

app.use(createPinia()).use(router).mount('#app')
