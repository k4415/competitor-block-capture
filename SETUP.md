# セットアップ手順

## 1. Python環境を作る

```bash
cd competitor-block-capture
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[browser]"
python3 -m playwright install chromium
cp .env.example .env
```

## 2. `.env` を設定する

```bash
NOTION_API_KEY=
COMPETITOR_BLOCK_DB_ID=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
```

`OPENAI_API_KEY` は任意です。未設定の場合、画像の構造メモと画像生成プロンプトのAI補助はスキップされますが、素材の切り出し自体は実行できます。

## 3. Notion側を準備する

1. Notionで競合サイト画像DBを作る、または既存DBを使います。
2. Notion integrationを作成します。
3. 対象DBをintegrationに共有します。
4. DB IDを `.env` の `COMPETITOR_BLOCK_DB_ID` に入れます。
5. 初回実行時に、不足しているDBプロパティはCLIが自動追加します。

## 4. 動作確認

まずはNotion保存なしのdry-runで確認します。

```bash
python3 -m research_os capture-blocks \
  --category-name マウスピース矯正 \
  --competitor-url https://example.com/ \
  --dry-run \
  --no-openai \
  --out artifacts/block-capture-dry-run.json
```

`artifacts/block-capture-dry-run.json` が作成され、`run.blocks` にブロック情報が入っていればセットアップは完了です。
