#!/usr/bin/env python3
"""失敗テーマ(data/failure-themes.json)から Zenn 記事を Claude API で生成する。

承認動線はスマホ完結(GitHub アプリ):
  GH Action が記事(published: true)を生成 → PR を作成(assignee に通知) →
  スマホの GitHub アプリに push 通知 → PR を開いて確認 → Merge を押す →
  main に入り Zenn が数秒で自動公開。Close すれば非公開のまま。
  ※記事は published: true で生成するが、main に merge されるまで Zenn は公開しない
    (Zenn は連携ブランチ=main しか見ない)。つまり「マージ=承認=公開」。

note(拡散) / Substack(メール所有) の上流 = 検索・開発者コミュニティからの新規流入を担う。
読者は AI×個人開発の開発者なので技術用語を使ってよい(L2-L3)。

Environment:
  ANTHROPIC_API_KEY  — 必須(未設定ならスキップ)
  CLAUDE_MODEL       — 任意(default: claude-opus-4-7)
  ZENN_PER_RUN       — 任意(default: 1)
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).resolve().parent.parent
THEMES_PATH = BASE_DIR / "data" / "failure-themes.json"
ARTICLES_DIR = BASE_DIR / "articles"

SYSTEM_PROMPT = """あなたは個人開発者向けの技術記事ライター。媒体は Zenn。
読者は「AI に開発を任せて一人で自動の仕組みを作っている/作りたい開発者」。
ブランドの芯は『先に転んだ記録 — 失敗 → 真因 → 防止装置』。

# 書き方
- Zenn の技術記事。読者は開発者なので技術用語は使ってよい(GitHub Actions / cron / API / JSON 等)。
- 構成: 何が起きた → 真因(表面でなく構造) → 防止装置(コード/yml/設定の実例) → 学び。
- 防止装置には必ず1つ以上、コピペできる最小のコードか yml の例を入れる。
- 一般論の寄せ集めにしない。具体的な状況・再現条件・最初の判断を書く。
- 煽らない。最後は「同じ罠の前の人へ届けば」程度の静かな締め。

# 安全(厳守・一度ミスると取り返せない)
- 会社名・業界名・顧客名・同僚名・案件名を出さない。本業(HR コンサル: 人事・採用・労務)は転用しない。
- 内部の固有な仕組み名・リポジトリ名・実 Secret 名・個人の数値は出さない。一般化して書く。
- 架空の数字を作らない。一般論として書ける範囲に留める。

# 出力フォーマット(これだけを返す。前後に説明文を付けない)
---
title: "..."            # 検索されやすい具体的な1行
emoji: "X"              # 絵文字1つ
type: "tech"
topics: ["...", "..."]  # 3〜5個。英小文字 or 日本語タグ
published: true
---

## ...(本文。失敗 → 真因 → 防止装置 → 学び)
"""


def _now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _load_themes() -> dict:
    return json.loads(THEMES_PATH.read_text(encoding="utf-8"))


def _save_themes(data: dict) -> None:
    THEMES_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _build_prompt(theme: dict) -> str:
    topics = "、".join(theme.get("topics") or [])
    return f"""以下の失敗テーマで Zenn の技術記事を1本書いてください。

- テーマ: {theme.get('title_hint', '')}
- 章(分類): {theme.get('chapter', '')}
- 伝える学び(核): {theme.get('lesson', '')}
- 推奨トピックタグ(参考): {topics}

失敗 → 真因 → 防止装置(コード/yml の実例を最低1つ) → 学び の順で、
個人開発者が自分のリポにそのまま移植できる形で。published は true のまま出力する
(公開ゲートは GitHub の PR マージ。マージされるまで Zenn は公開しない)。
"""


def _call_claude(prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.getenv("CLAUDE_MODEL", "claude-opus-4-7")
    msg = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return "\n".join(
        b.text for b in msg.content if getattr(b, "type", "") == "text"
    ).strip()


_FM_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _title_and_slug(md: str, theme: dict) -> tuple[str, str]:
    title = theme.get("title_hint", "zenn-article")
    m = _FM_RE.match(md.strip())
    if m:
        for line in m.group(1).splitlines():
            if line.strip().startswith("title:"):
                title = line.split(":", 1)[1].strip().strip('"').strip("'") or title
                break
    # Zenn の slug 規約: a-z0-9-_ の 12〜50 字。日本語タイトルは消えるため id ベースで安定化。
    base = re.sub(r"[^a-z0-9-]+", "-", (theme.get("id", "z") + "-" + title).lower())
    slug = base.strip("-")[:50]
    if len(slug) < 12:
        slug = (slug + "-failure-note")[:50]
    return title, slug


def generate(n: int) -> int:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("[zenn] ANTHROPIC_API_KEY not set — skipping")
        return 0
    data = _load_themes()
    todo = [t for t in data.get("themes", []) if t.get("status") == "todo"]
    if not todo:
        print("[zenn] no todo themes — nothing to generate")
        return 0
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    made = 0
    for theme in todo[:n]:
        try:
            md = _call_claude(_build_prompt(theme))
        except Exception as e:  # noqa: BLE001
            print(f"[zenn] error for {theme.get('id')}: {e}", file=sys.stderr)
            continue
        # 記事は published: true で確定(公開ゲートは PR マージ)。false で返れば true に正す。
        md = re.sub(r"(?m)^published:\s*false\s*$", "published: true", md)
        title, slug = _title_and_slug(md, theme)
        path = ARTICLES_DIR / f"{slug}.md"
        path.write_text(md.strip() + "\n", encoding="utf-8")
        theme["status"] = "drafted"
        theme["drafted_at"] = _now_iso()
        theme["article"] = path.name
        made += 1
        print(f"[zenn] drafted {path.relative_to(BASE_DIR)} (title={title})")
    if made:
        _save_themes(data)
    return made


def main() -> int:
    try:
        generate(int(os.getenv("ZENN_PER_RUN") or "1"))
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[zenn] error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
