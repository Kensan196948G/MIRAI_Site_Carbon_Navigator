# Runbook（障害対応手順）

## 共通の切り分け

1. `scripts/monitor.sh` のログと `logs/monitor.log` の FAIL 時刻を確認
2. `docker compose ps` で app/db の状態確認
3. `GET /api/health/ready` で DB 接続を確認
4. リクエストログで 5xx・遅延の傾向を確認

## 障害シナリオ

### A. appコンテナ停止・クラッシュ
1. `docker compose logs --tail=100 app` で原因確認
2. 設定変更が原因なら直近デプロイcommitを確認
3. `docker compose up -d app` で再起動 → ヘルス確認
4. 再発時: `scripts/deploy.sh` を直近の安定commitで再実行、またはバックアップから復元

### B. DB障害・接続失敗
1. `docker compose logs --tail=100 db` でDBログ確認
2. `docker compose ps` でdbの状態確認（healthy）
3. データ損失リスクがあれば app を停止し、直近バックアップで復元（`scripts/restore.sh`）
4. 復旧後 `scripts/smoke.sh` で確認

### C. 認証・ログイン障害
1. `logs/monitor.log` と API ログで 401/500 を確認
2. `MIRAI_SECRET_KEY` が変わっていないか確認（変更すると全トークン失効）
3. 2FA有効ユーザーは一時トークン期限（5分）を確認
4. OIDC障害時はユーザーにローカルログインを案内（OIDCユーザーは管理者がパスワード再発行）

### D. データ訂正
1. 誤登録は管理画面の削除/更新で対応（変更履歴・監査ログに自動記録）
2. 承認済み・締め済みデータの訂正は「締め解除（admin）→修正→再承認→再締め」の順で実施
3. 大量訂正はバックアップ取得後に実施し、結果を運用台帳に記録

### E. セキュリティインシデント（秘密漏えい疑い）
1. 対象Secrets（`MIRAI_SECRET_KEY`、SMTP/Teams/テレマティクス/OIDC）を即時ローテーション
2. アクセスログ・監査ログで異常操作を確認
3. 影響範囲を記録し、必要ならアカウント無効化

## 連絡先

- 一次対応: 本番運用管理者
- エスカレーション: GitHub オーナー（Kensan196948G）
- 記録: 本リポジトリのIssueに障害No・時刻・影響・復旧内容を記載
