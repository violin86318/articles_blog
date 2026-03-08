import os
import re
import requests
from flask import Flask, render_template, abort, jsonify
from config import Config
from cachetools import cached, TTLCache
import markdown
import markupsafe

app = Flask(__name__)
app.config.from_object(Config)

# 缓存飞书 tenant_access_token (存活1小时)
token_cache = TTLCache(maxsize=1, ttl=3600)

@cached(cache=token_cache)
def get_tenant_access_token():
    if app.config['FEISHU_APP_ID'] == "***":
        return "placeholder_token"
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    data = {
        "app_id": app.config['FEISHU_APP_ID'],
        "app_secret": app.config['FEISHU_APP_SECRET']
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        if result.get('code') != 0:
            print(f"Failed to get token: {result}")
            return None
        return result.get('tenant_access_token')
    except Exception as e:
        print(f"Error fetching token: {e}")
        return None

# 缓存多维表格数据 (存活5分钟)
data_cache = TTLCache(maxsize=1, ttl=300)


def estimate_reading_time(text):
    """Estimate reading time for Chinese text (~300 chars/min)."""
    if not text:
        return 1
    char_count = len(text)
    minutes = max(1, round(char_count / 300))
    return minutes


def extract_toc(content):
    """Extract headings from markdown content for table of contents."""
    if not content:
        return []
    toc = []
    # Match markdown headings: ## or ###
    heading_pattern = re.compile(r'^(#{2,3})\s+(.+)$', re.MULTILINE)
    for match in heading_pattern.finditer(content):
        level = len(match.group(1))
        title = match.group(2).strip()
        # Create a slug for anchor
        slug = re.sub(r'[^\w\u4e00-\u9fff]+', '-', title).strip('-').lower()
        toc.append({
            'level': level,
            'title': title,
            'slug': slug
        })
    return toc


@cached(cache=data_cache)
def fetch_bitable_records():
    token = get_tenant_access_token()
    if not token:
        return []
        
    if app.config['BASE_ID'] == "***":
        return [
            {
                'id': 'mock_1',
                'title': '深入理解苹果设计与中国红的结合',
                'quote': '设计不仅仅是外观，更是运作方式。将中国红融入苹果设计，是情感与理性的完美碰撞。',
                'review': '这篇文章深入浅出地讲解了设计心理学中的色彩运用，非常值得一读。结构清晰，论点有力。',
                'content': '在当代的网页设计中，苹果的极简设计语言（Apple Design）已经成为了一种标杆。它强调负空间、清晰的排版、毛玻璃效果和细腻的阴影。而中国红（#E60012），作为一种极具情感张力的颜色，如何在极简体系中发挥作用？\n\n## 红色的双重属性\n\n首先，我们要理解红色的双重属性：它既是警戒色，又是喜庆和热情的象征。在界面设计中，我们应当克制地使用红色。只在最重要的地方——比如行动号召按钮（CTA）、选中的高亮状态或是重要的金句中，适度地点缀。\n\n## 设计中的留白运用\n\n留白不是"浪费空间"，而是让内容呼吸的必要条件。苹果的设计之所以令人感到舒适，正是因为每个元素周围都有充足的负空间。当我们在大量留白中点缀极少量的中国红时，这种克制才能带来最大的视觉冲击力。\n\n## 层次与阴影\n\n通过微妙的阴影和透明度变化，我们可以在扁平化的界面中创造出空间层次感。这种方法不仅能吸引读者的眼球，更能传达出强烈的品牌个性，达到画龙点睛的效果。',
                'categories': ['设计', '科技']
            },
            {
                'id': 'mock_2',
                'title': '飞书多维表格与Flask后端的完美配合',
                'quote': 'API的设计决定了系统的扩展性，而数据的组织方式决定了阅读的体验。',
                'review': '实际项目中的前后端分离实践，提供了很好的参考价值。作者踩过的坑对新手极具借鉴意义。',
                'content': '多维表格作为一种轻量级的数据库，极大地降低了内容管理的门槛。在这个项目中，我们将飞书多维表格作为CMS服务器。\n\n## 架构设计思路\n\nFlask作为Python中最经典的轻量级Web框架之一，配合Requests和Cachetools库，可以在几十行代码内完成数据的请求和缓存。这种架构的好处在于：数据编辑即时生效，同时通过内存缓存避免了每次刷新都调用API。\n\n## 缓存策略\n\n保证了页面的快速响应速率，也避免了API被限流的问题。我们使用了TTLCache，设置5分钟的缓存时间，这意味着在飞书中编辑内容后，最多5分钟即可在网站上看到更新。\n\n## 前端渲染\n\n前端使用原生HTML/CSS，采用苹果设计风格。通过Jinja2模板引擎进行服务端渲染，结合Markdown解析库，实现了富文本内容的优雅展示。',
                'categories': ['科技']
            },
            {
                'id': 'mock_3',
                'title': '为什么我们需要慢下来阅读',
                'quote': '在信息洪流中，慢阅读不是效率的敌人，而是深度思考的盟友。',
                'review': '很有共鸣的一篇文章。作者对于快餐式阅读的反思值得每个人警醒。',
                'content': '我们生活在一个信息爆炸的时代。每天打开手机，数百条推送、短视频、碎片化文章向我们涌来。我们的注意力被切割成无数碎片，深度阅读似乎成了一种奢侈。\n\n## 碎片化阅读的代价\n\n研究显示，频繁切换注意力会导致认知负荷增加，记忆力下降。当我们习惯了15秒的短视频之后，阅读一篇长文似乎变成了一项挑战。这不是因为我们变笨了，而是因为我们的注意力系统被重新训练了。\n\n## 慢阅读的回归\n\n慢阅读不意味着低效，恰恰相反——当我们全身心投入一篇好文章时，我们获得的不仅是信息，还有思考的深度。一本好书值得反复咀嚼，一个好观点值得细细品味。\n\n## 如何培养深度阅读习惯\n\n首先，设定固定的阅读时间。其次，选择纸质书或长文，远离社交媒体的干扰。最重要的是，让阅读成为一种享受，而不是任务。',
                'categories': ['人文', '随笔']
            },
            {
                'id': 'mock_4',
                'title': 'AI时代的创意写作：工具还是替代？',
                'quote': 'AI不会取代作家，但会取代不愿思考的作家。',
                'review': '对AI辅助写作的思考很到位，既不盲目乐观也不悲观恐惧，是一种理性的中间态度。',
                'content': '自从ChatGPT横空出世以来，关于AI是否会取代人类创意工作的讨论就没有停止过。作为一个长期使用AI辅助写作的人，我有一些自己的思考。\n\n## AI的能力边界\n\nAI擅长的是模式识别和信息重组。它可以快速生成结构完整的文本，但它缺乏真正的"意图"和"体验"。一篇好的文章不仅需要正确的信息，更需要作者独特的视角和情感温度。\n\n## 人机协作的最佳实践\n\n最好的方式是把AI当作一个博学但缺乏个性的助手。让它帮你搜集资料、提供框架，但最终的判断、筛选和表达，仍然需要人来完成。\n\n## 未来展望\n\n在可预见的未来，最有价值的写作者将是那些既懂得利用AI提高效率，又保持独立思考能力的人。技术永远是工具，而不是目的。',
                'categories': ['科技', '人文']
            }
        ]
    
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app.config['BASE_ID']}/tables/{app.config['TABLE_ID']}/records"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }
    
    records = []
    page_token = None
    
    while True:
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code != 200:
                print(f"Failed to fetch records. Status code: {response.status_code}, error: {response.text}")
                break
            result = response.json()
            if result.get('code') != 0:
                print(f"Error from Feishu API: {result}")
                break
            data = result.get('data', {})
            items = data.get('items', [])
            records.extend(items)
            has_more = data.get('has_more', False)
            page_token = data.get('page_token')
            if not has_more or not page_token:
                break
        except Exception as e:
            print(f"Exception while fetching records: {e}")
            break
            
    formatted_records = []
    for item in records:
        fields = item.get('fields', {})
        
        def get_text_value(field_data):
            if isinstance(field_data, list):
                return ''.join([part.get('text', '') if isinstance(part, dict) else str(part) for part in field_data])
            elif field_data is None:
                return ''
            return str(field_data)
        
        def get_multi_select(field_data):
            """Parse multi-select field from Feishu."""
            if isinstance(field_data, list):
                return [str(item) for item in field_data]
            elif isinstance(field_data, str):
                return [field_data]
            return []
        
        formatted_record = {
            'id': item.get('record_id'),
            'title': get_text_value(fields.get('标题', '')),
            'quote': get_text_value(fields.get('金句输出', '')),
            'review': get_text_value(fields.get('黄叔点评', '')),
            'content': get_text_value(fields.get('概要内容输出', '')),
            'categories': get_multi_select(fields.get('分类', []))
        }
        if formatted_record['title']:
            formatted_records.append(formatted_record)
            
    return formatted_records[::-1]


@app.template_filter('markdown')
def markdown_filter(text):
    if not text:
        return ""
    html = markdown.markdown(text, extensions=['fenced_code', 'nl2br', 'toc'])
    return markupsafe.Markup(html)


@app.template_filter('markdown_with_ids')
def markdown_with_ids_filter(text):
    """Render markdown and add id attributes to headings for TOC linking."""
    if not text:
        return ""
    # Use toc extension to auto-generate heading IDs
    md = markdown.Markdown(extensions=['fenced_code', 'nl2br', 'toc'])
    html = md.convert(text)
    
    # Add IDs to headings manually if toc extension doesn't
    def add_heading_id(match):
        tag = match.group(1)
        content = match.group(2)
        slug = re.sub(r'[^\w\u4e00-\u9fff]+', '-', content).strip('-').lower()
        return f'<{tag} id="{slug}">{content}</{tag}>'
    
    html = re.sub(r'<(h[2-3])>([^<]+)</\1>', add_heading_id, html)
    return markupsafe.Markup(html)


@app.route('/')
def index():
    records = fetch_bitable_records()
    
    # Enrich records with computed fields
    all_categories = set()
    for record in records:
        content = record.get('content', '')
        # Preview: first 200 chars
        if len(content) > 200:
            record['preview'] = content[:200] + '...'
        else:
            record['preview'] = content
        # Reading time
        record['reading_time'] = estimate_reading_time(content)
        # Collect all categories
        for cat in record.get('categories', []):
            all_categories.add(cat)
    
    return render_template(
        'index.html',
        articles=records,
        total_count=len(records),
        all_categories=sorted(all_categories)
    )


@app.route('/post/<record_id>.html')
def detail(record_id):
    records = fetch_bitable_records()
    
    # Find article and its index
    article = None
    article_index = -1
    for i, r in enumerate(records):
        if r['id'] == record_id:
            article = r
            article_index = i
            break
    
    if not article:
        abort(404)
    
    # Enrich with computed fields
    content = article.get('content', '')
    article['reading_time'] = estimate_reading_time(content)
    article['toc'] = extract_toc(content)
    
    # Prev/Next articles
    prev_article = records[article_index - 1] if article_index > 0 else None
    next_article = records[article_index + 1] if article_index < len(records) - 1 else None
    
    return render_template(
        'detail.html',
        article=article,
        prev_article=prev_article,
        next_article=next_article
    )


if __name__ == '__main__':
    app.run(debug=True, port=5000)
