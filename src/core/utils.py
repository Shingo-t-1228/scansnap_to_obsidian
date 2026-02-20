import re

def sanitize_filename(filename):
    """ファイル名に使用できない文字を置換し、適切なファイル名に調整する"""
    if not filename:
        return ""
    # OSで禁止されている、または不適切な文字を置換
    # 全角のコロンなども置換対象に含める
    invalid_chars = r'[\\/:*?"<>|：／＊？＂＜＞｜]'
    sanitized = re.sub(invalid_chars, '_', filename)
    # 改行やタブ、スペースをアンダースコアに置換
    sanitized = re.sub(r'[\r\n\t\s]', '_', sanitized)
    # 連続するアンダースコアを1つに統合
    sanitized = re.sub(r'_+', '_', sanitized)
    # 前後のアンダースコアや空白を削除
    sanitized = sanitized.strip('_').strip()
    return sanitized

def convert_japanese_era_to_western(date_str):
    """和暦を西暦に変換する。変換できない場合は元の文字列を返す"""
    if not date_str or date_str == "不明":
        return date_str
    
    eras = {
        "令和": 2018,
        "令": 2018,
        "R": 2018,
        "平成": 1988,
        "平": 1988,
        "H": 1988,
        "昭和": 1925,
        "昭": 1925,
        "S": 1925,
        "大正": 1911,
        "大": 1911,
        "T": 1911,
        "明治": 1867,
        "明": 1867,
        "M": 1867
    }
    
    # 元号+年 を抽出する正規表現
    pattern = r'(令和|平成|昭和|大正|明治|令|平|昭|大|明|[RHSMT])\s*([0-9０-９]+|元)\s*年?'
    match = re.search(pattern, date_str)
    
    if match:
        era_name = match.group(1)
        year_str = match.group(2)
        
        if year_str == "元":
            year = 1
        else:
            # 全角数字を半角に変換
            year_str = year_str.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
            year = int(year_str)
        
        western_year = eras[era_name] + year
        suffix = date_str[match.end():]
        suffix = suffix.replace('.', '/').replace('-', '/')
        new_date_str = date_str[:match.start()] + str(western_year) + "年" + suffix
        return new_date_str
        
    return date_str

def extract_yyyymmdd(date_str):
    """文字列からYYYYMMDD形式の日付を抽出する。見つからない場合はNoneを返す"""
    if not date_str:
        return None
    
    # まず和暦があれば西暦に変換
    date_str = convert_japanese_era_to_western(date_str)
    
    # YYYY/MM/DD, YYYY-MM-DD, YYYY年MM月DD日, YYYY.MM.DD などを探す
    patterns = [
        r'(\d{4})[/\-年./\s]*(\d{1,2})[/\-月./\s]*(\d{1,2})', 
        r'(\d{4})(\d{2})(\d{2})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, date_str)
        if match:
            y, m, d = match.groups()
            return f"{y}{int(m):02d}{int(d):02d}"
            
    # 年（YYYY）だけ見つかる場合
    year_match = re.search(r'(\d{4})年?', date_str)
    if year_match:
        return f"{year_match.group(1)}0000"
        
    return None
