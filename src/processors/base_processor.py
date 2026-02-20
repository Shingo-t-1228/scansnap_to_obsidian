import os
import json
import logging
import base64
import re
import shutil
from datetime import datetime
from pathlib import Path
from openai import OpenAI
from core.utils import sanitize_filename, extract_yyyymmdd

class BaseProcessor:
    def __init__(self, config, format_config):
        self.config = config
        self.format_config = format_config
        self.client = OpenAI(base_url=config['common']['lm_studio_base_url'], api_key="lm-studio")
        self.temp_dir = Path(config['common'].get('temp_directory', 'temp_images'))
        if not self.temp_dir.exists():
            self.temp_dir.mkdir(parents=True)
        
        # 履歴ファイルのパス決定
        history_cfg = config['common'].get('history_file')
        script_dir = Path(__file__).parent.parent.parent
        if history_cfg:
            self.history_path = script_dir / history_cfg
        else:
            self.history_path = script_dir / "data" / "history.json"
            
        # 履歴は共有されるため、読み込みは呼び出し側か個別で行う必要があるが、
        # ここではインスタンスごとに読み込む（本当はシングルトンか共有管理が良い）
        self.history = self.load_history()

    def load_history(self):
        if self.history_path.exists():
            try:
                with open(self.history_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    structured_data = {}
                    for key, value in data.items():
                        if isinstance(value, str):
                            structured_data[key] = {"md_path": value, "ocr_completed": False}
                        else:
                            structured_data[key] = value
                    return structured_data
            except Exception as e:
                logging.warning(f"Failed to load history: {e}")
        return {}

    def save_history(self):
        try:
            # 最新の状態をファイルから読み直してマージするのが安全だが、
            # 現状のロジックを踏襲
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logging.error(f"Failed to save history: {e}")

    def should_reprocess(self, md_path):
        if not os.path.exists(md_path):
            return True
        if self.config.get('summarizer', {}).get('control', {}).get('force_reprocess'):
            return True
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = ""
                for _ in range(50):
                    line = f.readline()
                    if not line: break
                    content += line
                if re.search(r'^reprocess:\s*true', content, re.MULTILINE | re.IGNORECASE):
                    return True
        except Exception as e:
            logging.warning(f"Error checking reprocess flag in {md_path}: {e}")
        return False

    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def get_ai_summary(self, image_paths, custom_prompt=None):
        try:
            prompt = custom_prompt if custom_prompt else self.config.get('summarizer', {}).get('ai_analysis', {}).get('prompt')
            content = [{"type": "text", "text": prompt}]
            for img_path in image_paths:
                base64_image = self.encode_image(img_path)
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}"
                    }
                })
            response = self.client.chat.completions.create(
                model=self.config['common']['llm_model'],
                messages=[{"role": "user", "content": content}],
                temperature=0.7,
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"Error communicating with AI: {e}")
            return f"AI要約の取得に失敗しました: {e}"

    def get_output_paths(self, ai_data, source_path, relative_dir):
        """出力先のディレクトリとファイル名を決定する"""
        ai_title = ai_data.get('title', '').strip()
        sanitized_title = sanitize_filename(ai_title)
        if not sanitized_title:
            sanitized_title = Path(source_path).stem

        # カテゴリ決定
        category = ai_data.get('category', '99_未分類')
        if 'classification_rules' in self.config.get('summarizer', {}).get('ai_analysis', {}):
            valid_categories = [r['name'] for r in self.config['summarizer']['ai_analysis']['classification_rules']]
            for valid_cat in valid_categories:
                if valid_cat in category:
                    category = valid_cat
                    break
        sanitized_category = sanitize_filename(category)

        # サブディレクトリ決定
        ai_analysis_config = self.config.get('summarizer', {}).get('ai_analysis', {})
        if ai_analysis_config.get('enable_categorization', True):
            sub_dir = sanitized_category
        else:
            sub_dir = relative_dir

        # Markdown出力
        md_dest_base = self.config.get('summarizer', {}).get('markdown_output', {}).get('destination_directory')
        md_dir = os.path.join(md_dest_base, sub_dir)
        if not os.path.exists(md_dir):
            os.makedirs(md_dir)
        
        md_name = f"{sanitized_title}.md"
        md_path = os.path.join(md_dir, md_name)
        if os.path.exists(md_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            md_path = os.path.join(md_dir, f"{sanitized_title}_{timestamp}.md")

        # リネーム（コピー）後ファイル名の決定
        new_name = Path(source_path).name
        if self.format_config.get('auto_rename'):
            published_date = ai_data.get('published', '')
            date_prefix = extract_yyyymmdd(published_date)
            if not date_prefix or date_prefix.endswith("0000"):
                try:
                    mtime = os.path.getmtime(source_path)
                    date_prefix = datetime.fromtimestamp(mtime).strftime("%Y%m%d")
                except:
                    date_prefix = datetime.now().strftime("%Y%m%d")
            new_name = f"{date_prefix}_{sanitized_title}{Path(source_path).suffix}"

        # コピー先
        copy_path = None
        if self.format_config.get('auto_copy'):
            copy_dest_base = self.format_config.get('destination_directory')
            copy_dir = os.path.join(copy_dest_base, sub_dir)
            if not os.path.exists(copy_dir):
                os.makedirs(copy_dir)
            copy_path = os.path.join(copy_dir, new_name)
            if os.path.exists(copy_path):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                copy_path = os.path.join(copy_dir, f"{Path(new_name).stem}_{timestamp}{Path(new_name).suffix}")

        return md_path, copy_path, category

    def generate_markdown(self, output_path, ai_data, ai_response, category, source_file_name):
        # ファイル作成日時の取得
        try:
            # 原本から取得したいが、BaseProcessorでは source_path が分からない場合があるため
            # 呼び出し側で解決するか、引数に追加する。ここでは簡易化。
            created_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except:
            created_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # メタデータ
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        raw_tags = ai_data.get('tags', [])
        prefixed_tags = [f"auto/{tag}" if not tag.startswith("auto/") else tag for tag in raw_tags]
        tags_str = json.dumps(prefixed_tags, ensure_ascii=False)
        
        wiki_link = f"[[{source_file_name}]]"
        
        front_matter = (
            f"---\n"
            f"title: \"{ai_data.get('title', '')}\"\n"
            f"category: \"{category}\"\n"
            f"source: \"{wiki_link}\"\n"
            f"author: \"{ai_data.get('author', '')}\"\n"
            f"published: \"{ai_data.get('published', '')}\"\n"
            f"created: \"{created_date}\"\n"
            f"description: \"{ai_data.get('description', '')}\"\n"
            f"tags: {tags_str}\n"
            f"date: {now}\n"
            f"status: 'processed'\n"
            f"reprocess_ocr: false\n"
            f"---\n\n"
        )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(front_matter)
            f.write(f"# {ai_data.get('title', Path(output_path).stem)}\n\n")
            f.write(ai_data.get('summary', ai_response))
            
            # プレビューとして原本ファイルを埋め込み
            f.write(f"\n\n## プレビュー\n\n![[{source_file_name}]]")

    def process(self, file_path, relative_dir=""):
        raise NotImplementedError("Subclasses must implement process()")
