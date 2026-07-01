---
title: "GitHub Actions の PAT 権限不足に push して初めて気づいた話"
emoji: "🔑"
type: "tech"
topics: ["githubactions", "security", "個人開発", "ci", "github"]
published: true
---

## 何が起きた

個人開発で、別リポジトリへ生成物を push する Actions を組んでいた。ローカルで生成スクリプトは動く。`act` で workflow も通る。Secrets に PAT を入れ、いざ本番の `main` で走らせると、最後の `git push` だけが落ちた。

```
remote: Permission to user/other-repo.git denied to github-actions[bot].
fatal: unable to access ...: The requested URL returned error: 403
```

最初は「PAT の文字列をコピペミスったか」と思って入れ直した。変わらない。次に「リポジトリ名を間違えたか」と疑った。違う。最終的に、PAT に付けたスコープが `repo` ではなく `public_repo` だけで、push 先がプライベートだったことが原因だった。

ここまでに 30 分くらい溶かした。問題は時間ではなく、**「動いた気でいた状態が長く続いたこと」** だった。

## 真因 — 検証していた環境が、実行する環境ではなかった

表面的な原因は「スコープ不足」。だが本当の問題は別にある。

- ローカルでは、自分のユーザー権限で git 操作していた。PAT を使っていない。
- `act` でも、ローカルの認証情報がたまたま効いていた。
- Actions 上で初めて「PAT 経由の認証」が実際に行われる。
- つまり **権限のテストを、権限が試される場所でやっていなかった**。

PAT の権限不足は「コードのバグ」ではないので、コードを見ても見つからない。実行環境に出てはじめて顕在化する種類の失敗で、しかも「最後の push まで成功体験が積み上がる」ので、その分だけ落胆が大きい。

加えて、PAT を作るときに UI で「とりあえず repo 全部チェック」とせず、最小権限を意識して `public_repo` だけにしていたのも、今回の文脈ではむしろ事故の入り口になった。**最小権限は正しい。ただし「実環境で意図通り動くか」をセットで検証していなかった**ことが構造的な敗因。

## 防止装置

### 1. 「権限だけ」を検証する dry-run job を分ける

実処理の前に、認証と権限だけを確認する軽い job を置く。これがあれば、長い処理が走り切った最後に死ぬのを防げる。

```yaml
name: deploy

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  # 1. 権限の dry-run。失敗するならここで失敗する。
  check-permissions:
    runs-on: ubuntu-latest
    steps:
      - name: Verify PAT can access target repo
        env:
          GH_TOKEN: ${{ secrets.TARGET_REPO_PAT }}
          TARGET: owner/target-repo
        run: |
          set -e
          # 読み取り権限の確認
          gh api "repos/$TARGET" > /dev/null

          # 書き込み権限の確認(空コミットを ls-remote で擬似確認)
          # 実 push せず、push 可能性のあるエンドポイントを叩く
          code=$(curl -s -o /dev/null -w "%{http_code}" \
            -H "Authorization: token $GH_TOKEN" \
            -H "Accept: application/vnd.github+json" \
            "https://api.github.com/repos/$TARGET/collaborators/$(gh api user -q .login)/permission")

          if [ "$code" != "200" ]; then
            echo "PAT does not have sufficient permission on $TARGET (HTTP $code)"
            exit 1
          fi

          perm=$(curl -s \
            -H "Authorization: token $GH_TOKEN" \
            "https://api.github.com/repos/$TARGET/collaborators/$(gh api user -q .login)/permission" \
            | jq -r .permission)

          echo "Permission level: $perm"
          case "$perm" in
            admin|write|maintain) echo "OK" ;;
            *) echo "Need write or higher"; exit 1 ;;
          esac

  build-and-push:
    needs: check-permissions
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # ... 本処理
```

ポイントは **「本処理の前に落ちる」** こと。10 分の処理の最後に死ぬのと、開始 10 秒で死ぬのは、心理的にもデバッグ的にも全く違う。

### 2. PAT ではなく Fine-grained PAT、できれば GitHub App に寄せる

クラシック PAT は「ユーザー単位 × 雑なスコープ」で事故りやすい。Fine-grained PAT ならリポジトリ単位 × 権限単位で指定でき、足りないときの failure メッセージも具体的になる。

```
Repository access: Only select repositories → target-repo
Permissions:
  Contents:        Read and write   # push に必要
  Metadata:        Read-only        # 必須
```

「Contents: Read-only」のまま push して落ちる、を一度やると、UI 上の権限名と Actions の挙動が頭の中で繋がる。

### 3. Secrets 名に意図を埋める

`PAT` や `TOKEN` という名前にしない。**何のための、どこに対する、どの権限の Secret か** を名前で表現する。

```
✗ GH_TOKEN
✗ MY_PAT
○ TARGET_REPO_CONTENTS_RW_PAT
```

長いが、半年後の自分が「これ何だっけ」と Secret 設定画面を行き来する時間より遥かに短い。

### 4. PAT の有効期限を Issue に予約する

Fine-grained PAT は期限必須。期限切れも「push して初めて気づく」系の典型なので、PAT 作成時に同じ日付で Issue / リマインダーを切っておく。これだけで再発を一段防げる。

## 学び

- **権限は、権限が実際に使われる環境でしか検証できない。** ローカルで動いても何も保証していない。
- **最小権限は正しい。ただし dry-run とセットで初めて運用に乗る。** 片方だけだと、ただ事故りやすい構成になる。
- **失敗は本処理の最後ではなく、最初に出させる。** workflow を分け、軽い検証 job を先頭に置く。
- **Secret 名に意図を込める。** 命名は未来の自分への dry-run。

同じ罠の前の人へ、何か届けば。
