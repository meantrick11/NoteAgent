# Models

`Router/` 提供配置与运行接口；`Domain/Dto/` 是 HTTP 对象，`Domain/Vo/` 是配置、能力和错误；`Mapper/` 持久化配置。`Provider/` 适配模型客户端及探测，`Service/ModelRuntime.py` 管理当前运行快照和模型切换。

## 聊天模型能力验证

配置卡片显示 `text` 与 `vision`。`capabilities` 表示启用的能力，`verified_capabilities` 和 `capability_checked_at` 记录最近一次实测通过的能力及时间。旧配置的 `vision` 声明不自动视为已验证；图片解析要求 `vision` 同时启用且已验证。模型连接字段或凭据变更后验证结果失效。验证是当时的结果，不保证供应商服务持续可用。

- `POST /model-settings/chat/profiles/{id}/capabilities/{text|vision}/verify`：请求 `{ "expected_revision": n }`。文字探测检查流式输出和工具调用；视觉探测使用与图片解析相同的 `image_url` 输入，连续两轮核对随机六色块答案。成功时保存结果并返回无密钥的配置；失败不写入。
- `DELETE /model-settings/chat/profiles/{id}/capabilities/vision?expected_revision=n`：关闭视觉能力并清除其验证结果。`text` 为必需能力，不能关闭。
- 验证期间配置版本变化返回 409；供应商连接失败和超时分别沿用模型探测的 502/504 错误。接口不记录测试图片、模型原始回答或密钥。
