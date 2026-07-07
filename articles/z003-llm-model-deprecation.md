---
title: "LLM の model 名をコードに直書きしていたら、deprecation で全機能が同時に落ちた話"
emoji: "🪦"
type: "tech"
topics: ["llm", "api", "claude", "openai", "個人開発"]
published: true
---

## 何が起きた

個人で回している複数の自動化スクリプト(要約 bot、日次レポート生成、Slack への通知)を、ある朝まとめて確認したら全部同じエラーで死んでいた。

```
model: xxx-xxx-2024xxxx has been deprecated
```

原因は 1 つ。deprecation の告知は事前に出ていた。ただ、私はそれを個別スクリプトの中で見逃していた。

なぜ「全部」同時に落ちたか。model 名を、それぞれのスクリプトの中に文字列でハードコードしていたから。しかも同じ model を使っていたので、同じ日に、同じエラーで、同時に沈黙した。

## 真因(表面ではなく構造)

表面的な原因は「deprecation の告知を見落とした」。だがこれは真因ではない。真因は 2 つある。

**1. model 名という「揮発する定数」を、コードに埋め込んでしまっていた**

model 名は、一見「定数」に見える。`"claude-..."` とか `"gpt-..."` とか、いかにも変わらなさそうな文字列だ。だから何も考えず `client.messages.create(model="claude-...", ...)` と書く。

でも LLM の model 名は定数ではない。**バージョン付きの API エンドポイントに近い、揮発する識別子**だ。半年〜1 年で deprecate される前提で扱うべきものを、私は "MAX_RETRY = 3" と同じ気分でコードに直書きしていた。

**2. 鮮度を確認する定例プロセスがなかった**

依存関係の更新は Dependabot が見てくれる。でも「使っている model が今も推奨されているか」を教えてくれる仕組みを、私は用意していなかった。プロバイダのブログを RSS で追ってはいたが、「後で見る」が積もって、届いていない通知と同じ状態になっていた。

つまり「1 箇所に集約されていない」×「鮮度を強制的にチェックする装置がない」の掛け算で、静かに時限爆弾が仕掛かっていた。

## 防止装置

### 1. model 名を env と 1 つの設定ファイルに集約する

まず、コードから model 名の文字列を全部剥がす。参照は必ず 1 つのモジュール経由にする。

```python
# config/models.py
import os

# デフォルトはコードで持ちつつ、env で上書きできるようにする
MODELS = {
    "chat_main":   os.getenv("MODEL_CHAT_MAIN",   "claude-xxx-latest"),
    "chat_cheap":  os.getenv("MODEL_CHAT_CHEAP",  "claude-xxx-haiku-latest"),
    "embedding":   os.getenv("MODEL_EMBEDDING",   "text-embedding-xxx"),
}

def get_model(role: str) -> str:
    if role not in MODELS:
        raise KeyError(f"unknown model role: {role}")
    return MODELS[role]
```

呼び出し側はこう:

```python
from config.models import get_model

resp = client.messages.create(
    model=get_model("chat_main"),
    messages=[...],
)
```

こうしておくと、deprecation 通知が来たときに **env を書き換えるだけで全スクリプトが追従する**。roll back も env を戻すだけ。

`.env.example` に role を列挙しておくと、新しい環境を作るときにも忘れない:

```bash
# .env.example
MODEL_CHAT_MAIN=claude-xxx-latest
MODEL_CHAT_CHEAP=claude-xxx-haiku-latest
MODEL_EMBEDDING=text-embedding-xxx
```

### 2. 鮮度を強制的にチェックする GitHub Actions

集約しても、「今使っている model がまだ生きているか」を人間の記憶に頼るのは同じ罠だ。週次で軽く叩いて、死んでいたら Issue を立てる。

```yaml
# .github/workflows/model-healthcheck.yml
name: model-healthcheck

on:
  schedule:
    - cron: "0 0 * * 1"  # 毎週月曜 UTC 00:00
  workflow_dispatch:

jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install anthropic openai
      - name: ping each model
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OPENAI_API_KEY:    ${{ secrets.OPENAI_API_KEY }}
          MODEL_CHAT_MAIN:   ${{ vars.MODEL_CHAT_MAIN }}
          MODEL_CHAT_CHEAP:  ${{ vars.MODEL_CHAT_CHEAP }}
          MODEL_EMBEDDING:   ${{ vars.MODEL_EMBEDDING }}
        run: python scripts/model_healthcheck.py
      - name: open issue on failure
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: "⚠️ model healthcheck failed",
              body: "週次の model 疎通に失敗しました。deprecation の可能性あり。"
            })
```

`scripts/model_healthcheck.py` は本当に最小でいい。1 トークンだけ返させて、例外が飛んだら非ゼロ終了する程度。

```python
# scripts/model_healthcheck.py
import os, sys
from anthropic import Anthropic

client = Anthropic()

roles = ["MODEL_CHAT_MAIN", "MODEL_CHAT_CHEAP"]
failed = []
for r in roles:
    model = os.environ[r]
    try:
        client.messages.create(
            model=model,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        print(f"ok: {r}={model}")
    except Exception as e:
        print(f"fail: {r}={model} -> {e}")
        failed.append(r)

if failed:
    sys.exit(1)
```

これで、deprecation が発表された時点(実際に呼べなくなる前)か、遅くとも切れた翌週の月曜に Issue が立つ。**「気づく前提」から「気づかされる前提」に構造を切り替える**のがポイント。

## 学び

- LLM の model 名は定数ではない。**バージョン付きの揮発する識別子**として、env と 1 つの設定モジュールに閉じ込める。
- 「複数箇所にコピペした文字列」は、いつか同時に落ちる。同時に落ちて初めて、それが同じものだったと気づく。
- 鮮度チェックを cron でリポジトリの中に置く。プロバイダのブログを覚えておく、は仕組みではない。

同じ日の朝に、全機能から同じ deprecation エラーを浴びた人へ、少しでも早く届けば。
