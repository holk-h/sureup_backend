# 订阅验证 Function

## 功能

验证 iOS App Store 和 Android Google Play 的购买收据，创建/更新订阅记录。

## 环境变量

必需的环境变量：
- `APPWRITE_ENDPOINT`: Appwrite API 端点
- `APPWRITE_PROJECT_ID`: 项目 ID
- `APPWRITE_API_KEY`: API Key
- `APPWRITE_DATABASE_ID`: 数据库 ID (默认: main)
- `APPLE_SHARED_SECRET`: Apple App Store 共享密钥（用于验证 iOS 收据）
- `GOOGLE_SERVICE_ACCOUNT_JSON`: Google Play 服务账号 JSON（用于 Android 收据验证，待实现）

## API 接口

### 验证订阅

**请求格式（iOS）：**
```json
{
  "userId": "用户 ID",
  "platform": "ios",
  "receiptData": "base64 编码的收据数据"
}
```

**请求格式（Android）：**
```json
{
  "userId": "用户 ID",
  "platform": "android",
  "productId": "产品 ID（如 monthly_premium）",
  "purchaseToken": "购买令牌",
  "packageName": "应用包名"
}
```

**成功响应：**
```json
{
  "success": true,
  "subscription": {
    "id": "订阅记录 ID",
    "productId": "monthly_premium",
    "expiryDate": "2025-12-11T10:00:00.000Z",
    "autoRenew": true
  },
  "message": "订阅已激活"
}
```

**失败响应：**
```json
{
  "success": false,
  "error": "错误消息",
  "details": {}
}
```

## 工作流程

1. 前端完成内购后获取收据
2. 调用此 Function 传递收据数据
3. Function 验证收据有效性
4. 创建/更新 `subscriptions` 表记录
5. 更新 `profiles` 表的订阅状态
6. 返回结果给前端

## 注意事项

### iOS
- 支持生产环境和沙盒环境自动切换
- 需要在 App Store Connect 中获取共享密钥
- 收据数据需要 base64 编码

### Android
- **当前为简化实现，生产环境必须完整实现 Google Play API 验证**
- 需要创建 Google Play 服务账号
- 需要启用 Google Play Developer API
- 需要获取服务账号 JSON 密钥文件

## 安全性

- ✅ 防重放攻击：通过 `transactionId` 唯一索引
- ✅ 服务端验证：所有验证在服务端完成
- ✅ 收据加密存储：敏感数据加密保存
- ⚠️ Android 验证待完善：需实现完整的 Google Play API 调用

