# Apple 订阅 Webhook

处理来自 Apple App Store 的服务器通知（Server Notifications），实时更新订阅状态。

## 功能

- ✅ 使用 Apple 官方库 `@apple/app-store-server-library` 验证签名
- ✅ 自动验证 JWS（JSON Web Signature）签名
- ✅ 处理多种订阅事件：
  - `SUBSCRIBED` - 新订阅
  - `DID_RENEW` - 续订成功
  - `DID_FAIL_TO_RENEW` - 续订失败
  - `EXPIRED` - 订阅过期
  - `DID_CHANGE_RENEWAL_STATUS` - 自动续订状态变更
  - `REFUND` - 退款
- ✅ 自动更新数据库中的订阅状态

## 配置步骤

### 1. 在 App Store Connect 中配置 Webhook URL

1. 登录 [App Store Connect](https://appstoreconnect.apple.com)
2. 进入 **"App Store Connect" → "My Apps" → 选择你的应用**
3. 点击 **"General" → "App Information"**
4. 滚动到 **"App Store Server Notifications"**
5. 设置 Webhook URL：
   ```
   https://api.delvetech.cn/v1/functions/apple-webhook/executions
   ```
6. 选择通知版本：**Version 2**（推荐）
7. 点击 **"Save"**

### 2. 部署函数

```bash
cd backend
npx appwrite push function apple-webhook
```

### 3. 配置环境变量

在 Appwrite Console 中设置以下环境变量：

| 变量名 | 说明 | 示例值 |
|--------|------|--------|
| `APPWRITE_ENDPOINT` | Appwrite API 端点 | `https://api.delvetech.cn/v1` |
| `APPWRITE_PROJECT_ID` | Appwrite 项目 ID | `6901942c30c3962e66eb` |
| `APPWRITE_API_KEY` | Appwrite API 密钥 | 从 Console 获取 |
| `APPWRITE_DATABASE_ID` | 数据库 ID | `main` |
| `APPLE_BUNDLE_ID` | 应用的 Bundle ID | `com.delvetech.sureup` |
| `APPLE_ENVIRONMENT` | 环境 | `Sandbox` 或 `Production` |

## Webhook 工作流程

```
┌──────────────┐
│  Apple 服务器 │
└──────┬───────┘
       │ 1. 发送通知 (signedPayload)
       ▼
┌──────────────────┐
│  apple-webhook   │
│  验证 JWS 签名    │
└──────┬───────────┘
       │ 2. 解析通知类型
       ▼
┌──────────────────┐
│ 查找用户 ID       │
│ (originalTxnId)  │
└──────┬───────────┘
       │ 3. 更新订阅状态
       ▼
┌──────────────────┐
│  Appwrite 数据库  │
│  - subscriptions │
│  - profiles      │
└──────────────────┘
```

## 通知类型说明

| 通知类型 | 说明 | 订阅状态 |
|---------|------|---------|
| `SUBSCRIBED` | 用户首次订阅或重新订阅 | `active` |
| `DID_RENEW` | 订阅成功续订 | `active` |
| `DID_FAIL_TO_RENEW` | 订阅续订失败 | `expired` |
| `EXPIRED` | 订阅已过期 | `expired` |
| `DID_CHANGE_RENEWAL_STATUS` | 用户开启/关闭自动续订 | 根据情况 |
| `REFUND` | 用户获得退款 | `expired` |

## 测试

### 沙盒环境测试

在沙盒环境中，订阅会加速：
- 1 个月订阅 → 5 分钟
- 订阅会自动续订 6 次

Apple 会在以下时间点发送通知：
1. 首次订阅时：`SUBSCRIBED`
2. 每次自动续订时：`DID_RENEW`
3. 最后一次续订后过期：`EXPIRED`

### 手动测试 Webhook

使用 curl 模拟 Apple 的通知（需要真实的 signedPayload）：

```bash
curl -X POST https://api.delvetech.cn/v1/functions/apple-webhook/executions \
  -H "Content-Type: application/json" \
  -d '{
    "signedPayload": "eyJhbGc..."
  }'
```

### 查看日志

在 Appwrite Console 中：
1. 进入 **Functions → apple-webhook**
2. 点击 **"Executions"** 标签
3. 查看每次执行的日志

## 常见问题

### Q: Webhook 没有被触发？

**A:** 检查：
1. Webhook URL 是否正确配置在 App Store Connect
2. 函数是否已部署并启用
3. 函数权限设置中是否包含 `guests`（允许未认证访问）

### Q: 签名验证失败？

**A:** 检查：
1. `APPLE_BUNDLE_ID` 是否正确
2. `APPLE_ENVIRONMENT` 是否匹配（沙盒或生产环境）
3. Apple 官方库是否为最新版本

### Q: 找不到用户？

**A:** 这是正常的！首次订阅时：
1. 用户在应用内购买
2. 应用调用 `subscription-verify` 验证并创建订阅记录
3. 之后 Apple Webhook 才能通过 `originalTransactionId` 找到用户

如果用户还没通过应用验证购买，Webhook 会记录日志但不会报错。

## 参考文档

- [App Store Server Notifications](https://developer.apple.com/documentation/appstoreservernotifications)
- [Apple Server Library (Node.js)](https://github.com/apple/app-store-server-library-node)
- [Enabling App Store Server Notifications](https://developer.apple.com/documentation/appstoreservernotifications/enabling_app_store_server_notifications)

## 安全性

- ✅ 所有通知都会验证 Apple 的 JWS 签名
- ✅ 使用 Apple 官方的根证书验证
- ✅ 检查 Bundle ID 和环境匹配
- ✅ 防止重放攻击（transactionId 唯一性）

## 生产环境注意事项

部署到生产环境前：

1. **更改环境变量**：
   ```
   APPLE_ENVIRONMENT=Production
   ```

2. **更新 Bundle ID**：
   ```
   APPLE_BUNDLE_ID=com.yourcompany.yourapp
   ```

3. **配置生产环境 Webhook URL**：
   在 App Store Connect 中设置生产环境的 URL

4. **监控执行日志**：
   定期检查 Webhook 执行情况，确保通知正常处理

