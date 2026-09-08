---
title: "SoTを二重化してAIエージェントに壊された話 — READMEとconfig、どちらが正か問題"
emoji: "🪞"
type: "tech"
topics: ["個人開発", "設計", "ドキュメント", "githubactions"]
published: true
---

## 何が起きた

個人開発の自動化スクリプトで、実行スケジュールを `README.md` に「毎日 09:00 JST に走る」と書いていた。
一方で GitHub Actions の `cron` は UTC で `0 0 * * *`(= JST 09:00)にしていた。ここまでは正しい。

ある日、AI エージェントに「実行時間を朝 7 時に変えたい」と依頼した。エージェントは `.github/workflows/*.yml` の `cron` を素直に書き換えた。しかし README の記述はそのまま。次に別の作業を頼んだとき、エージェントは README を読んで「このジョブは 9:00 に走る」と信じ、9:00 前提のログ整形処理を追加した。

結果、実際は 7:00 に走るのに、7:00 のログが「昨日のぶん」として扱われるという、地味に気付きにくいズレが生まれた。気付いたのは数日後、集計値がなんとなく合わないと感じたときだった。

## 真因

これは「AI が README を読み違えた」話ではない。真因は構造にある。

**同じ事実(実行時刻)が、README と yml の 2 箇所に、手で書かれていた。**

SoT(Source of Truth) が二重化していると、片方を更新したときにもう片方が古くなる。人間の運用でも起きるが、AI エージェントは「読める場所を全部読んで、それぞれを事実として扱う」ので、齟齬があると片方を信じて別の変更を積む。しかも自然言語(README)とコード(yml)では、AI は文脈的に自然言語の方を優先することがある。

つまり問題は「AI が間違えた」ではなく、**間違えられる余地を自分で用意していた**こと。

## 防止装置

原則は 1 つだけ。

> 同じ情報を 2 箇所に置かない。どうしても 2 箇所に見せたいなら、片方は「生成物」にする。

具体的には、yml を SoT にして、README の該当箇所は生成する。

### 1. README にマーカーを埋める

````markdown
<!-- AUTOGEN:SCHEDULE START -->
<!-- ここは自動生成されます。手で編集しないでください。SoT は .github/workflows/daily.yml -->
<!-- AUTOGEN:SCHEDULE END -->
````

### 2. 生成スクリプト(yml から README を書き換える)

```python
# scripts/sync_readme.py
import re, yaml, pathlib
from datetime import datetime, timezone, timedelta

WF = pathlib.Path(".github/workflows/daily.yml")
README = pathlib.Path("README.md")

wf = yaml.safe_load(WF.read_text())
cron_utc = wf["on"]["schedule"][0]["cron"]  # 例: "0 0 * * *"

m, h, *_ = cron_utc.split()
jst = (datetime(2000, 1, 1, int(h), int(m), tzinfo=timezone.utc)
       + timedelta(hours=9))
line = f"- 実行時刻: 毎日 {jst.strftime('%H:%M')} JST (cron: `{cron_utc}` UTC)"

text = README.read_text()
new = re.sub(
    r"(<!-- AUTOGEN:SCHEDULE START -->)(.*?)(<!-- AUTOGEN:SCHEDULE END -->)",
    rf"\1\n{line}\n\3",
    text, flags=re.DOTALL,
)
README.write_text(new)
```

### 3. CI で「生成物がズレていないか」だけをチェックする

```yaml
# .github/workflows/verify-sot.yml
name: verify-sot
on: [pull_request, push]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install pyyaml
      - name: regenerate README section
        run: python scripts/sync_readme.py
      - name: fail if README is stale
        run: |
          if ! git diff --exit-code README.md; then
            echo "README のスケジュール記述が yml と一致していません。"
            echo "ローカルで 'python scripts/sync_readme.py' を実行してコミットしてください。"
            exit 1
          fi
```

これで、

- SoT は `daily.yml` の 1 箇所だけ
- README に見えているのは「生成物」なので、手で書き換えられても CI が落ちる
- AI エージェントが README を読んでも、それは常に yml と一致している

という状態になる。AI に「README を直接編集して」と頼まれても、CI が防波堤になる。

## 学び

- 「同じ情報を 2 箇所に書く」は、その瞬間はコストが安く見える。壊れるのは未来。
- SoT を 1 つに決められないときは、**片方を人間が編集する場所、もう片方を自動生成される場所**に分ける。両方が手書きなのが一番危ない。
- AI エージェントを前提にすると、この設計原則はさらに重くなる。エージェントは「読める場所を全部読む」ので、矛盾は矛盾のまま次の変更に持ち込まれる。
- 防止装置は難しい仕組みでなくていい。マーカー + 生成スクリプト + `git diff --exit-code` の CI、この 3 点セットで十分効く。

自分の場合、これに気付くまで数日ぶんの集計を手で見直すはめになった。同じ罠の前の人へ届けば。
