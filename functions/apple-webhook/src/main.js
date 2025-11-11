/**
 * Apple App Store Server Notifications (ASSN v2)
 * ✅ 支持 webhook 验签
 * ✅ 支持 Execution envelope (Appwrite functions.createExecution)
 * ✅ 更新 Appwrite 订阅表 & 用户档案表
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { Client, Databases, Query, ID } from 'node-appwrite';
import {
  SignedDataVerifier,
  Environment,
  NotificationTypeV2,
} from '@apple/app-store-server-library';

// ========== Paths / ENV / Setup ==========
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 本地 Apple Root CA 证书
const APPLE_CERT_PATH = path.join(__dirname, '../certs/AppleRootCA-G3.cer');

// DB collection
const DB_ID = process.env.APPWRITE_DATABASE_ID || 'main';
const COL_SUBSCRIPTIONS = 'subscriptions';
const COL_PROFILES = 'profiles';

// Apple config
const APPLE_BUNDLE_ID = process.env.APPLE_BUNDLE_ID;
const APPLE_ENVIRONMENT = (process.env.APPLE_ENVIRONMENT || 'Sandbox').toLowerCase();
const APPLE_APP_ID = process.env.APPLE_APP_ID ? Number(process.env.APPLE_APP_ID) : undefined;

// ========== 工具函数 ==========

// ✅ 读取本地证书
function loadAppleRootCert(log) {
  const buf = fs.readFileSync(APPLE_CERT_PATH);
  log(`[Apple] 加载本地 Root CA: ${APPLE_CERT_PATH}`);
  return [buf];
}

// ✅ 创建验签器
async function createVerifier(log) {
  const certs = loadAppleRootCert(log);
  const env = APPLE_ENVIRONMENT === 'production'
    ? Environment.PRODUCTION
    : Environment.SANDBOX;

  log(`[Apple] 证书环境: ${env}, bundleId: ${APPLE_BUNDLE_ID}, appId: ${APPLE_APP_ID ?? '(未设置)'}`);

  return new SignedDataVerifier(
    certs,
    true,
    env,
    APPLE_BUNDLE_ID,
    APPLE_APP_ID
  );
}

// ✅ 初始化数据库
function getDB() {
  const client = new Client()
    .setEndpoint(process.env.APPWRITE_ENDPOINT)
    .setProject(process.env.APPWRITE_PROJECT_ID)
    .setKey(process.env.APPWRITE_API_KEY);

  return new Databases(client);
}

/**
 * ✅ 解析 Request Body（支持 Appwrite Execution envelope + object payload）
 */
function safeParseBody(req, log) {
  let raw = req?.body ?? req?.payload ?? null;

  // ✅ Case 1: body 已经是对象，比如 { signedPayload: "..." }
  if (raw && typeof raw === 'object' && !('body' in raw)) {
    log('[Apple Webhook] body 已是对象（Appwrite 直接传递）');
    return raw;
  }

  // ✅ Case 2: Execution envelope { method, path, headers, body }
  if (raw && typeof raw === 'object' && raw.hasOwnProperty('body')) {
    log('[Apple Webhook] 检测到 execution envelope');
    raw = raw.body;
  }

  if (typeof raw !== 'string') {
    raw = String(raw || '');
  }

  log(`[Apple Webhook] raw body(len=${raw.length}) preview="${raw.slice(0, 100)}..."`);

  try {
    return JSON.parse(raw);
  } catch (err) {
    log(`[Apple Webhook] ❌ 原始体不是 JSON，将返回空对象: ${err.message}`);
    return {};
  }
}


// ✅ 根据 originalTransactionId 查找用户
async function findUserByOriginalTransactionId(db, originalTransactionId, log) {
  const resp = await db.listDocuments(DB_ID, COL_SUBSCRIPTIONS, [
    Query.equal('originalTransactionId', originalTransactionId),
    Query.limit(1)
  ]);

  if (resp.total > 0) {
    log(`[DB] 找到原交易对应用户: ${resp.documents[0].userId}`);
    return resp.documents[0].userId;
  }

  log('[DB] 未找到对应用户');
  return null;
}

// ✅ 更新订阅 + profile
async function updateSubscription(db, userId, transaction, notificationType, log) {
  const sub = {
    userId,
    platform: 'ios',
    productId: transaction.productId,
    transactionId: transaction.transactionId,
    originalTransactionId: transaction.originalTransactionId,
    purchaseDate: new Date(transaction.purchaseDate).toISOString(),
    expiryDate: new Date(transaction.expiresDate).toISOString(),
    autoRenew: transaction.autoRenewStatus === 1,
    status:
      [NotificationTypeV2.EXPIRED, NotificationTypeV2.DID_FAIL_TO_RENEW, NotificationTypeV2.REFUND].includes(notificationType)
        ? 'expired'
        : 'active'
  };

  log(`[DB] 更新订阅:`, JSON.stringify(sub, null, 2));

  // 查订阅记录
  const existing = await db.listDocuments(DB_ID, COL_SUBSCRIPTIONS, [
    Query.equal('originalTransactionId', sub.originalTransactionId),
    Query.limit(1)
  ]);

  if (existing.total > 0) {
    await db.updateDocument(DB_ID, COL_SUBSCRIPTIONS, existing.documents[0].$id, sub);
    log('[DB] ✅ 已更新订阅记录');
  } else {
    await db.createDocument(DB_ID, COL_SUBSCRIPTIONS, ID.unique(), sub);
    log('[DB] ✅ 已创建订阅记录');
  }

  // 更新 profile
  const prof = await db.listDocuments(DB_ID, COL_PROFILES, [
    Query.equal('userId', userId),
    Query.limit(1)
  ]);

  if (prof.total > 0) {
    await db.updateDocument(DB_ID, COL_PROFILES, prof.documents[0].$id, {
      subscriptionStatus: sub.status,
      subscriptionExpiryDate: sub.expiryDate
    });
    log('[DB] ✅ 已更新用户 Profile');
  }
}

// ========== Appwrite Function 入口 ==========
export default async ({ req, res, log, error: logError }) => {
  log('================== Apple Webhook Start ==================');
  log(`[Appwrite] req.method=${req.method}`);

  try {
    const body = safeParseBody(req, log);

    if (!body.signedPayload) {
      logError('[Apple Webhook] ❌ 缺少 signedPayload');
      return res.json({ error: 'Missing signedPayload' }, 400);
    }

    if ((body.signedPayload.match(/\./g) || []).length !== 2) {
      log('[Apple Webhook] ⚠️ payload 不像 JWS（测试/非 Apple 调用）');
      return res.json({ status: 'test-mode' }, 200);
    }

    log('[Apple Webhook] ✅ 收到 signedPayload (JWS)');
    log(`[Apple Webhook] signedPayload preview: ${body.signedPayload.slice(0, 80)}...`);

    const verifier = await createVerifier(log);

    log('[Apple Webhook] 🔐 验证通知 JWS...');
    const decodedNotification = await verifier.verifyAndDecodeNotification(body.signedPayload);

    log(`[Apple Webhook] ✅ 通知类型: ${decodedNotification.notificationType}`);

    const signedTransaction = decodedNotification.data?.signedTransactionInfo;
    if (!signedTransaction) {
      log('[Apple Webhook] ⚠️ 通知无 transaction 信息');
      return res.json({ status: 'ignored' }, 200);
    }

    log('[Apple Webhook] 🔐 验证与解析 Transaction JWS...');
    const transaction = await verifier.verifyAndDecodeTransaction(signedTransaction);

    log(`[Apple Webhook] originalTransactionId: ${transaction.originalTransactionId}`);

    const db = getDB();
    const userId = await findUserByOriginalTransactionId(db, transaction.originalTransactionId, log);

    if (!userId) {
      log('[Apple Webhook] ⚠️ 用户尚未建立订阅记录，等待客户端初次验证');
      return res.json({ status: 'pending' }, 200);
    }

    await updateSubscription(db, userId, transaction, decodedNotification.notificationType, log);

    log('================== ✅ 完成 ==================');
    return res.json({ success: true, notificationType: decodedNotification.notificationType });

  } catch (err) {
    logError(`[Apple Webhook] ❌ 错误: ${err.message}`);
    logError(err.stack);
    return res.json({ error: err.message }, 500);
  }
};
