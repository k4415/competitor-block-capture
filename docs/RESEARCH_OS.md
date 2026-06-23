# 比較リス リサーチOS

## コンセプト

ジャンルごとにNotion親ページを作り、その中にリサーチDBを集約する。V2は「調査計画 -> ソース収集 -> 個別抽出 -> 根拠検証 -> Notion投入」に分割し、カテゴリー、ターゲット、メインプレイヤー、競合比較サイトを別々に抽出する。

## V2 Notion構造

- 親ページ: `{カテゴリ名} 比較リスティング調査 V2`
- inline DB: `カテゴリーリサーチ`
- inline DB: `ターゲットリサーチ`
- inline DB: `メインプレイヤーリサーチ`
- inline DB: `競合比較サイトリサーチ`

各DBは日本語プロパティで `事実 / 大項目 / 小項目 / セグメント / 根拠URL / 根拠タイトル / 短い引用 / 信頼度 / 検証状態 / 取得日時 / リサーチRun ID` を持つ。メインプレイヤーDBは `サービス名 / 公式URL / 価格 / プラン / 会員数 / 実績 / オファー` を追加する。競合比較サイトDBは `URL / ドメイン / 構成タイプ / ランキング1-5 / 主要CTA / 掲載サービス / 直接競合 / 画像内主要文言` を追加する。

## 実行方式

1. `research_os run-v2` でカテゴリと競合URLからV2親ページと4DBを作る。
2. `--replace-v1` を付けるとResearch OSが作成したV1ページをtrashしてからV2を作る。
3. 結婚相談所ではV2のseedソースを使い、最低限のカテゴリー/ターゲット/主要プレイヤー網羅を確保する。
4. 競合URLはPlaywrightが利用可能ならレンダリング取得し、未導入ならHTML取得にフォールバックする。
5. Web UIは `uvicorn research_os.web:app` で起動し、V2実行と `V1削除して再作成` を既定にする。

```bash
python3 -m research_os run-v2 \
  --category-name 結婚相談所 \
  --memo '比較リスティング向け。直接競合3URLを重点調査。' \
  --competitor-url https://konkatsu-navi.info/ranking/ \
  --competitor-url https://best-marriage.com/top5/ \
  --competitor-url https://soudanjo-hikaku.com/ \
  --replace-v1 \
  --out artifacts/research-os-v2-marriage-agency-run.json
```

## 安全ルール

- 競合サイト本文を丸ごと転載しない。
- `短い引用` は短い根拠引用に制限する。
- URLがない事実はNotion行にしない。
- APIキー、内部ログ、長い本文、個人情報はNotionに入れない。
- 競合サイトページ本文は `構成順 / 見出し / ランキング / CTA / 掲載サービス / 画像内主要文言 / 比較軸 / 証拠表現 / 訴求パターン` に構造化して保存する。
