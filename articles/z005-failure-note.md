---
title: "自分で決めたコーディングルールを、その日のうちに自分で破った話"
emoji: "🚧"
type: "tech"
topics: ["個人開発", "自動化", "ci", "githubactions", "lint"]
published: true
---

## 何が起きた

朝、`CONTRIBUTING.md` に「コミット前に必ず `pnpm test` を通す」「秘密情報は `.env` に入れて `.env.example` を更新する」「TODO コメントは残さない」の3つを追記した。自分ひとりのリポだ。読むのも守るのも自分だけ。

夜、動作確認のために書いた検証用スクリプトを `main` に直接 push した。

翌朝ログを見返すと、そのコミットには次が全部入っていた。

- テストを走らせないまま push(急いでいた)
- 一時的に API キーをハードコード(あとで消すつもりだった)
- `// TODO: あとで消す` の行が3つ

自分で書いたルールを、ルールを書いた日のうちに全部踏んだ。

## 真因

最初は「気の緩み」で片付けそうになった。だが同じ失敗を繰り返す構造を疑うと、原因は自分の意志ではなかった。

**ルールを人間の読める文章にしか落としていなかった。**

`CONTRIBUTING.md` はコミット時に何も止めてくれない。ドキュメントは「読んだ人が思い出したときにだけ効く」防御であって、疲れているとき・急いでいるとき・自分ひとりで PR レビューがないときは素通りする。一人開発では特に、レビュアーが機能しないので、ドキュメントの拘束力はほぼゼロになる。

つまり真因はこう:

- ルールを **自然言語** で書いた(→ 実行時に評価されない)
- ルールを **自分の意志** に預けた(→ 疲労で崩れる)
- ルールが **push を止める仕組み** に接続されていなかった(→ 事故が本番に届く)

書いた瞬間にルールは「気持ち」であって「装置」ではなかった。

## 防止装置

ルールを機械が読める形に翻訳して、コミット時と push 後の二段で止めるようにした。個人リポにそのまま置ける最小構成を出す。

### 1. コミット時に止める(pre-commit)

`.githooks/pre-commit` に置く。シェルだけで完結させて依存を増やさない。

```bash
#!/usr/bin/env bash
set -e

# 1) TODO コメントの持ち込み禁止
if git diff --cached | grep -E '^\+.*(TODO|FIXME|XXX)' > /dev/null; then
  echo "❌ TODO/FIXME/XXX を含む変更はコミットできません"
  exit 1
fi

# 2) 素朴なシークレット検知(必要に応じて正規表現を足す)
if git diff --cached | grep -E '^\+.*(AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)' > /dev/null; then
  echo "❌ シークレットらしき文字列が含まれています"
  exit 1
fi

# 3) テスト
if [ -f package.json ] && grep -q '"test"' package.json; then
  pnpm test --silent
fi
```

有効化はリポジトリごとに一度だけ。

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
```

`core.hooksPath` を使うと `.git/hooks/` に手で置く運用と違い、フックが Git 管理下に入る。マシンを乗り換えても再現する。

### 2. push 後にも止める(GitHub Actions)

pre-commit は `--no-verify` で回避できる。人間(自分)は必ず抜け道を通るので、リモート側でもう一度検査する。

`.github/workflows/guard.yml`:

```yaml
name: guard

on:
  pull_request:
  push:
    branches: [main]

jobs:
  guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: TODO/FIXME を新規に増やしていないか
        run: |
          if git log -1 --format=%B | grep -qi 'allow-todo'; then
            echo "コミットメッセージで明示的に許可されています"
          else
            ! git diff origin/main...HEAD -- . ':(exclude).github/**' \
              | grep -E '^\+.*(TODO|FIXME|XXX)'
          fi

      - name: secret スキャン(gitleaks)
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: 'pnpm' }
      - run: pnpm install --frozen-lockfile
      - run: pnpm test
```

さらに `main` を Branch protection で「guard を必須」にしておくと、`git push origin main` を直接叩いてもマージが通らない。ここまでやって初めて、ルールが自分の意志から切り離される。

### 3. ルールとチェックを対応表にする

`CONTRIBUTING.md` は残していい。ただし各ルールの隣に「どの装置が検知するか」を書く。検知装置がない行は、その時点で守られないルールだと分かる。

```markdown
| ルール                       | 検知装置                          |
| ---------------------------- | --------------------------------- |
| テストを通してから push      | pre-commit / Actions `pnpm test`  |
| TODO を残さない              | pre-commit / Actions grep         |
| シークレットをコミットしない | pre-commit / Actions (gitleaks)   |
```

この表に「未検知」の行を発見したら、ルールを消すか、検知装置を足す。ドキュメントを増やす方向には進まない。

## 学び

- **文章で書かれたルールは、書いた本人が最初に破る**。特に一人開発ではレビュアーがいないので、ルールの拘束力はドキュメントに書いた瞬間の気合だけで支えられている。
- ルールを追加するときの正しい問いは「これをどう書くか」ではなく「これを **どうやって検知するか**」。検知手段が思いつかないルールは、守られないルールとして扱う。
- ローカルのフックだけでは足りない。自分は必ず `--no-verify` を使う日が来る。CI 側で同じ検査をもう一度回して、`main` を保護対象にする二段構えにして、初めてルールが装置になる。

同じ日にルールを破ったことがある人へ、届けば。
