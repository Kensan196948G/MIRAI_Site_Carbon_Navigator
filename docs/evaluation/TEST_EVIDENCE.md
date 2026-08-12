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
