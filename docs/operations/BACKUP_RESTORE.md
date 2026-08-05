# バックアップ / 復元

## バックアップ

- 方式: PostgreSQL 論理バックアップ（`pg_dump -Fc`）
- 実行: `scripts/backup.sh`（cron 毎日 02:00）
- 保存先: `backups/mirai_carbon_YYYYmmdd_HHMMSS.dump`
- 保持: 直近14世代（超過分は自動削除）
- 暗号化: ディスク暗号化はホスト環境に依存（本番移行時にKMS/暗号化ボリューム導入を推奨）
- RPO: 最大24時間 / RTO: 30分以内（復元手順に従う）

## 復元手順

```bash
scripts/restore.sh backups/mirai_carbon_YYYYmmdd_HHMMSS.dump
```

1. 対象バックアップを選択（最新かつ検証済みの世代）
2. appを停止して書き込みを防ぐ（スクリプトが自動実施）
3. `pg_restore --clean --if-exists` でDBを置換
4. appを再起動
5. `scripts/smoke.sh` でログイン・ダッシュボードを確認

## 復元試験（実施済み/定期）

- 初回: 本番デプロイ時にバックアップ→リストア→スモーク試験を実施（結果は運用台帳に記録）
- 定期: 四半期ごとに復元試験を実施
