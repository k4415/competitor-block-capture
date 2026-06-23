# Notion DB設計

`CMOAI v9 0` 配下に以下の10DBを作る想定です。実際のAPI投入payloadは `python3 -m listing_os init-schema` で生成できます。

## DB一覧

1. `ジャンル`: 比較リス案件の立ち上げ単位。
2. `検索クエリ`: SERP/API収集対象。
3. `SERPスナップショット`: 取得日時、provider、device、raw result数。
4. `競合サイト`: ドメイン重複排除後の競合リスト。
5. `ASP/案件`: 報酬、承認条件、訴求可能/NG表現。
6. `訴求インサイト`: 競合、案件、ターゲット調査からの示唆。
7. `比較LP構成案`: ランキング軸、Hero、CTA、承認状況。
8. `外注指示パック`: Figma/コーディング外注への共有単位。
9. `制作タスク`: デザイン、コーディング、レビュー、公開。
10. `運用結果`: 費用、CV、CPA、学習、次アクション。

## Notion API実装方針

Notion API `2026-03-11` では、DB作成時のプロパティは `initial_data_source.properties` に入れます。relationは参照先の `data_source_id` が必要なため、CLIは次の順で処理します。

1. relation以外のプロパティで全DBを作成
2. 各DBの `data_source_id` を取得
3. relationプロパティを `PATCH /v1/data_sources/{data_source_id}` で追加

V1のrelationは片方向で十分なため、更新payloadは `{"relation": {"data_source_id": "...", "single_property": {}}}` の形にします。

Notion操作ツールが使えない環境では、まず `artifacts/notion-schema.json` を生成し、Notion APIキーが使える環境で `--create` を実行します。

## 運用ビュー案

- `ジャンル`: Priority別、Status別、今週立ち上げ。
- `検索クエリ`: Enabledのみ、Intent別。
- `競合サイト`: Score順、Genre別。
- `外注指示パック`: Ready/Sent/Delivered別。
- `制作タスク`: Assignee別、Due Date別。
- `運用結果`: Genre別、CPA昇順、Learningあり。
