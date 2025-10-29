# 火山引擎短信服务集成说明

本项目使用火山引擎短信服务替代Appwrite内置的短信功能，以支持中国境内的短信发送。

## 一、准备工作

### 1. 开通火山引擎短信服务

1. 访问 [火山引擎控制台](https://console.volcengine.com/)
2. 开通**短信服务**
3. 创建签名和模板
4. 获取AccessKey和SecretKey

### 2. 配置短信模板

创建验证码模板（**重要**）：

**模板要求**：
- 模板类型：必须选择 `CN_OTP`（国内验证码）或 `I18N_OTP`（国际验证码）
- 模板变量：只支持 `${code}`，其他变量不支持
- 签名：需要先审核通过

**模板示例**：
```
【稳了】您的验证码是${code}，5分钟内有效，请勿泄露给他人。
```

**创建步骤**：
1. 登录火山引擎控制台
2. 进入短信服务 → 短信模板
3. 点击"创建模板"
4. 选择模板类型为 `CN_OTP`
5. 输入模板内容，使用 `${code}` 作为验证码占位符
6. 提交审核（通常几分钟内通过）

## 二、后端函数配置

### 1. sms-send 函数

发送验证码的云函数，使用 `SendSmsVerifyCode` API。

**API说明**：
- 验证码由火山引擎自动生成
- 验证码长度：6位
- 有效期：5分钟（300秒）
- 可尝试次数：3次
- 使用场景：`登录注册`

**环境变量**：
```bash
VOLC_ACCESS_KEY=your_access_key          # 火山引擎AccessKey
VOLC_SECRET_KEY=your_secret_key          # 火山引擎SecretKey
VOLC_SMS_ACCOUNT=your_sms_account        # 消息组ID
VOLC_SMS_TEMPLATE_ID=your_template_id    # 验证码模板ID（必须是CN_OTP或I18N_OTP类型）
VOLC_SMS_SIGN_NAME=稳了                   # 签名名称
```

**模板要求**：
- 模板类型必须是 `CN_OTP` 或 `I18N_OTP`
- 模板变量只支持 `${code}`
- 示例：`【稳了】您的验证码是${code}，5分钟内有效，请勿泄露`

**API调用**：
```bash
POST /v1/functions/sms-send/executions
Content-Type: application/json

{
  "phone": "+8613812345678"
}
```

**响应**：
```json
{
  "success": true,
  "message": "验证码已发送",
  "data": {
    "phone": "+8613812345678",
    "messageId": "xxx"
  }
}
```

### 2. sms-verify 函数

验证验证码并处理登录/注册的云函数，使用 `CheckSmsVerifyCode` API。

**API说明**：
- 验证结果：`0`-成功，`1`-错误，`2`-过期
- Scene必须与发送时一致：`登录注册`
- 验证通过后自动创建或登录用户

**环境变量**：
```bash
VOLC_ACCESS_KEY=your_access_key          # 火山引擎AccessKey
VOLC_SECRET_KEY=your_secret_key          # 火山引擎SecretKey
VOLC_SMS_ACCOUNT=your_sms_account        # 消息组ID（必须与发送时一致）
APPWRITE_ENDPOINT=https://api.delvetech.cn/v1
APPWRITE_PROJECT_ID=your_project_id
APPWRITE_API_KEY=your_api_key            # Server API Key
APPWRITE_DATABASE_ID=main
```

**API调用**：
```bash
POST /v1/functions/sms-verify/executions
Content-Type: application/json

{
  "phone": "+8613812345678",
  "code": "123456"
}
```

**响应**：
```json
{
  "success": true,
  "message": "验证成功",
  "data": {
    "userId": "xxx",
    "phone": "+8613812345678",
    "name": "用户5678",
    "isNewUser": true,
    "hasProfile": false
  }
}
```

## 三、部署步骤

### 1. 部署云函数

```bash
# 进入backend目录
cd backend

# 部署sms-send函数
appwrite deploy function --function-id sms-send

# 部署sms-verify函数
appwrite deploy function --function-id sms-verify
```

### 2. 配置环境变量

在Appwrite控制台中为每个函数配置环境变量：

1. 进入 Functions → sms-send → Settings → Variables
2. 添加上述环境变量
3. 对sms-verify函数重复相同操作

### 3. 测试

使用Appwrite控制台或API工具测试函数：

```bash
# 测试发送验证码
curl -X POST https://api.delvetech.cn/v1/functions/sms-send/executions \
  -H "Content-Type: application/json" \
  -H "X-Appwrite-Project: your_project_id" \
  -d '{"phone": "+8613812345678"}'

# 测试验证验证码
curl -X POST https://api.delvetech.cn/v1/functions/sms-verify/executions \
  -H "Content-Type: application/json" \
  -H "X-Appwrite-Project: your_project_id" \
  -d '{"phone": "+8613812345678", "code": "123456"}'
```

## 四、前端集成

前端代码已经更新为调用新的云函数。主要变更：

### 1. AuthService变更

- `sendPhoneVerification()`: 调用`sms-send`函数
- `verifyPhoneAndLogin()`: 调用`sms-verify`函数
- 前端限流：60秒内不能重复发送

### 2. 登录流程

```
1. 用户输入手机号 → 前端验证
2. 调用sendPhoneVerification() → 发送验证码
3. 用户输入验证码
4. 调用verifyPhoneAndLogin() → 验证码验证
5. 验证通过 → 创建/登录用户
6. 新用户 → 跳转到资料完善页面
7. 老用户 → 直接进入应用
```

## 五、注意事项

### 1. 安全性

- ✅ 前端限流：防止频繁请求
- ✅ 验证码有效期：5分钟（火山引擎默认）
- ✅ API Key保护：仅在云函数中使用
- ⚠️ 建议添加：IP频率限制、黑名单机制

### 2. 成本控制

火山引擎短信按条收费：
- 验证码短信：约0.05元/条
- 建议监控每日发送量
- 设置预算告警

### 3. 错误处理

常见错误及处理：

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| 签名未审核 | 签名还在审核中 | 等待审核通过 |
| 模板不存在 | 模板ID错误 | 检查模板配置 |
| 余额不足 | 账户欠费 | 充值 |
| 验证码错误 | 验证码过期或错误 | 重新发送 |

### 4. 监控建议

- 监控云函数执行次数和失败率
- 监控短信发送成功率
- 设置告警规则

## 六、技术实现

**当前实现**：使用火山引擎官方Python SDK `volcengine-python-sdk`

**依赖包**：
```txt
# sms-send
volcengine-python-sdk==1.0.98

# sms-verify  
appwrite==5.0.1
volcengine-python-sdk==1.0.98
```

**关键代码片段**：

```python
from volcengine.ApiInfo import ApiInfo
from volcengine.Credentials import Credentials
from volcengine.ServiceInfo import ServiceInfo
from volcengine.base.Service import Service

def _get_sms_service(access_key, secret_key):
    """初始化火山引擎SMS服务"""
    # API信息
    api_info = {
        'SendSmsVerifyCode': ApiInfo('POST', '/', {
            'Action': 'SendSmsVerifyCode', 
            'Version': '2020-01-01'
        }, {}, {}),
    }
    
    # 服务信息
    service_info = ServiceInfo(
        'sms.volcengineapi.com',
        {},
        Credentials(access_key, secret_key, 'sms', 'cn-north-1'),
        10, 10, 'https'
    )
    
    # 创建服务实例
    return Service(service_info, api_info)

# 调用API
service = _get_sms_service(access_key, secret_key)
response = service.post('/2020-01-01/SendSmsVerifyCode', {}, json.dumps(body))
```

**优势**：
- ✅ 官方SDK，稳定可靠
- ✅ 自动处理签名、重试等细节
- ✅ 减少出错可能性
- ✅ 便于维护和升级

**参考文档**：
- [火山引擎短信服务概览](https://www.volcengine.com/docs/6361/170898)
- [SendSmsVerifyCode API](https://www.volcengine.com/docs/6361/171579)
- [CheckSmsVerifyCode API](https://www.volcengine.com/docs/6361/171580)
- [Python SDK - GitHub](https://github.com/volcengine/volcengine-python-sdk)
- [调用方式说明](https://www.volcengine.com/docs/6361/171632)

## 七、FAQ

**Q: 为什么不使用Appwrite内置的短信功能？**
A: Appwrite内置的短信功能需要国际短信服务商（如Twilio），在中国境内发送短信需要使用国内服务商。

**Q: 验证码有效期是多久？**
A: 火山引擎默认5分钟，可以在模板中配置。

**Q: 可以发送通知短信吗？**
A: 可以，创建新的模板和云函数即可。

**Q: 如何防止恶意刷验证码？**
A: 
1. 前端限流（已实现）
2. IP限流（建议在云函数中添加）
3. 图形验证码（可选）
4. 黑名单机制

**Q: 费用大概是多少？**
A: 验证码短信约0.05元/条，1000条约50元。建议充值50-100元测试。

