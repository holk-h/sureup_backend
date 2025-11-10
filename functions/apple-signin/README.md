# 苹果登录函数 (Apple Sign In)

## 功能说明

验证 Apple Sign In 的 identityToken，查找或创建用户，并返回 session token。

## 流程

1. 接收客户端传来的 Apple Sign In 凭证（identityToken、userIdentifier 等）
2. 从苹果服务器获取公钥
3. 验证 identityToken 的有效性
4. 从 token 中提取用户信息（sub - 用户唯一标识，email 等）
5. 通过 Apple User ID 或 email 查找现有用户
6. 如果用户不存在，创建新用户
7. 检查用户档案是否存在
8. 创建并返回 session token（有效期1年）

## 环境变量配置

在 Appwrite 控制台中，为此函数配置以下环境变量：

### 必需配置

| 变量名 | 说明 | 示例值 |
|--------|------|--------|
| `APPLE_CLIENT_ID` | 苹果开发者后台配置的 Client ID（Service ID） | `com.example.sureup.signin` |
| `APPWRITE_ENDPOINT` | Appwrite API 端点 | `https://api.delvetech.cn/v1` |
| `APPWRITE_PROJECT_ID` | Appwrite 项目 ID | `6901942c30c3962e66eb` |
| `APPWRITE_API_KEY` | Appwrite API 密钥（需要 users.read, users.write, databases.read 权限） | `your-api-key` |

### 可选配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `APPWRITE_DATABASE_ID` | 数据库 ID | `main` |
| `APPWRITE_USERS_COLLECTION_ID` | 用户档案集合 ID | `profiles` |

## Apple Developer 配置要求

### 1. 创建 App ID
- 登录 [Apple Developer](https://developer.apple.com/)
- 进入 Certificates, Identifiers & Profiles
- 创建 App ID，启用 "Sign In with Apple" capability

### 2. 创建 Service ID (Client ID)
- 在 Identifiers 中创建 Services ID
- 记录 Identifier（这就是 `APPLE_CLIENT_ID`）
- 配置 "Sign In with Apple"
- 添加你的域名和回调 URL（用于 Web）

### 3. 在 Xcode 中配置
- 打开项目的 Signing & Capabilities
- 添加 "Sign In with Apple" capability
- 确保 Team 和 Bundle Identifier 正确

## 部署

```bash
# 安装依赖
cd backend/functions/apple-signin
pip install -r requirements.txt

# 通过 Appwrite CLI 部署
appwrite deploy function

# 或通过配置文件部署
cd ../..
appwrite deploy collection
```

## API 请求格式

### 请求

```json
{
  "identityToken": "eyJraWQiOiJlWGF1...",
  "userIdentifier": "001234.abc...",
  "email": "user@example.com",  // 可选，首次登录时苹果提供
  "givenName": "张",              // 可选
  "familyName": "三"              // 可选
}
```

### 响应（成功）

```json
{
  "success": true,
  "message": "验证成功",
  "data": {
    "userId": "507f1f77bcf86cd799439011",
    "email": "user@example.com",
    "name": "三张",
    "isNewUser": false,
    "hasProfile": true,
    "sessionToken": "a1b2c3d4..."
  }
}
```

### 响应（失败）

```json
{
  "success": false,
  "message": "身份验证失败"
}
```

## 安全说明

1. **Token 验证**：使用苹果的公钥验证 identityToken，确保请求来自真实的苹果登录
2. **用户关联**：通过 labels 字段存储 `apple_id:xxx`，用于后续登录时快速查找用户
3. **Email 可选**：用户可能选择隐藏邮箱，所以 email 字段可能为空
4. **首次信息**：givenName 和 familyName 只在首次登录时提供，后续登录不会再提供

## 故障排除

### Token 验证失败

- 检查 `APPLE_CLIENT_ID` 是否正确配置
- 确认 Apple Developer 中的 Service ID 配置正确
- 检查 identityToken 是否过期（有效期很短，约10分钟）

### 用户创建失败

- 检查 API Key 是否有 `users.write` 权限
- 查看 Appwrite 日志获取详细错误信息

### 找不到公钥

- 检查服务器是否能访问 `https://appleid.apple.com/auth/keys`
- 可能是网络问题，稍后重试

