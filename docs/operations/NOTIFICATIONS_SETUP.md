# 通知チャネル設定手順（SMTP / Teams）

## 必要な情報（利用者から提供を受ける項目）

| 項目 | 例 | 説明 |
|---|---|---|
| MIRAI_SMTP_HOST | smtp.office365.com | Exchange Online SMTP エンドポイント |
| MIRAI_SMTP_PORT | 587 | STARTTLS 用ポート |
| MIRAI_SMTP_USER | carbon-noreply@<domain> | M365 アカウント |
| MIRAI_SMTP_PASSWORD | アプリパスワード | M365 でアプリパスワードを発行（条件付きアクセス設定に注意） |
| MIRAI_SMTP_FROM | carbon-noreply@<domain> | 送信元アドレス |
| MIRAI_TEAMS_WEBHOOK | https://...office.com/webhookb2/... | Teams チャネルの Incoming Webhook URL |

## M365 側の準備（管理者作業）

1. 送信用メールボックス（例: carbon-noreply@...）を用意
2. アプリパスワードを発行（多要素認証必須の環境では「アプリ パスワード」または SMTP AUTH 許可）
3. Teams の対象チャネル → コネクタ → Incoming Webhook を追加し URL を取得
4. Webhook URL・パスワードは本リポジトリの `.env` にのみ保存（Git へコミット禁止）

## 設定コマンド

```bash
MIRAI_SMTP_HOST=smtp.office365.com \
MIRAI_SMTP_PORT=587 \
MIRAI_SMTP_USER=carbon-noreply@example.com \
MIRAI_SMTP_PASSWORD='<app-password>' \
MIRAI_SMTP_FROM=carbon-noreply@example.com \
MIRAI_SMTP_TLS=1 \
MIRAI_TEAMS_WEBHOOK='<teams-webhook-url>' \
./scripts/configure_notifications.sh
```

## 確認

- `email_sent: true` / `teams_sent: true` になれば成功
- メール本文・Teams 通知の到着を実機で確認
- 未設定のままの場合は `false` が返る（チャネル未設定の状態）

## セキュリティ注意

- SMTP パスワード・Webhook URL は `.env`（パーミッション 600）のみ
- ログ・PR・スクリーンショットに値を出さない
- 漏えい時は即時再発行（運用台帳に記録）
