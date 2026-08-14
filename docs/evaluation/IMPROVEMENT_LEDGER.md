# 改善台帳（2026-08-12）

ブランチ: `feature/production-hardening-review` / 検証: テスト176件・ruff 0 error・Docker build 成功

## 実装済み改善

| # | 分類 | 内容 | 影響度 | 変更箇所 | 証跡 |
|---|---|---|---|---|---|
| 1 | UI 復旧 | `/static` マウントを `frontend/static` へ修正（CSS/JS 404 解消） | 重大 | app/main.py | テスト・実コンテナで 200 確認 |
| 2 | セキュリティ | 活動量・算定結果・督促・アクション・フィードバック等を利用者可視範囲（支店/割当工事）へ限定 | 重大 | app/crud.py, routers | tests/test_security_hardening.py |
| 3 | セキュリティ | site の他支店・client の全操作を API で拒否 | 重大 | app/crud.py, routers | 同テスト |
| 4 | セキュリティ | エクスポートから TOTP 秘密・oidc_sub を除外 | 重大 | app/routers/export.py | 同テスト |
| 5 | セキュリティ | OIDC をワンタイムコード交換方式へ変更（URL にトークン非掲載） | 重大 | app/routers/auth.py, app.js | 同テスト |
| 6 | セキュリティ | ログイン失敗回数制限（15分/10回→429） | 高 | app/routers/auth.py | 同テスト |
| 7 | セキュリティ | パスワード最小 10 文字 | 高 | app/schemas.py, index.html | テスト更新 |
| 8 | セキュリティ | 多段階承認の遷移制約強化（env 承認は branch 承認後のみ） | 高 | app/crud.py | 同テスト |
| 9 | データ整合 | 活動量編集時に approval_status を draft へリセット | 高 | app/crud.py | 同テスト |
| 10 | データ整合 | 工事削除で算定結果・変更履歴・コメント・締め・アクセス割当・クレジット充当を掃除 | 高 | app/crud.py | 同テスト |
| 11 | セキュリティ | 既定開発アカウントは `MIRAI_SEED_DEFAULT_USERS=1` 時のみ。本番は環境変数で初期管理者作成 | 重大 | seed_data.py, docker-entrypoint.sh | 同テスト |
| 12 | セキュリティ | 本番 env で `MIRAI_SECRET_KEY` 未設定/プレースホルダーなら起動失敗（fail-closed） | 重大 | docker-entrypoint.sh | 実コンテナ検証 |
| 13 | セキュリティ | フロントエンド資材を自己ホスト化（CDN/SRI 依存排除）、CSP を self のみへ | 高 | frontend/index.html, vendor/, app/main.py | テスト・実コンテナ |
| 14 | セキュリティ | HSTS を compose デフォルト有効化、.env.example を本番向けへ更新 | 中 | docker-compose.yml, .env.example | - |
| 15 | セキュリティ | 既定アカウント無効化スクリプト `scripts/disable_default_users.py` 追加 | 重大 | scripts/ | ドキュメント |
| 16 | データ品質 | 東京電力EP 係数を 2024 年度速報値 0.421 へ更新 | 高 | seed_data.py | 公式ニュースリリース（2025-08-01） |
| 17 | 性能 | 主要クエリ（活動量・算定結果・監査・通知等）へインデックス追加 | 中 | app/database.py | 起動検証 |
| 18 | 監視 | ヘルス監視を `/api/health/ready`（DB 含む）へ変更、3回連続失敗で Teams アラート | 中 | scripts/monitor.sh | ログ |
| 19 | バックアップ | バックアップ checksum と `scripts/verify_backup.sh` 追加 | 中 | scripts/ | - |
| 20 | CI/CD | pip-audit の `\|\| true` を撤廃、カバレッジゲート（80%）、Dependabot 追加 | 中 | .github/ | CI 実行予定 |
| 21 | コード品質 | security.py の循環 import を解消（遅延 import 化） | 中 | app/security.py | 全テスト |
| 22 | 文書 | 評価・台帳・証跡・ロードマップ追加、README を実態へ更新 | 中 | docs/, README.md | - |

## 2026-08-14 MVP/Prototype レビュー対応（追記）

| # | 分類 | 内容 | 影響度 | 変更箇所 | 証跡 |
|---|---|---|---|---|---|
| 23 | セキュリティ | site の明示 `project_id` 指定による他支店閲覧漏れを修正（`has_project_access` に支店境界追加、actions/feedbacks/closes 一覧も 403） | 重大 | app/crud.py, app/routers/{actions,feedbacks,closes}.py | tests/test_security_hardening.py |
| 24 | セキュリティ | `crud.create_user` が branch/email を保存しない問題を修正 | 高 | app/crud.py | 同テスト |
| 25 | MVP | 架空ダミーデータ一式を投入する `scripts/seed_mvp_demo.py` を追加（冪等） | - | scripts/ | tests/test_mvp_demo_seed.py |
| 26 | MVP | デモ環境バナー（`/api/meta` + `MIRAI_DEMO_MODE`）を追加 | 中 | app/main.py, frontend/ | 公開 URL で確認 |
| 27 | MVP | MVP 専用トンネル・systemd・起動/検証スクリプト一式を追加し公開 | - | scripts/, docs/operations/MVP_ENVIRONMENT.md | https://carbon-mvp.mirai-dx-platform.com |
| 28 | テスト | 認可回帰 2 件 + デモシード統合 2 件を追加（計 186 passed / coverage 87%） | 中 | tests/ | CI 実行 |

## 残課題（優先度順）

| # | 課題 | 影響度 | 必要操作 |
|---|---|---|---|
| 1 | 公開 URL が 530（Tunnel 断）継続中 | 重大 | ✅ 2026-08-12 復旧・トークン再ローテーション済み（公開 URL 200 継続） |
| 2 | 本番 DB の既定アカウント無効化 | 重大 | ✅ 2026-08-12 実施（carbon_admin を代替管理者として作成・無効化済み） |
| 3 | SMTP/Teams 通知未設定 | 高 | ✅ 配線・手順・スクリプト整備済み。残るは M365/Teams 資格情報の提供と実通知試験 |
| 4 | 実地 PoC（2現場）未実施 | 高 | Phase 8 計画は具体化済み。参加者・現場名の確定と 9/1 開始準備が残る |
| 5 | 排出係数の一次情報突合（電力・材料・建機等） | 高 | ✅ 台帳・反映スクリプト追加。建機・コンクリート等は現場実績値での再検証が残る |
| 6 | マイグレーション基盤（Alembic）導入 | 中 | スキーマ変更の運用管理 |
| 7 | E2E（Playwright 等）・負荷試験 | 中 | 主要画面の自動操作と性能確認 |
| 8 | トークン有効期限 12h・リフレッシュ/失効機能 | 中 | 認証設計の拡張 |
| 9 | 監査ログへの IP・UA 記録 | 低 | ログ項目拡張 |
| 10 | ライセンスファイル・NOTICE 整備 | 低 | 依存ライセンスの整理 |

## 2026-08-14 追記（MVP 後）

| # | 課題 | 影響度 | 備考 |
|---|---|---|---|
| 11 | ブラウザ E2E（Playwright）・負荷試験 | 中 | MVP レビュー後・本番 PoC 前に実施 |
| 12 | 実 SMTP/Teams 通知試験 | 高 | M365 資格情報提供待ち |
| 13 | 実地 PoC（2現場） | 高 | 9/1 開始予定のまま |
