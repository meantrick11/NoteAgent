# 模型能力标签与实测验证：执行记录

日期：2026-10-20。对应本轮用户确认的 `text + vision` 方案；未引入 `video` 或视频上传。

## 已实现

- 模型卡片在「已启用」旁显示 `text`、`vision`；点击即验证，失败弹窗且不保存；已验证的 `vision` 可关闭。编辑表单不再重复提供视觉复选框。
- 文字继续检查流式输出和工具调用；视觉使用与图片解析相同的 `image_url` 协议，发送两轮独立、各含三种颜色的六色块图片并逐轮核对答案，总计 20 秒超时。探测期间配置版本变化会拒绝提交。
- 模型配置 JSON 升级至 schema 3，保存最近验证能力和时间；旧配置仍可读取，但旧 `vision` 声明不视为已验证。图片解析要求视觉能力已启用且已验证。连接字段或凭据变化后，验证状态失效。
- 新增按模型配置 ID 验证能力和关闭视觉能力的 HTTP 接口；响应不包含 API Key 或内部凭据摘要。

## 自动验证

| 命令 | 结果 |
|---|---|
| `.venv/Scripts/python.exe -m pytest Tests/Unit/Modules/Models Tests/Unit/Modules/Sources Tests/Integration/TestModelSettingsApi.py -q` | 172 passed |
| `npm run test:unit` | 147 passed |
| `npx playwright test tests/e2e/settings.spec.ts --workers=1` | 18 passed |
| `npm run build` | 通过 |

真实视觉模型探测**未运行**：本机只有环境默认的 `deepseek-v4-flash` 文本配置，没有单独配置可验证的视觉模型。自动测试使用模拟模型验证协议、正确/错误答案和失败状态，不能代替真实供应商验收。本轮未运行数据库迁移，也未修改本机数据库。

## 交互修订（2026-10-20）

用户反馈两项标签应独立，并允许再次点击关闭。现在验证 `vision` 只点亮 `vision`；`text` 与 `vision` 分别使用蓝色、紫色。点击亮色标签关闭本项，失败弹窗出现时立即退出「验证中」。关闭 `text` 后只拦截新的聊天请求，`vision` 状态不变；重新验证 `text` 后恢复聊天。

模型配置 JSON 升级至 schema 4，新增 `text_enabled`，旧配置缺省为允许聊天。`capabilities` 继续保留聊天协议需要的 `text`，关闭标签时记录用户主动暂停；没有数据库迁移。更新后的验证结果：后端相关测试 174 passed、前端单测 149 passed、设置页端到端测试 19 passed、前端构建通过。真实供应商视觉探测仍未运行。
