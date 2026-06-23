# 運用手順

## dry-run

Notionへ保存せず、ローカルJSONと画像だけを確認します。

```bash
python3 -m research_os capture-blocks \
  --category-name マウスピース矯正 \
  --competitor-url https://example.com/ \
  --dry-run \
  --out artifacts/block-capture-dry-run.json
```

## Notionへ保存

```bash
python3 -m research_os capture-blocks \
  --category-name マウスピース矯正 \
  --competitor-url https://example.com/ \
  --reference-review \
  --out artifacts/block-capture-notion.json
```

## 複数URLをまとめて実行

`urls.txt` に1行1URLで保存します。

```bash
python3 -m research_os capture-blocks \
  --category-name マウスピース矯正 \
  --competitor-url-file urls.txt \
  --reference-review \
  --out artifacts/block-capture-notion.json
```

## 参照レビューだけ厳しくする

参照DBとのズレがある場合に保存を止めたいときだけ使います。

```bash
python3 -m research_os capture-blocks \
  --category-name マウスピース矯正 \
  --competitor-url https://example.com/ \
  --reference-review \
  --fail-on-reference-warning \
  --out artifacts/block-capture-notion.json
```

## フィードバックを学習候補にする

`feedback.txt` にユーザーの指摘を書きます。

```bash
python3 -m research_os learn-block-feedback \
  --run-artifact artifacts/block-capture-notion.json \
  --feedback-file feedback.txt \
  --out learning/pending_rules.json
```

`pending_rules.json` を確認し、次回から自動適用してよいものだけ `learning/approved_rules.json` に移してください。

## テスト

```bash
python3 -m unittest discover -s tests -v
```
