# zenn-content — 失敗ラボ Zenn 集客チャネル

個人開発 × AI の「**失敗 → 真因 → 防止装置**」を Zenn に自動下書きし、レビュー後に公開する集客チャネル。
note(拡散) / Substack(メール所有) の **上流＝検索・開発者コミュニティからの新規流入**を担う。

## なぜ Zenn か（フォロワー0 でも機能する）

- **git ベース公開**: `published: true` で push すると数秒で自動デプロイ。手動公開ボタンも API ハックも不要。
- **承認 → 公開フロー**: 生成は `published: false`（下書き）→ GitHub でレビュー → `true` にして push → 公開。
  （＝Cowork を待たずに「承認したら公開」が今日から成立する唯一の媒体）
- **発見される**: Zenn 内トレンド／トピック + Google SEO。フォロワー0 でも検索で読者が来る。
- 失敗インデックスのネタは Zenn 読者（AI×個人開発）のど真ん中。技術用語を使ってよい（note より楽）。

## 仕組み（スマホ承認で完結）

```
data/failure-themes.json (失敗テーマ)
        │  weekly GH Action
        ▼
scripts/generate_zenn_article.py (Claude API, published: true)
        ▼
   GH Action が「📗 公開承認 PR」を自動作成（あなたを assignee に）
        ▼  GitHub アプリに push 通知
   スマホで PR を開く → 記事を確認 → Merge をタップ
        ▼
   main に入り Zenn が数秒で自動公開 (zenn.dev) ／ Close で非公開
```

> 公開ゲートは **PR マージ**。記事は `published: true` で生成するが、main に
> マージされるまで Zenn は公開しない（Zenn は連携ブランチ=main しか見ない）。
> = **マージ = 承認 = 公開**。通知から公開まで GitHub アプリだけで完結する。

## セットアップ（一度だけ）

このリポは Zenn 連携用の独立リポ（canon から切り出し済み）。Zenn は**リポジトリ直下の `/articles/`** を読む。
`main` に内容を載せたうえで、一度だけ次を実施する：

1. **Zenn にリポ連携**: https://zenn.dev/dashboard/deploys →「リポジトリを連携する」→ `kikimi-02-cmd/zenn-content` / ブランチ `main`。
2. **Secret 追加**（Settings → Secrets and variables → Actions）: `ANTHROPIC_API_KEY`（必須）。
3. **PR 自動作成を許可**: Settings → Actions → General → Workflow permissions →「Allow GitHub Actions to create and approve pull requests」を ON。
4. 動作確認: Actions →「zenn-article-weekly」→ Run workflow → 「📗 公開承認」PR が立つ → スマホで Merge すれば公開。

## 日々の運用（週1・スマホで完結）

1. GitHub アプリに「📗 公開承認」PR の通知が届く。
2. PR を開き、**Files changed** で記事を QC（固有名／会社／顧客／Secret／個人数値が無いか）。
3. OK なら **Merge** をタップ → 数秒で zenn.dev に公開。修正は GitHub アプリ上で該当ファイルを編集してから Merge。
4. ダメなら **Close**（公開されない）。

## ローカル執筆（任意）

```bash
npm i
npx zenn preview   # http://localhost:8000
```

## 安全運用（厳守・一度ミスると取り返せない）

会社／業界／顧客／同僚／案件名・本業（HR コンサル）・内部の仕組み名・実 Secret 名・個人数値は出さない。架空数字 NG。
生成プロンプトに同ルールを埋め込み済みだが、**最終 QC は人間**（published を true にする前）。
