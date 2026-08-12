# テスト証跡

## 実行日時

2026-08-12（ブランチ `feature/production-hardening-review`）

## 結果サマリ

| 項目 | 結果 |
|---|---|
| pytest 全件 | 178 passed（改善前 163 → 改善後 178、うち新規セキュリティ回帰テスト 15 件） |
| アプリカバレッジ | 86%（`coverage run --source=app`） |
| ruff | 0 error |
| Docker build | 成功（`mirai-carbon-navigator:hardening-ci`） |
| Docker 起動（開発 env） | seed 完了、/api/health 200、CSS/JS/vendor 200 |
| Docker fail-closed | `MIRAI_ENV=production` + 既定シークレットで起動拒否を確認 |
| pip-audit | No known vulnerabilities found |
| GitHub CI | PR プッシュ後に実行予定（test / lint / build / coverage / pip-audit） |

## 新規テストの観点（tests/test_security_hardening.py）

1. 静的アセット配信（CSS/JS/vendor/フォント）が 200
2. CSP に外部 CDN が含まれない
3. site は自支店のみの活動量・算定結果・督促を参照できる
4. site は他支店の活動量を更新・削除・登録できない
5. client は割当工事のみ参照でき、社内マスタ（係数・クレジット・SBTi）へ 403
6. 全量エクスポートに TOTP 秘密・パスワードハッシュが含まれない
7. ログイン失敗 3 回（設定値）で 429 + Retry-After
8. env 承認は branch 承認後に限定
9. 活動量編集で approval_status が draft へ戻る
10. 工事削除で関連行とクレジット充当が掃除される
11. 本番シードは既定アカウントを作らず、初期管理者パスワード必須
12. OIDC は code 交換方式（URL に token 非掲載、使い捨て）

## 実操作確認（TestClient + 実コンテナ）

- ログイン → 工事/活動量/算定 → 承認 → レポートの主要 API フロー（既存 163 件で担保）
- 静的ファイル: 改善前 `/static/css/style.css` 404 → 改善後 200
- 権限実証: 改善前 site が他支店活動量を更新 200 → 改善後 403
- エクスポート: 改善前 TOTP 秘密が ZIP 内 JSON に含まれる → 改善後 除外

## 残りの検証（未実施）

- ブラウザ E2E（Playwright）・実機モバイル
- 負荷試験（600 名同時利用想定）
- 本番 DB に対する復元試験・既定アカウント無効化作業（人間承認待ち）
- 公開 URL の可用性確認（Tunnel 復旧待ち）

## 2026-08-12 夜間の本番検証（追記）

| 項目 | 結果 |
|---|---|
| Cloudflare Tunnel 復旧 | OK（user systemd サービス化、`mirai-site-carbon-navigator` 0接続→4接続） |
| 公開 URL | `/api/health/ready` 200（db ok）、CSS/JS/vendor 200 |
| 本番デプロイ | PR #5 マージ（1e2ee93）→ `scripts/deploy.sh` 成功、health 20s・smoke PASS |
| 公開経由の実操作 | carbon_admin ログイン → ダッシュボード（project_count=2）成功 |
| 既定アカウント無効化 | admin/reviewer/site/viewer を is_active=false、旧 admin ログイン 401 を確認 |
| 通知試験 | SMTP/Teams 未設定のため false（設定には M365/Teams 資格情報が必要） |

## 2026-08-12 残課題対応（追記）

| 項目 | 結果 |
|---|---|
| Tunnel トークン再ローテーション | OK（新トークン発行・旧トークン退避、systemd は `TUNNEL_TOKEN` 環境変数経由で引数非露出） |
| carbon_admin 初回パスワード変更 | OK（24文字ランダム、旧パスワード 401、`.cred` 0600） |
| 通知設定配線 | docker-compose に `MIRAI_SMTP_*` / `MIRAI_TEAMS_WEBHOOK` を追加、`configure_notifications.sh`・手順書を追加 |
| 排出係数一次情報突合 | 燃料・電力・輸送・材料を公式資料と突合。`reconcile_emission_factors.py` を temp DB で dry-run/apply 検証（adds=31、conflicts=0） |
| pytest / ruff 再実行 | 178 passed / ruff 0 error（残課題対応後の master 作業ツリー） |
| 実SMTP/Teams通知試験 | 未実施（M365アプリパスワード・Teams Webhook URL の提供待ち） |

## 2026-08-12 通知経路の単体テスト（追記）

- `tests/test_notifications.py` を追加（SMTP 送信成功・未設定時 false、Teams webhook 送信成功・未設定時 false）
- pytest は通知テスト 4 件を追加し **182 passed / ruff 0 error**
- 実 SMTP/Teams への送信は M365 資格情報・Webhook URL 提供後の `scripts/configure_notifications.sh` で確認する
