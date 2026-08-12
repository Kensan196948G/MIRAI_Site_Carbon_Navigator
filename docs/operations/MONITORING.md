# 監視・ログ・メトリクス

## ヘルスチェック

| エンドポイント | 用途 | 期待値 |
|---|---|---|
| `GET /api/health` | 生存確認 | 200 `{"status":"ok"}` |
| `GET /api/health/ready` | DB含む準備確認（監視スクリプトはこちらを使用） | 200 `{"db":"ok"}` |

## ログ

- 保存先: `logs/`（monitor.log、monitor_state、backup_cron.log、uvicorn 標準出力）
- 内容: リクエストログ（method/path/status/duration_ms/ip）、監視結果、バックアップ結果
- 保持期間: 90日（超過分は圧縮アーカイブ、担当: 運用管理者）
- 検索方法: `rg "FAIL|error|5xx" logs/`
- 個人情報マスキング: パスワードハッシュはDB/エクスポートから除外済み。ログにパスワード・トークンは出力しない方針（フロントエンドの`Authorization`ヘッダーはログに含めない）

## 監査ログ

- 保存先: DB `audit_logs` テーブル（操作: create/update/delete/approve/login 等）
- 保持期間: 3年（年次アーカイブ推奨）
- 検索: 管理画面「監査」タブ / `GET /api/audit-logs`

## メトリクス

- `GET /api/admin/status`（admin）: バージョン、DB状態、起動時間、主要テーブル件数
- 応答時間・エラー率: リクエストログから `logs/` の集計で算出（初期運用は手動集計）
- 外部API（SMTP/Teams/テレマティクス）: 通知試験・取込試験で定期確認

## 障害検知（2026-08-12 改善）

- `scripts/monitor.sh` は `/api/health/ready` を確認（DB 障害も検知）
- 3 回連続失敗で `MIRAI_TEAMS_WEBHOOK` にアラートを送信（未設定時はログのみ）
- 連続失敗数は `logs/monitor_state` に保持し、成功で 0 に戻す
- アラート通知が届くよう SMTP/Teams の設定と月次通知試験を必須とする

## 容量上限

- ログ容量: `logs/` は 500MB で警告、1GB でローテーション（手動）
- DB: PostgreSQLボリュームの残量を月次点検（運用台帳に記録）
