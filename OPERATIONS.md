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

## ユーザーOK後にNotionへ保存

dry-runで作成された画像を確認し、ユーザーからOKをもらった後に実行します。このコマンドは各画像から `image_text` と `Template_image_text` を生成して、画像と一緒にNotionへ保存します。

```bash
python3 -m research_os finalize-block-capture \
  --run-artifact artifacts/block-capture-dry-run.json \
  --category-name マウスピース矯正 \
  --confirm-reviewed \
  --out artifacts/block-capture-finalized.json
```

`--confirm-reviewed` は、ユーザーが画像素材を確認してOKしたことを明示するための必須フラグです。`OPENAI_API_KEY` が未設定の場合、この承認後保存は停止します。

## 複数URLをまとめて実行

`urls.txt` に1行1URLで保存します。

```bash
python3 -m research_os capture-blocks \
  --category-name マウスピース矯正 \
  --competitor-url-file urls.txt \
  --dry-run \
  --reference-review \
  --out artifacts/block-capture-dry-run.json
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
  --run-artifact artifacts/block-capture-finalized.json \
  --feedback-file feedback.txt \
  --out learning/pending_rules.json
```

`pending_rules.json` を確認し、次回から自動適用してよいものだけ `learning/approved_rules.json` に移してください。

## テスト

```bash
python3 -m unittest discover -s tests -v
```
