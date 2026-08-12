# セキュリティ・秘密情報・保守

## 秘密情報の取り扱い

- `.env` は Git にコミットしない（.gitignore 済み）。`.env.example` に変数名と安全な例のみ記載
- 秘密候補（APIキー、SMTPパスワード、OIDCクライアントシークレット、トンネルトークン）は画面・ログ・PR・テスト・commit に出力しない
- 秘密が漏れた場合は即時ローテーション

## 既定アカウント・本番シード（2026-08-12 変更）

- 開発用の既定ユーザー（admin/admin123 等）は `MIRAI_SEED_DEFAULT_USERS=1` のときのみ作成
- 本番（`MIRAI_SEED_DEFAULT_USERS=0`）は初回のみ `MIRAI_INITIAL_ADMIN_PASSWORD`（12文字以上）で管理者を作成
- 既存本番 DB に既定アカウントが残っている場合は以下で無効化:
  `python scripts/disable_default_users.py --deactivate`（確認は引数なしで実行）
- コンテナは本番モードで `MIRAI_SECRET_KEY` がプレースホルダーなら起動を拒否

### 本番実施記録（2026-08-12）

- 既定 4 アカウント（admin/reviewer/site/viewer）は無効化済み
- 代替管理者 `carbon_admin` を作成。初回パスワードは `/home/kensan/.mirai_carbon_admin.cred`（0600）に保存し、初回ログイン後に変更を推奨
- Tunnel は user systemd サービス化。`MIRAI_TUNNEL_TOKEN` がプロセス引数に現れるため、次回 Cloudflare ダッシュボード操作時にトークン再発行（ローテーション）を推奨

## 認証・入力の保護（2026-08-12 追加）

- ログイン失敗は 15分/10回（`MIRAI_LOGIN_MAX_FAILURES`）で一時ロック（429）
- パスワードは最小10文字
- OIDC コールバックはワンタイムコード交換方式（URL にトークン非掲載、60秒有効・使い捨て）
- 全量エクスポートはパスワードハッシュ・TOTP 秘密・oidc_sub を除外
- フロントエンド資材は自己ホスト化し、CSP は `'self'` ベース（CDN スクリプトなし）

## ローテーション手順

| 秘密 | 保管先 | ローテーション | 頻度 |
|---|---|---|---|
| `MIRAI_SECRET_KEY` | `.env` | 新値に変更→全ユーザー再ログイン | 年1回/漏えい時 |
| SMTPパスワード | `.env` | メールプロバイダで再発行 | 漏えい時/年1回 |
| Teams Webhook | `.env` | チャネルで再生成 | 漏えい時 |
| テレマティクスAPIキー | `.env` | ベンダーポータルで再発行 | 年1回 |
| OIDCクライアントシークレット | IdP管理画面 + `.env` | IdPで再発行 | 年1回 |
| Cloudflare Tunnelトークン | ホストローカル（`.env`/トンネル設定） | Tunnel再作成 | 漏えい時 |

## 証明書・ドメイン

- 証明書: Cloudflare が自動管理（エッジ証明書）。更新はCloudflare側で自動化
- ドメイン: `mirai-dx-platform.com`（Cloudflare zone、有効期限はCloudflareダッシュボードで確認）
- 期限管理: 四半期点検で証明書・ドメイン期限を確認し、運用台帳に記録

## アクセス権限の棚卸し

- 管理者・サービスアカウント・DBロール・外部連携権限を四半期ごとに棚卸し
- 不要ユーザーは管理画面「ユーザー」から無効化（clientは割当工事のみ閲覧）
- site は自支店、client は割当工事のみ参照・操作可能（2026-08-12 より API で強制）
- DB接続はアプリコンテナ内のみ（ホスト公開なし）

## 依存関係・ライセンス

- CI で `pip-audit` を実行（既知脆弱性の監視）
- OS/ランタイム更新: Docker イメージ再ビルド時に `python:3.12-slim` / `postgres:16-alpine` の更新を確認
- EOL管理: Python 3.12 / PostgreSQL 16 のEOLを四半期点検で確認
- ライセンス: 依存パッケージのライセンス一覧を年次確認（`pip-licenses` 等）
