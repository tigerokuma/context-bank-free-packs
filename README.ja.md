# Context Bank Free Packs

[Read in English](README.md)

この repo は、Context Bank の approved free pack を扱う中央の public repository です。

## 概要

- contributor はこの repo に PR を出して free pack を投稿できます。
- GitHub Actions は marketplace の本番 secret を使わずに untrusted PR を validation します。
- `merge` が approval event です。
- `merge` 後、private marketplace app 側で `pnpm free-pack:sync` を実行すると、approved pack を取り込めます。

paid pack はこの repo の対象外です。MVP では `source.type = internal_repo` の free pack のみ対応します。

## Source Of Truth Docs

- [Hybrid Submission Strategy](docs/context-bank/00-overview/hybrid-submission-strategy.md)
- [Public Free-Pack Repo Layout](docs/context-bank/02-product/free-pack-repo-layout.md)
- [Free Pack PR Rules](docs/context-bank/06-execution/free-pack-pr-rules.md)
- [Trusted Source Repo Submission](docs/context-bank/06-execution/trusted-source-repo-submission.md)

## フロー図

```mermaid
flowchart LR
    A["作成者 / Contributor"] --> B["free-packs repo を fork"]
    B --> C["packs/{creator}/{slug} に 1 pack を追加または更新"]
    C --> D["central public repo に PR を作成"]

    D --> E["central repo の pull_request CI"]
    E --> E1["validate-free-pack.yml"]
    E1 --> E2["manifest.json / SKILL.md の整合性チェック"]
    E1 --> E3["path / free pricing / source.type のチェック"]
    E1 --> E4["安全性チェック: executable, symlink, hidden file, blocked pattern"]

    E --> F{"Maintainer review"}
    F -->|"approve + merge"| G["main に merge された commit = approval event"]
    F -->|"changes requested"| D

    G --> H["sync-marketplace.yml が normalized artifact を生成"]
    G --> I["private marketplace repo で pnpm free-pack:sync を手動実行"]
    I --> J["marketplace 用 normalized snapshot を保存"]
    J --> K["catalog / detail page に synced free pack を表示"]
```

## 投稿フロー

1. この repository を fork します。
2. `packs/<creator>/<slug>/` に対して、ちょうど 1 つの pack directory を追加または更新します。
3. `manifest.json` と `SKILL.md` を含めます。
4. Pull Request を作成します。
5. central repo 側の CI と maintainer review を待ちます。
6. 承認されれば maintainer が merge します。
7. merge 後、private app repo 側で `pnpm free-pack:sync` を実行すると marketplace に取り込めます。

## 既存 Pack の更新方法

以前に approved された pack を更新したい場合も、基本は同じ PR フローです。

1. 同じ pack path を使います: `packs/<creator>/<slug>/`
2. その directory 内の pack ファイルを更新します。
3. metadata が変わるなら `manifest.json` と `SKILL.md` も一緒に更新します。
4. PR を作成します。
5. CI と maintainer review を待ちます。
6. merge 後、次回の `pnpm free-pack:sync` で marketplace 側の approved version が更新されます。

重要ルール:

- 通常の更新では `creator` と `slug` の path を維持してください。
- 通常の update PR で pack directory を勝手に rename / move してはいけません。
- rename / move は maintainer 承認前提の migration PR が必要です。

## ディレクトリ構成

```text
.
├── .github/
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── workflows/
│       ├── submit-from-trusted-source-repo.yml
│       ├── sync-marketplace.yml
│       └── validate-free-pack.yml
├── catalogs/
│   ├── index.json
│   └── latest.json
├── docs/
│   └── context-bank/
├── packs/
│   └── <creator>/
│       └── <slug>/
│           ├── manifest.json
│           ├── SKILL.md
│           ├── knowledge.md
│           ├── data.json
│           ├── examples/
│           ├── prompts/
│           └── assets/
└── scripts/
    ├── build-sync-payload.py
    ├── create-submission-pr.py
    ├── free_pack_common.py
    └── validate-free-pack.py
```

## Contributor Guide

- 1 PR で変更できる pack directory は 1 つだけです。
- free pack のみ対象です。
- executable、symlink、hidden file、危険な prompt / shell content は不可です。
- `manifest.json` と `SKILL.md` は free pricing と category を一致させてください。

推奨ローカル validation:

```bash
printf '%s\n' \
  packs/<creator>/<slug>/manifest.json \
  packs/<creator>/<slug>/SKILL.md \
  > /tmp/changed-files.txt

python3 scripts/validate-free-pack.py \
  --repo-root . \
  --repo-url https://github.com/tigerokuma/context-bank-free-packs \
  --changed-files-file /tmp/changed-files.txt
```

## Maintainer Guide

1. PR が 1 つの pack directory だけを変更しているか確認します。
2. `manifest.json`、`SKILL.md`、変更ファイルを確認します。
3. `pull_request` validation workflow が通っていることを確認します。
4. 問題なければ merge します。squash merge でも構いません。
5. marketplace へ反映したいタイミングで、private marketplace repo 側で `pnpm free-pack:sync` を実行します。

## Advanced Maintainer Workflow

自分で管理する source repo から、自動で submission PR を作ることもできます。これは `.github/workflows/submit-from-trusted-source-repo.yml` を使う maintainer 向けの上級フローです。

ただし、これは primary contributor path ではありません。通常の contributor は `fork -> pack 更新 -> PR` のフローを使ってください。

## 現在の MVP 境界

- paid-pack logic は含みません。
- public PR validation では marketplace の本番 secret を使いません。
- この public repo から private app へ直接書き込みません。
- `external_repo` registration flow は未対応です。
- marketplace 反映は post-merge の manual sync 前提です。
