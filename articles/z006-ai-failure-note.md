---
title: "AIに雑に投げると『早合点した提案』が返り続ける問題を、受入条件テンプレで止める"
emoji: "🧭"
type: "tech"
topics: ["ai", "claude", "プロンプト", "個人開発", "githubactions"]
published: true
---

## 何が起きた

個人開発の自動化スクリプトを直したくて、AI にこう投げた。

> 「このスクリプト、たまにコケるから直して」

返ってきたのは、それっぽいリファクタ案。try/except を足し、リトライを入れ、ログを整え、ついでに構成まで一部書き換えてくれていた。

一見親切。だが自分が直したかったのは「特定 API のレート制限で 429 が返ったときだけ、指数バックオフでリトライする」という一点だけだった。それ以外は触ってほしくなかった。

追加で「そこじゃなくて〜」と補足すると、今度は別方向に走り出す。会話ログだけがどんどん伸びて、元の一行の修正が終わらない。半日溶かした。

## 真因

表面上は「AI が早合点した」だが、構造はそうじゃない。

- 自分が「たまにコケる」としか言っていない
- どの例外か、どの頻度か、何を触っていいか、何を触ってはいけないか、どうなったら完了か、を一つも渡していない
- 曖昧な入力に対しては、AI は「たぶんこれだろう」で最大公約数の親切を返すしかない

つまり **曖昧入力 → 曖昧出力**。AI の推論が悪いのではなく、受入条件(Acceptance Criteria)を人間側が持っていない状態で委任していたのが真因。

これは対人でも同じで、要件を固めずに「いい感じにお願い」と投げると、返ってくる成果物にどれだけダメ出ししても収束しない。AI 相手だと会話コストが安いぶん、この「発散」に気付きにくい。

## 防止装置

「頼む前に埋めるテンプレ」をリポジトリ側に置いて、AI に投げる前に必ず通す。頭の中でやろうとすると省略するので、ファイル化する。

### 1. リポジトリに置く依頼テンプレ

`.github/PROMPT_TEMPLATE.md` として置いておく。issue でも PR の下書きでもコピペで使う。

```markdown
## 目的(1行)
<何を達成したいか。手段ではなくゴール>

## 前提
- 対象ファイル / 関数:
- 実行環境(ランタイム, バージョン):
- 依存(外部 API, ライブラリ):

## 制約(触ってはいけないもの)
- [ ] 公開インターフェースは変更しない
- [ ] 依存の追加は禁止 / 許可(どちらか明記)
- [ ] スタイル/整形の差分は含めない
- その他:

## 再現条件
- 入力:
- 期待:
- 実際:
- 頻度 / トリガ:

## 受入条件(これが満たされたら完了)
- [ ] <観測可能な条件1>
- [ ] <観測可能な条件2>
- [ ] 既存テストが通る / 追加テストがある

## 出力形式
- diff / full file / 説明のみ のいずれか
```

ポイントは「制約」と「受入条件」を分けていること。**やってほしいこと**より、**やらないでほしいこと**と**完了の判定条件**のほうが早合点を防ぐ。

### 2. AI に投げる前にテンプレの空欄を検出する

空欄のまま投げるのが人間の弱さなので、機械的に止める。`scripts/check_prompt.py`:

```python
#!/usr/bin/env python3
"""AI依頼前のテンプレ空欄チェック。空欄があれば非0で終了する。"""
import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = ["目的", "前提", "制約", "再現条件", "受入条件", "出力形式"]

def main(path: str) -> int:
    text = Path(path).read_text(encoding="utf-8")
    missing = []
    for name in REQUIRED_SECTIONS:
        # セクション見出しの次〜次の見出しまでを抜き出す
        m = re.search(rf"##\s*{name}.*?\n(.*?)(?=\n##\s|\Z)", text, re.S)
        if not m or not re.search(r"[^\s\-\[\]\(\)<>のか。、]", m.group(1)):
            missing.append(name)
    if missing:
        print("未記入セクション:", ", ".join(missing))
        return 1
    print("OK: 依頼テンプレは埋まっています")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ".github/PROMPT_TEMPLATE.md"))
```

使い方:

```bash
python scripts/check_prompt.py drafts/fix-retry.md && \
  echo "→ このファイルを AI に投げる"
```

### 3. GitHub Actions で PR にテンプレ埋め込みを強制する

PR 本文に上記セクションが揃っていない状態でマージされるのを防ぐ。`.github/workflows/prompt-check.yml`:

```yaml
name: prompt-template-check
on:
  pull_request:
    types: [opened, edited, synchronize]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - name: Verify PR body has acceptance criteria
        env:
          BODY: ${{ github.event.pull_request.body }}
        run: |
          for s in "目的" "制約" "再現条件" "受入条件"; do
            if ! echo "$BODY" | grep -q "## $s"; then
              echo "PR本文に「## $s」がありません"
              exit 1
            fi
          done
          echo "OK"
```

これで「頭の中だけで AI にお願いする」ルートが物理的に塞がる。自分ひとりのリポでも意味がある。むしろ一人だからこそ意味がある。

## 学び

- 「たまにコケる」「いい感じに直して」は、依頼ではなく愚痴に近い。愚痴を投げると愚痴が返ってくる
- AI の出力の質は、モデルより先に **受入条件の解像度** で決まる
- 受入条件は頭の中に置くと必ず省略するので、ファイル化して機械的に空欄検出する
- 制約(触らないでほしいもの)を明記すると、早合点の面積が一気に減る

同じように AI との会話ログだけが伸びていく人へ、届けば。
