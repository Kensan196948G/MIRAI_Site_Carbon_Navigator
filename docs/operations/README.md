# 運用ドキュメント索引

MIRAI Site Carbon Navigator の本番運用に必要な文書です。

| 文書 | 内容 |
|---|---|
| [SLO.md](./SLO.md) | SLI/SLO、アラート閾値、通知先、エスカレーション、一次対応責任者 |
| [MONITORING.md](./MONITORING.md) | ヘルスチェック、ログ、メトリクス、個人情報マスキング、保存先・保持期間 |
| [BACKUP_RESTORE.md](./BACKUP_RESTORE.md) | バックアップ方式、保持期間、RPO/RTO、復元手順、復元試験 |
| [RUNBOOK.md](./RUNBOOK.md) | 障害対応・切り分け・rollback・復旧・データ訂正・連絡手順 |
| [OPERATIONS_LEDGER.md](./OPERATIONS_LEDGER.md) | 日次・週次・月次・四半期点検、担当、周期、証跡、次回予定 |
| [SECURITY.md](./SECURITY.md) | 秘密情報・証明書・Secrets・アクセス権限・依存関係・ライセンス管理 |

## 本番環境の一意特定情報

| 項目 | 値 |
|---|---|
| アプリ URL | https://carbon.mirai-dx-platform.com |
| 公開方式 | Cloudflare Tunnel（cloudflared） |
| アプリコンテナ | docker compose `app`（FastAPI/uvicorn, port 8000 inside network） |
| DB | docker compose `db`（PostgreSQL 16, コンテナ内ネットワークのみ） |
| DB接続 | `postgresql+psycopg2://mirai:mirai@db:5432/mirai_carbon`（外部非公開） |
| バックアップ | `scripts/backup.sh` → `backups/`（14世代保持） |
| 監視 | `scripts/monitor.sh` → `logs/monitor.log`（cron 5分毎） |
| デプロイ | `scripts/deploy.sh`（main確定commitから実施） |

> スモークテスト（`scripts/smoke.sh`）は `SMOKE_PASSWORD` 環境変数が必須です。
> 既定開発パスワードは本番では使えません。

## 定期ジョブ（cron）

| ジョブ | 周期 | コマンド |
|---|---|---|
| バックアップ | 毎日 02:00 | `scripts/backup_cron.sh` |
| ヘルス監視 | 5分毎 | `scripts/monitor.sh` |

設定例:
```cron
0 2 * * * /home/kensan/Projects/Mirai-DX-Project/MIRAI_Site_Carbon_Navigator/scripts/backup_cron.sh >> /home/kensan/Projects/Mirai-DX-Project/MIRAI_Site_Carbon_Navigator/logs/backup_cron.log 2>&1
*/5 * * * * /home/kensan/Projects/Mirai-DX-Project/MIRAI_Site_Carbon_Navigator/scripts/monitor.sh
```
