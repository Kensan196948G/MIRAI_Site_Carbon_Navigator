# MIRAI Site Carbon Navigator

## 🎯 プロジェクト概要

**MIRAI Site Carbon Navigator** は、工事別のCO2排出量を自動算定し、削減施策まで提示する脱炭素支援システムです。

船舶、建機、燃料、材料、輸送、電力のデータを集め、SBTiやSDGsの取り組みを現場改善と発注者提案へ接続します。

## 🌱 全体像

```mermaid
flowchart TB
  Fuel["燃料・給油"] --> Calc["CO2算定エンジン"]
  Material["材料数量"] --> Calc
  Transport["輸送・配車"] --> Calc
  Power["電力"] --> Calc
  Machine["船舶・建機稼働"] --> Calc
  Calc --> Dashboard["工事別ダッシュボード"]
  Calc --> Report["発注者・社内レポート"]
  Calc --> Navi["削減ナビ"]
  Navi --> Action["現場改善アクション"]
```

## 🧩 MVPスコープ

| 項目 | 内容 |
|---|---|
| 対象 | 港湾工事1件、陸上工事1件 |
| データ | 燃料、主要材料、輸送距離、現場電力 |
| 出力 | 工事別CO2、月次推移、削減候補 |
| 方式 | Excel/CSV取込 + Web/BI画面 |
| レビュー | 環境担当・現場所長による月次確認 |

## 👥 役割分担

| 担当 | 役割 |
|---|---|
| PM | 算定ルール、データ設計、全体設計 |
| ノーコード担当 | 入力フォーム、月次確認画面 |
| 元システム管理者 | CSV収集、ファイル置場、権限 |
| プログラミング担当 | 排出係数マスタ、算定ロジック |
| 部長 | 環境部門・現場部門との調整 |

## 🗺 ロードマップ

```mermaid
gantt
  title MIRAI Site Carbon Navigator Roadmap
  dateFormat YYYY-MM-DD
  section Phase 1
  算定範囲定義             :a1, 2026-06-01, 14d
  排出係数マスタ整備       :a2, after a1, 14d
  section Phase 2
  取込テンプレート作成     :b1, after a2, 14d
  CO2算定MVP              :b2, after b1, 21d
  section Phase 3
  2現場PoC                :c1, after b2, 30d
  削減ナビ追加             :c2, after c1, 21d
```

## ✅ 成功指標

- CO2算定に必要な月次集計時間を50%削減
- 工事別CO2を月次で可視化
- 削減施策を現場単位で3件以上提示
- 発注者向け環境提案資料に転用可能

## 📄 関連ドキュメント

- [要件定義書](./requirements.md)
- [詳細設計仕様書](./detailed-design.md)
