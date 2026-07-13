#!/usr/bin/env python3
"""
AI 日报生成器
每天运行：收集 RSS → 去重 → 生成漂亮的 HTML 页面
"""
import feedparser
import urllib.request
import yaml
import json
import os
import sys
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).parent
SOURCES_FILE = ROOT / "sources.yaml"
CACHE_FILE = ROOT / "ai_daily.json"
OUTPUT_FILE = ROOT / "index.html"
ARCHIVE_DIR = ROOT / "archive"


def load_sources():
    """加载 RSS 源配置"""
    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config.get('sources', []), config.get('max_per_source', 3), config.get('max_total', 25)


def load_cache():
    """加载已收集的文章缓存（去重用）"""
    if CACHE_FILE.exists():
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


    # Archive to dated file
    today_file = datetime.now().strftime("%Y-%m-%d") + ".html"
    ARCHIVE_DIR.mkdir(exist_ok=True)
    with open(ARCHIVE_DIR / today_file, "w", encoding="utf-8") as f:
        f.write(html)
    
    # Purge archives older than 7 days
    cutoff = datetime.now() - timedelta(days=7)
    for old_f in ARCHIVE_DIR.glob("*.html"):
        try:
            fd = datetime.strptime(old_f.stem, "%Y-%m-%d")
            if fd < cutoff:
                old_f.unlink()
                print(f"   Purged: {old_f.name}")
        except ValueError:
            pass
    
def save_cache(cache):
    """保存缓存（只保留最近 7 天的）"""
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    cache = {k: v for k, v in cache.items() if v.get('collected_date', '') >= cutoff}
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def fetch_articles(sources, max_per_source, cache):
    """从所有源抓取文章"""
    articles = []
    today = datetime.now().strftime('%Y-%m-%d')
    
    for src in sources:
        name = src['name']
        url = src['url']
        region = src.get('region', '')
        
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    feed = feedparser.parse(resp.read())
            except Exception as _e:
                print(f"    ⚠️  连接超时，尝试直连...")
                feed = feedparser.parse(url)
            
            if feed.bozo and not feed.entries:
                print(f"  ⚠️  {name}: RSS 解析失败 ({feed.bozo_exception})")
                continue
            
            count = 0
            for entry in feed.entries[:max_per_source]:
                # 用链接作为唯一标识去重
                link = entry.get('link', '')
                if link in cache:
                    continue
                
                # 提取发布时间
                published = entry.get('published', entry.get('updated', ''))
                
                articles.append({
                    'title': entry.get('title', '无标题'),
                    'link': link,
                    'source_name': name,
                    'source_region': region,
                    'published': published,
                    'summary': extract_content(entry),
                    'collected_date': today,
                })
                
                # 标记为已收集
                cache[link] = {'collected_date': today, 'source': name}
                count += 1
            
            print(f"  ✅ {name}: {count} 条新文章")
            
        except Exception as e:
            print(f"  ❌ {name}: {e}")
    
    return articles


def extract_content(entry):
    """Extract the best available content from a feed entry"""
    # Try to get full content first
    content_list = entry.get('content', [])
    if content_list:
        full = content_list[0].get('value', '')
        if len(full) > 100:
            return clean_summary(full)
    
    # Fall back to summary/description
    summary = entry.get('summary', entry.get('description', ''))
    return clean_summary(summary)


def clean_summary(text):
    """清洗摘要：去 HTML 标签，截断"""
    import re
    # 去 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)
    # 去多余空白
    text = re.sub(r'\s+', ' ', text).strip()
    # 截断到 200 字
    if len(text) > 400:
        text = text[:400] + '...'
    return text



def auto_git_push():
    """Auto git add + commit + push to GitHub"""
    import subprocess
    try:
        subprocess.run(["git", "add", "index.html", "archive/"], cwd=str(ROOT),
                       capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m",
                       "📰 " + datetime.now().strftime("%m-%d") + " AI日报更新"],
                       cwd=str(ROOT), capture_output=True, timeout=10)
        result = subprocess.run(["git", "push"], cwd=str(ROOT),
                                capture_output=True, timeout=30)
        if result.returncode == 0:
            print("   📤 已推送到 GitHub")
        else:
            print(f"   ⚠️ 推送失败: {result.stderr.decode()[:100]}")
    except Exception as e:
        print(f"   ⚠️ Git推送跳过: {e}")


def format_date(date_str):
    """尝试格式化日期"""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        diff = now - dt
        
        if diff < timedelta(hours=1):
            return f"{int(diff.total_seconds() // 60)} 分钟前"
        elif diff < timedelta(hours=24):
            return f"{int(diff.total_seconds() // 3600)} 小时前"
        elif diff < timedelta(days=7):
            return f"{diff.days} 天前"
        else:
            return dt.strftime('%m-%d')
    except:
        return ''


def generate_html(articles, max_total):
    """生成漂亮的 HTML 日报"""
    articles = articles[:max_total]
    today = datetime.now().strftime('%Y年%m月%d日')
    
    # 按来源分组
    from collections import defaultdict
    by_region = defaultdict(list)
    for a in articles:
        by_region[a['source_region']].append(a)
    
    # 构建文章列表 HTML
    articles_html = ""
    for article in articles:
        region = article['source_region']
        source = article['source_name']
        title = article['title']
        link = article['link']
        summary = article['summary']
        published = format_date(article['published'])
        
        articles_html += f"""
            <article class="card">
                <div class="card-header">
                    <span class="region">{region}</span>
                    <span class="source">{source}</span>
                    <span class="time">{published}</span>
                </div>
                <h2 class="title">
                    <a href="{link}" target="_blank">{title}</a>
                </h2>
                <p class="summary">{summary}</p>
            </article>"""
    
    # 统计
    foreign = len(by_region.get('🇺🇸', []))
    domestic = len(by_region.get('🇨🇳', []))
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 AI 每日资讯 — {today}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", sans-serif;
            background: #f5f5f7;
            color: #1d1d1f;
            line-height: 1.6;
            padding: 20px;
        }}
        
        .container {{
            max-width: 800px;
            margin: 0 auto;
        }}
        
        .hero {{
            text-align: center;
            padding: 40px 20px 30px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 20px;
            color: white;
            margin-bottom: 30px;
            box-shadow: 0 10px 40px rgba(102, 126, 234, 0.3);
        }}
        
        .hero h1 {{
            font-size: 36px;
            margin-bottom: 8px;
        }}
        
        .hero .date {{
            font-size: 18px;
            opacity: 0.9;
        }}
        
        .hero .stats {{
            margin-top: 16px;
            font-size: 15px;
            opacity: 0.85;
        }}
        
        .hero .stats span {{
            margin: 0 12px;
        }}
        
        .card {{
            background: white;
            border-radius: 14px;
            padding: 20px 24px;
            margin-bottom: 16px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            transition: transform 0.15s, box-shadow 0.15s;
        }}
        
        .card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.1);
        }}
        
        .card-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 10px;
            font-size: 13px;
            color: #86868b;
        }}
        
        .region {{
            font-size: 16px;
        }}
        
        .source {{
            background: #f0f0f5;
            padding: 2px 10px;
            border-radius: 12px;
            font-weight: 500;
            color: #1d1d1f;
        }}
        
        .time {{
            margin-left: auto;
        }}
        
        .title {{
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 8px;
            line-height: 1.4;
        }}
        
        .title a {{
            color: #1d1d1f;
            text-decoration: none;
        }}
        
        .title a:hover {{
            color: #667eea;
        }}
        
        .summary {{
            font-size: 14px;
            color: #6e6e73;
            line-height: 1.6;
        }}
        
        .footer {{
            text-align: center;
            padding: 30px;
            color: #86868b;
            font-size: 13px;
        }}
        
        .empty {{
            text-align: center;
            padding: 60px 20px;
            color: #86868b;
        }}
        
        .empty .emoji {{
            font-size: 64px;
            margin-bottom: 16px;
        }}
        
        /* 响应式：手机 */
        @media (max-width: 600px) {{
            body {{ padding: 12px; }}
            .hero h1 {{ font-size: 28px; }}
            .card {{ padding: 16px; }}
            .title {{ font-size: 16px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="hero">
            <h1>🤖 AI 每日资讯</h1>
            <div class="date">{today}</div>
            <div class="stats">
                <span>📰 {len(articles)} 篇文章</span>
                <span>🇺🇸 {foreign} 篇</span>
                <span>🇨🇳 {domestic} 篇</span>
            </div>
        </div>
        
        <div class="articles">
            {articles_html if articles else '<div class="empty"><div class="emoji">☕️</div><p>今天还没有新文章，晚点再来看看~</p></div>'}
        </div>
        
        <div class="footer">
            🤖 由 AI 日报系统自动生成 · 每天更新 · <a href="archive/" style="color:#86868b">历史存档</a>
        </div>
    </div>
</body>
</html>"""
    
    return html


def main():
    print("=" * 50)
    print("🤖 AI 日报生成器")
    print("=" * 50)
    
    # 加载配置
    sources, max_per_source, max_total = load_sources()
    print(f"\n📡 已配置 {len(sources)} 个 RSS 源")
    
    # 加载缓存
    cache = load_cache()
    print(f"📦 缓存中已有 {len(cache)} 条记录")
    
    # 抓取文章
    print("\n🔍 开始收集...")
    articles = fetch_articles(sources, max_per_source, cache)
    
    # 排序：最新的在前
    articles.sort(key=lambda x: x.get('published', ''), reverse=True)
    
    # 生成 HTML
    print(f"\n📝 生成 HTML 日报...")
    html = generate_html(articles, max_total)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    
    # 保存缓存
    save_cache(cache)
    
    print(f"\n✅ 完成！")
    print(f"   新文章: {len(articles)} 条")
    print(f"   日报位置: {OUTPUT_FILE}")
    print(f"   浏览器打开: file:///{OUTPUT_FILE.as_posix()}")
    
    # Auto push to GitHub
    auto_git_push()


if __name__ == '__main__':
    main()
