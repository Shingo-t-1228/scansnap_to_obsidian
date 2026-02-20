# ScanSnap-Obsidian 連携システム (AI要約 & 全文OCR抽出)

ScanSnapでスキャンされた書類 (PDF/JPEG) から、AI (Visionモデル) を使って高度な情報抽出、要約、および全文OCRを行い、ObsidianのMarkdownファイルとして取り込むためのツール群です。
本バージョンではモジュール化およびフォルダ構成の整理が行われ、拡張性とメンテナンス性が向上しています。

## 特徴
- **マルチフォーマット対応**: PDFに加え、JPEG/JPG画像も1書類として処理可能。
- **モジュール構成**: プロセス共通化により、将来的な他形式への対応も容易。
- **高度な解析**: AIが書類の文脈を理解し、タイトル、カテゴリ、タグ等を抽出。
- **全文OCR**: Vision LLMによる高精度な文字起こしと構造化出力。
- **スマートサンプリング**: ページ数の多い書類でも、冒頭と末尾を優先的に解析に利用（要約時）。

## システム構成・ディレクトリ構造

詳細は [system_architecture.md](file:///e:/00Obsidian/MyVault/scripts/scansnap_to_obsidian/doc/system_architecture.md) を参照してください。

```text
scripts/scansnap_to_obsidian/
├── src/                 # ソースコード
│   ├── scansnap_to_obsidian.py  # エントリポイント
│   ├── obsidian_ocr_enhancer.py # OCR追加処理
│   ├── processors/      # PDF/JPEG等の個別処理ロジック
│   └── core/            # 共通ユーティリティ
├── config/              # 設定ファイル (config.json)
├── data/                # 履歴データ (history.json)
├── doc/                 # ドキュメント (system_architecture.md)
└── ...
```

## 設定 (`config/config.json`)

PDFとJPEGで個別の入出力設定が可能です。

```json
{
    "common": {
        "lm_studio_base_url": "http://localhost:1234/v1",
        "llm_model": "...",
        "temp_directory": "temp_images"
    },
    "summarizer": {
        "pdf": {
            "input_directory": "...",
            "destination_directory": "...",
            "auto_copy": true,
            "auto_rename": true
        },
        "jpeg": {
            "input_directory": "...",
            "destination_directory": "...",
            "auto_copy": true,
            "auto_rename": true
        }
    }
}
```

## セットアップ

1. **依存関係のインストール**:
   [uv](https://github.com/astral-sh/uv) を使用している場合：
   ```powershell
   uv sync
   ```

2. **設定ファイルの作成**:
   `config/config.json.example` を `config/config.json` にコピーし、ご自身の環境（Obsidian VaultのパスやLM StudioのURL等）に合わせて編集してください。
   ```powershell
   copy config/config.json.example config/config.json
   ```

## 使い方

### 1. 書類の取り込みと要約
```powershell
uv run src/scansnap_to_obsidian.py
```

### 2. OCRテキストの追加・更新
```powershell
uv run src/obsidian_ocr_enhancer.py
```

## 注意事項
- **Visionモデル必須**: 画像を解析するため、マルチモーダル対応モデルが必要です（LM Studio等で `qwen/qwen3-vl-8b` などを推奨）。
- **APIコスト/負荷**: 全ページOCRを実行する場合、ページ数に応じた処理時間と負荷が発生します。

---

詳細な設計思想や構成図については `doc/system_architecture.md` をご確認ください。

## ライセンス

MIT License
