# 短信服务商切换指南

## 概述

本项目支持多个短信服务商，目前已集成：
- **阿里云短信服务**（默认）
- **火山引擎短信服务**

通过环境变量 `SMS_PROVIDER` 可以轻松切换服务商。

## 架构设计

### 模块化设计
- `providers/base.py`: 定义统一的短信服务商接口
- `providers/aliyun_provider.py`: 阿里云短信服务商实现
- `providers/volc_provider.py`: 火山引擎短信服务商实现
- `providers/__init__.py`: 模块初始化文件

### 统一接口
所有服务商都实现相同的接口：
- `send_verification_code(phone)`: 发送验证码
- `verify_code(phone, code)`: 验证验证码

## 配置说明

### 1. 阿里云短信服务（默认）

在 `appwrite.config.json` 中配置以下环境变量：

```json
{
  "SMS_PROVIDER": "aliyun",
  "ALIYUN_ACCESS_KEY_ID": "你的阿里云AccessKeyId",
  "ALIYUN_ACCESS_KEY_SECRET": "你的阿里云AccessKeySecret", 
  "ALIYUN_SMS_SIGN_NAME": "稳了",
  "ALIYUN_SMS_TEMPLATE_CODE": "你的短信模板代码"
}
```

**注意**: 阿里云没有提供验证码验证接口，系统会将验证码存储在数据库表 `sms_verification_codes` 中进行验证。

### 2. 火山引擎短信服务

在 `appwrite.config.json` 中配置以下环境变量：

```json
{
  "SMS_PROVIDER": "volc",
  "VOLC_ACCESS_KEY": "你的火山引擎AccessKey",
  "VOLC_SECRET_KEY": "你的火山引擎SecretKey",
  "VOLC_SMS_ACCOUNT": "你的短信账户",
  "VOLC_SMS_TEMPLATE_ID": "你的模板ID",
  "VOLC_SMS_SIGN_NAME": "稳了"
}
```

## 数据库表

### sms_verification_codes (阿里云专用)

用于存储阿里云短信验证码：

| 字段 | 类型 | 说明 |
|------|------|------|
| phone | string | 手机号（作为文档ID） |
| code | string | 验证码 |
| createdAt | datetime | 创建时间 |
| expiresAt | datetime | 过期时间 |

## 切换服务商

只需要修改环境变量 `SMS_PROVIDER` 的值：

- `aliyun`: 使用阿里云短信服务
- `volc`: 使用火山引擎短信服务

## 测试验证码

系统支持测试验证码 `010101`，无论使用哪个服务商都会直接通过验证。

## 错误处理

### 统一错误格式
```json
{
  "success": false,
  "message": "用户友好的错误信息",
  "error_code": "具体的错误代码"
}
```

### 常见错误码
- `SEND_ERROR`: 发送失败
- `VERIFY_ERROR`: 验证失败
- `CODE_EXPIRED`: 验证码过期
- `CODE_INVALID`: 验证码错误
- `CODE_NOT_FOUND`: 验证码不存在

## 扩展新服务商

1. 在 `providers/` 目录下创建新的服务商实现文件
2. 继承 `SMSProvider` 基类
3. 实现必要的方法：`validate_config()`, `send_verification_code()`, `verify_code()`
4. 在文件末尾注册服务商：`SMSProviderFactory.register_provider('新服务商名称', 新服务商类)`
5. 在 `main.py` 中导入新的服务商文件
6. 在 `_create_sms_provider()` 函数中添加新服务商的配置逻辑

## 部署注意事项

1. 确保在 Appwrite 控制台中正确配置了所有环境变量
2. 阿里云服务商需要确保 Appwrite 数据库权限正确配置
3. 验证短信模板和签名已在对应平台审核通过
4. 测试环境可以使用测试验证码 `010101` 进行调试
