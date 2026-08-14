# MVP/Prototype レビュー環境

関係者レビュー用の MVP/Prototype 環境です。**本番（https://carbon.mirai-dx-platform.com）とは完全に分離**しており、表示されるデータはすべて架空のダミーデータです。

## 1. URL

| 環境 | URL | 用途 |
|---|---|---|
| 本番 | https://carbon.mirai-dx-platform.com | 既存の運用環境（本タスク対象外） |
| **MVP/Prototype** | **https://carbon-mvp.mirai-dx-platform.com** | 関係者レビュー・デモ用 |

MVP は FastAPI（uvicorn）+ SQLite（`mvp_data/mirai_carbon_mvp.db`）で動作します。
Cloudflare Tunnel（`mirai-carbon-mvp`）経由で公開しています。

## 2. ログインアカウント（架空・開発用）

| ユーザー名 | パスワード | ロール | 確認できるデモ |
|---|---|---|---|
| demo_admin | DemoAdmin!2026 | CarbonAdmin | 全画面・ユーザー管理・係数・クレジット無効化 |
| demo_reviewer | DemoReviewer!2026 | EnvironmentReviewer | 承認フロー（branch → env）・監査ログ |
| demo_site_tokyo | DemoSiteTokyo!2026 | SiteInput（東京支店） | 東京工事のみの入力・提出・削減アクション |
| demo_site_osaka | DemoSiteOsaka!2026 | SiteInput（大阪支店） | 大阪工事のみ（支店境界の確認用） |
| demo_client | DemoClient!2026 | Client（発注者） | 割当工事 2 件の閲覧のみ・PDF 受領 |

> これらのパスワードはデモ専用のダミーです。本番では使用できません（本番は既定アカウント無効化済み）。

## 3. デモデータ構成（全て架空）

`python scripts/seed_mvp_demo.py` で再生成可能です（冪等）。

| 項目 | 内容 |
|---|---|
| 工事 | 【デモ】MIRAI港湾護岸工事（東京支店・港湾工事）、【デモ】MIRAI道路改良工事（大阪支店・道路工事） |
| 活動量 | 2026-01〜07 の通常データ + 2026-08 の承認ワークフロー用データ（draft / site_submitted / branch_approved） |
| 異常値 | A重油 2026-03=100L → 2026-04=20,000L（前月比 200 倍で検知） |
| 未算定 | 「試験用特殊鋼材」は排出係数なし（missing-factors 表示の確認用） |
| 締め | 両工事とも 2026-03 を締め済み（締め後ロックの確認用） |
| SBTi | Scope1/2/3 目標 3 件（架空目標） |
| クレジット | J-クレジット 2 件（うち 1 件を港湾工事に充当）+ 再エネ証書 1 件（無効化済み） |
| 通知・監査 | ロール/ユーザー向け通知 5 件、監査ログ多数 |
| 発注者ポータル | demo_client に 2 工事を割当済み |

## 4. セットアップ手順（再構築時）

```bash
# 1) ローカル起動（開発モード・ダミーデータ自動投入）
scripts/start_mvp.sh          # http://127.0.0.1:8021

# 2) 公開（初回のみ）
scripts/setup_mvp_tunnel.sh   # トンネル + DNS + systemd ユニットを自動作成

# 3) 動作確認
scripts/smoke_mvp.sh
```

systemd（user セッション）:

| サービス | 内容 |
|---|---|
| `mirai-carbon-mvp.service` | MVP バックエンド（uvicorn 127.0.0.1:8021） |
| `mirai-carbon-mvp-cloudflared.service` | MVP トンネル（carbon-mvp.mirai-dx-platform.com） |

## 5. 既知の制約

- MVP は SQLite 単一ファイルのため、同時利用者は少数（レビュー用途）を想定。
- SMTP/Teams 通知は本番設定を共有せず、MVP では DB 内通知のみ有効。
- デモ用パスワードはリポジトリに記載された固定値です（開発・レビュー専用）。
- データはすべて架空であり、実在の人物・会社・金額・位置情報を含みません。
