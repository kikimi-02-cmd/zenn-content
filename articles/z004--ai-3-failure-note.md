---
title: "自動生成した記事が『AIっぽさ』で全部見抜かれた話 — テンプレ硬直を壊す3つの装置"
emoji: "🎭"
type: "tech"
topics: ["生成ai", "個人開発", "ライティング", "githubactions", "自動化"]
published: true
---

## 何が起きた

個人開発で、あるジャンルの解説記事を自動生成して毎日1本投稿するパイプラインを組んだ。GitHub Actions で cron を回し、OpenAI の API にプロンプトを投げ、Markdown を吐き出して Zenn/ブログにデプロイする。よくある構成。

最初の1〜2本は自分でもよく書けていると思った。ところが1週間続けたあたりで、コメントやアクセス解析からじわじわ気配が出てくる。

- 直帰率が明らかに高い
- 「これAIですよね?」というコメントが付く
- 過去記事をまとめて開くと **全部同じ顔をしている**

自分で並べて読んで確信した。個々の記事は悪くない。並べると全部同じ骨格なのだ。

- 導入: 「近年、〜が注目されています。」
- 本論: 見出し3つ、それぞれ「〜とは」「メリット」「注意点」
- 結論: 「いかがだったでしょうか。ぜひ試してみてください。」

これは1本ずつ読んで判断されているのではなく、**時系列に並んだ複数本の類似度で見抜かれている**。

## 真因: プロンプトが一つしかなかった

表面的な原因は「文体がAIっぽい」だが、これは対症療法しか生まない(語尾を変える、絵文字を入れる、等)。本当の原因は構造の側にあった。

1. **プロンプトが1個しかない**
   毎回同じシステムプロンプトを投げていたので、モデルの出力分布の中心が固定される。同じ場所から毎日サンプリングすれば、当然似た形が出る。

2. **入力の実データが薄い**
   トピックだけ渡して「書いて」と頼んでいた。モデルは自分の学習分布の一番安全な平均値を返してくる。平均値は当然、他の生成物とも似る。

3. **固定の締めがある**
   最後の一段落を「まとめ」テンプレで埋めていた。ここが全記事で最も似る。読者が「またこれか」と気づく場所は、だいたい終盤。

つまり **「型が1つ・実データが無い・締めが固定」** の三重で、生成物が同じ分布に収束していた。一つずつ壊す。

## 防止装置

### 装置1: 記事の「型」をローテーションする

プロンプトを配列にして、日付か記事IDで決定的に選ぶ。乱数ではなく決定的にするのは、同じ記事を再生成しても結果が変わらないようにするためと、後で「どの型で書いたか」を追跡するため。

```python
# templates.py
TEMPLATES = [
    {
        "id": "howto",
        "system": "あなたは実践重視のエンジニア。手順→つまずき→回避 の順で書く。まとめ段落は書かない。最後は次に試すことを1つだけ提示する。",
        "outline": ["前提と再現手順", "実際にハマった箇所", "回避のスニペット", "次に試すこと"],
    },
    {
        "id": "postmortem",
        "system": "失敗の記録として書く。時系列で事実→解釈→対策の順。感想は書かない。",
        "outline": ["起きたこと", "気づいた瞬間", "原因の切り分け", "残っている疑問"],
    },
    {
        "id": "compare",
        "system": "2つ以上の選択肢を、評価軸を先に宣言してから比較する。結論は表で示す。",
        "outline": ["評価軸の定義", "各選択肢の実挙動", "スコア表", "自分ならどれを選ぶか"],
    },
    {
        "id": "log",
        "system": "作業ログの体で書く。時刻・コマンド・出力の断片を含める。締めの挨拶は禁止。",
        "outline": ["環境", "実行ログ", "観測されたもの", "次のログで追いたいこと"],
    },
]

def pick_template(seed: str):
    # 日付やタイトルから決定的に選ぶ
    import hashlib
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    return TEMPLATES[h % len(TEMPLATES)]
```

型ごとに **見出し構成・禁止事項・締め方** を変える。特に「まとめ段落を書かない」「締めの挨拶は禁止」を明示するのが効く。モデルは放っておくと必ず「いかがでしたか」に戻る。

### 装置2: 実データを必ず注入する

トピック文字列だけを渡すのをやめる。ジャンルに応じて、その時点で取れる **具体的な数字・引用・実例** を必ずプロンプトに混ぜる。個人開発なら以下が現実的。

- 自分のリポの直近コミットログ
- 公開 API から取った最新値
- 自分の実行ログ・エラーメッセージ
- 過去記事の見出し一覧(重複回避のため)

```python
def build_user_prompt(topic: str, template: dict, facts: dict, past_titles: list[str]) -> str:
    return f"""
テーマ: {topic}
使う型: {template["id"]}
必ず含める見出し: {template["outline"]}

以下の事実を本文に最低3つ埋め込むこと。創作しないこと。
FACTS:
{facts}

過去に書いた見出しと似た構成は禁止:
{past_titles[-30:]}

締めは型の指示に従うこと。「まとめ」「いかがでしたか」等の定型句は使用禁止。
"""
```

「創作しないこと」と「事実を最低N個埋める」をセットで書くのが要点。事実の粒が入ると、文体が事実に引っ張られて平均から外れる。

### 装置3: 締めの固定を検知して落とす

生成後にリンター的なチェックを挟む。禁止フレーズと、過去記事との類似度をゲートにする。

```python
# lint.py
BANNED_ENDINGS = [
    "いかがでしたか",
    "いかがだったでしょうか",
    "ぜひ試してみてください",
    "参考になれば幸いです",
    "まとめると",
]

def lint_article(md: str, past_articles: list[str]) -> list[str]:
    errors = []
    tail = md.strip()[-300:]
    for phrase in BANNED_ENDINGS:
        if phrase in tail:
            errors.append(f"banned_ending: {phrase}")

    # 過去記事の末尾との類似度(簡易: 末尾200文字の共通n-gram率)
    from difflib import SequenceMatcher
    for past in past_articles[-20:]:
        ratio = SequenceMatcher(None, md[-200:], past[-200:]).ratio()
        if ratio > 0.6:
            errors.append(f"tail_too_similar: {ratio:.2f}")
            break
    return errors
```

### 装置4: PR ゲートで自動公開を止める

失敗が怖いのは、cron で自動生成 → 自動公開まで一気通貫にしてしまう構成。生成は自動、公開は手動 PR マージ、と切り分ける。

```yaml
# .github/workflows/generate.yml
name: generate-draft
on:
  schedule:
    - cron: "0 22 * * *"  # 毎日1回、下書きだけ作る
  workflow_dispatch:

jobs:
  draft:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - name: generate
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: python scripts/generate.py

      - name: lint
        run: python scripts/lint.py articles/*.md

      - name: open PR
        uses: peter-evans/create-pull-request@v6
        with:
          branch: draft/${{ github.run_id }}
          title: "draft: ${{ github.run_id }}"
          body: |
            自動生成の下書き。lint 済み。
            人間が読んでからマージしてください。マージ時に公開されます。
          labels: draft, auto-generated
```

公開側のワークフローは `on: push: branches: [main]` にしておく。**PR マージ = 公開** という単純な線を引いておけば、暴走しても本番には出ない。

## 学び

- 「AIっぽさ」は1本ごとの文体の問題ではなく、**複数本を並べたときの構造の同一性**として現れる。だから文体を弄っても直らない。
- 型を1つに固定するのは、モデルの出力分布の中心にわざわざ通うのと同じ。**型のローテーション**と**実データの注入**で分布の外側を引き出す。
- 締めは最も似る場所なので、最も強く禁止する。「まとめない勇気」がいる。
- 自動生成は速度が武器だが、**公開だけは人間の PR マージに残す**。速度を捨てるのではなく、責任の線をそこに引くだけ。

同じ罠の前の人へ、この記録が届けば。
