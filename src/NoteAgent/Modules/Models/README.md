# Models

`Router/` 提供配置与运行接口；`Domain/Dto/` 是 HTTP 对象，`Domain/Vo/` 是配置、能力和错误；`Mapper/` 持久化配置。`Provider/` 适配模型客户端及探测，`Service/ModelRuntime.py` 管理当前运行快照和模型切换。

## 聊天模型能力验证

配置卡片显示 `text` 与 `vision`，两项分别验证、分别着色。`capabilities` 保留聊天协议所需的 `text` 声明及已启用的 `vision`；`verified_capabilities` 和 `capability_checked_at` 分别记录实测通过的能力及时间。`text_enabled` 记录用户是否允许该配置用于新聊天，旧配置默认允许；关闭 `text` 后新聊天被拒绝，重新验证后恢复。旧配置的 `vision` 声明不自动视为已验证；图片解析要求 `vision` 同时启用且已验证。模型连接字段或凭据变更后验证结果失效。验证是当时的结果，不保证供应商服务持续可用。

- `POST /model-settings/chat/profiles/{id}/capabilities/{text|vision}/verify`：请求 `{ "expected_revision": n }`。文字探测检查流式输出和工具调用；视觉探测先确认文字协议可用，再使用与图片解析相同的 `image_url` 输入，连续两轮核对随机六色块答案。成功时只保存本次点击的能力，并返回无密钥的配置；失败不写入。
- `DELETE /model-settings/chat/profiles/{id}/capabilities/{text|vision}?expected_revision=n`：关闭指定能力并清除其验证结果。关闭 `text` 会暂停该配置的新聊天；关闭 `vision` 会停止图片解析权限。两项互不改变对方的验证状态。
- 验证期间配置版本变化返回 409；供应商连接失败和超时分别沿用模型探测的 502/504 错误。接口不记录测试图片、模型原始回答或密钥。
