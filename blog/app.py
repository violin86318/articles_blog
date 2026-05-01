import os
import html
import json
import re
import subprocess
import hashlib
from pathlib import Path
from urllib.parse import urlparse, urlsplit, parse_qs
import requests
from flask import Flask, Response, abort, render_template, request, url_for
from config import Config
from cachetools import cached, TTLCache
import markdown
import markupsafe
from markdown.extensions.toc import TocExtension, slugify_unicode
from urllib.parse import quote

app = Flask(__name__)
app.config.from_object(Config)

STATIC_ROOT = Path(app.root_path) / 'static'
ARTICLE_IMAGE_DIR = STATIC_ROOT / 'article-images'

# 缓存飞书 tenant_access_token (存活1小时)
token_cache = TTLCache(maxsize=1, ttl=3600)
IMAGE_PROXY_PATH = '/media/image-proxy'
IMAGE_PLACEHOLDER_PREFIX = 'data:image/svg+xml'

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
    _, toc = render_markdown_content(content)
    return toc


def flatten_toc_tokens(tokens):
    toc = []
    for token in tokens:
        toc.append({
            'level': token.get('level'),
            'title': html.unescape(token.get('name', '')),
            'slug': token.get('id', '')
        })
        toc.extend(flatten_toc_tokens(token.get('children', [])))
    return toc


def is_placeholder_image_url(url: str) -> bool:
    return url.strip().lower().startswith(IMAGE_PLACEHOLDER_PREFIX)


def build_proxy_image_url(url: str) -> str:
    return f"{IMAGE_PROXY_PATH}?url={quote(url, safe='')}"


def normalize_markdown_content(text: str) -> str:
    if not text:
        return ''

    def _replace_image(match):
        alt = (match.group('alt') or '').strip()
        src = (match.group('src') or '').strip()

        if not src:
            return ''

        if is_placeholder_image_url(src):
            label = html.escape(alt or '图片')
            return f"\n<div class=\"detail-image-missing\" role=\"img\" aria-label=\"{label}\">{label}：来源内容未完整抓取</div>\n"

        if src.startswith('/static/article-images/') or src.startswith('static/article-images/'):
            local_path = src.split('?')[0].lstrip('/')
            absolute_path = os.path.join(app.root_path, local_path)
            if not os.path.isfile(absolute_path):
                label = html.escape(alt or '图片')
                return f"\n<div class=\"detail-image-missing\" role=\"img\" aria-label=\"{label}\">{label}：本地图片缓存未找到</div>\n"

        if src.startswith('http://') or src.startswith('https://'):
            return f'![{alt}]({build_proxy_image_url(src)})'

        return match.group(0)

    return re.sub(r'!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\n]+)\)', _replace_image, text)


def render_markdown_content(text):
    normalized_text = normalize_markdown_content(text or '')
    md = markdown.Markdown(
        extensions=[
            'fenced_code',
            'nl2br',
            TocExtension(slugify=slugify_unicode)
        ]
    )
    rendered = md.convert(normalized_text)
    return rendered, flatten_toc_tokens(getattr(md, 'toc_tokens', []))


def canonical_image_url(url):
    return url.split('#', 1)[0].strip()


def infer_image_extension(url, content_type=''):
    content_type = (content_type or '').lower()
    if 'jpeg' in content_type or 'jpg' in content_type:
        return 'jpg'
    if 'png' in content_type:
        return 'png'
    if 'webp' in content_type:
        return 'webp'
    if 'gif' in content_type:
        return 'gif'

    query = parse_qs(urlsplit(url).query)
    wx_fmt = query.get('wx_fmt', [''])
    if wx_fmt and wx_fmt[0]:
        return wx_fmt[0].lower()

    path = urlparse(url).path.lower()
    match = re.search(r'\.(jpg|jpeg|png|webp|gif)$', path)
    if match:
        ext = match.group(1).lower()
        return 'jpg' if ext == 'jpeg' else ext
    return 'jpg'


def should_localize_image(url):
    if not url:
        return False
    if url.startswith('data:image/svg+xml'):
        return False
    if not url.startswith(('http://', 'https://')):
        return False
    host = urlparse(url).netloc.lower()
    return host.endswith('qpic.cn') or host.endswith('qq.com') or 'wx_fmt=' in url


def download_article_image(url, article_id, image_index):
    canonical_url = canonical_image_url(url)
    ARTICLE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(canonical_url.encode('utf-8')).hexdigest()[:10]
    file_stem = f'{article_id}-{image_index}-{digest}'

    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(canonical_url, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as exc:
        print(f'Error downloading article image {canonical_url}: {exc}')
        return url

    ext = infer_image_extension(canonical_url, response.headers.get('Content-Type', ''))
    file_name = f'{file_stem}.{ext}'
    file_path = ARTICLE_IMAGE_DIR / file_name
    if not file_path.exists():
        file_path.write_bytes(response.content)
    return url_for('static', filename=f'article-images/{file_name}')


def localize_markdown_images(text, article_id):
    if not text or not article_id:
        return text

    image_index = {'value': 0}
    localized = {}

    def replace(match):
        alt_text = match.group(1)
        raw_url = match.group(2).strip()
        if raw_url.startswith('data:image/svg+xml'):
            return ''
        if not should_localize_image(raw_url):
            return match.group(0)
        canonical_url = canonical_image_url(raw_url)
        if canonical_url not in localized:
            localized[canonical_url] = download_article_image(canonical_url, article_id, image_index['value'])
            image_index['value'] += 1
        return f'![{alt_text}]({localized[canonical_url]})'

    return MARKDOWN_IMAGE_PATTERN.sub(replace, text)


FAILED_GENERATION_MARKERS = (
    '抱歉，我无法直接访问',
    '无法直接访问该微信文章',
    '无法提取标题',
    '环境异常，完成验证后即可继续访问',
    '核心内容完全无法获取',
    '没有文章内容可供分析',
    '当前运行环境异常',
    '网页的核心内容完全无法获取',
    '请把目标微信文章的具体文本内容粘贴给我',
    '麻烦您将需要提炼处理的目标网页完整内容粘贴发送给我',
)
PUBLISH_BLOCK_MARKERS = (
    *FAILED_GENERATION_MARKERS,
    '未提供相关文章内容',
    '无法访问或提取网页内容',
)

LOW_SIGNAL_TITLES = {'无', '未命名', '无法提取标题'}
SOURCE_LINK_PATTERN = re.compile(r'\[([^\]]+)\]\((https?://[^)\s]+)\)')
PLAIN_URL_PATTERN = re.compile(r'https?://\S+')
MARKDOWN_IMAGE_PATTERN = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
CATEGORY_ORDER = [
    'AI 工具',
    '自动化工作流',
    '编程开发',
    '内容创作',
    '设计与视觉',
    '知识管理',
    '产品增长',
    '商业机会',
    '教程实操',
]


def is_failed_generation(text):
    return any(marker in text for marker in FAILED_GENERATION_MARKERS)


def first_useful_text(*values):
    for value in values:
        text = (value or '').strip()
        if text and not is_failed_generation(text):
            return text
    return ''


def clean_digest_text(text):
    text = first_useful_text(text)
    if not text:
        return ''
    text = re.sub(r'^以下是[^：]{0,60}：\s*', '', text)
    text = re.sub(r'[`*_]{1,3}', '', text)
    text = re.sub(r'^\s*[>#-]\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def clean_title(title):
    title = first_useful_text(title)
    if title in LOW_SIGNAL_TITLES:
        return ''
    return title


def contains_failure_text(*values):
    combined = '\n'.join((value or '').strip() for value in values if value)
    return any(marker in combined for marker in PUBLISH_BLOCK_MARKERS)


def is_publishable(record):
    status = (record.get('status') or '').strip().lower()
    publish_status = (record.get('publish_status') or '').strip().lower()
    title = record.get('title', '')
    summary = record.get('summary', '')
    content = record.get('content', '')
    review = record.get('review', '')

    if status or publish_status:
        return (
            status == 'ready' and
            publish_status in {'publish_ready', 'published'} and
            bool(title.strip()) and
            bool(summary.strip() or content.strip()) and
            not contains_failure_text(title, summary, content, review)
        )

    return (
        bool(title.strip()) and
        bool(summary.strip() or content.strip()) and
        not contains_failure_text(title, summary, content, review)
    )


def parse_source_link(value):
    text = first_useful_text(value)
    if not text:
        return '', ''

    markdown_link = SOURCE_LINK_PATTERN.search(text)
    if markdown_link:
        return markdown_link.group(1).strip(), markdown_link.group(2).strip()

    plain_url = PLAIN_URL_PATTERN.search(text)
    if plain_url:
        return '原文链接', plain_url.group(0).strip()

    return text, ''


def normalize_terms(value):
    if isinstance(value, list):
        terms = []
        for item in value:
            if isinstance(item, dict):
                item = item.get('text') or item.get('name') or item.get('value') or ''
            text = str(item).strip()
            if text and text not in terms:
                terms.append(text)
        return terms
    if isinstance(value, str):
        parts = re.split(r'[、,，/|]+', value)
        return [part.strip() for part in parts if part.strip()]
    return []


def sort_categories(categories):
    order = {name: index for index, name in enumerate(CATEGORY_ORDER)}
    return sorted(categories, key=lambda name: (order.get(name, len(order)), name))


def get_review_text(getter):
    return first_useful_text(
        getter('点评'),
        getter('黄叔点评'),
    )


@cached(cache=data_cache)
def fetch_bitable_records():
    if should_use_lark_cli():
        return fetch_bitable_records_with_lark_cli()

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
        if app.config.get('VIEW_ID'):
            params["view_id"] = app.config['VIEW_ID']
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
        record_id = item.get('record_id')
        
        def get_text_value(field_data):
            if isinstance(field_data, list):
                return ''.join([part.get('text', '') if isinstance(part, dict) else str(part) for part in field_data])
            elif field_data is None:
                return ''
            return str(field_data)
        
        def get_multi_select(field_data):
            """Parse multi-select field from Feishu."""
            return normalize_terms(field_data)

        categories = get_multi_select(fields.get('分类', []))
        tags = get_multi_select(fields.get('标签', []))
        summary = clean_digest_text(first_useful_text(
            get_text_value(fields.get('概要内容输出', '')),
            get_text_value(fields.get('概要内容提炼.输出结果', ''))
        ))
        localized_content = localize_markdown_images(
            first_useful_text(
                get_text_value(fields.get('全文', '')),
                summary
            ),
            record_id,
        )
        source_label, source_url = parse_source_link(get_text_value(fields.get('文章链接', '')))
        
        formatted_record = {
            'id': record_id,
            'title': clean_title(get_text_value(fields.get('标题', ''))),
            'quote': clean_digest_text(first_useful_text(
                get_text_value(fields.get('金句输出', '')),
                get_text_value(fields.get('金句提炼.输出结果', ''))
            )),
            'review': get_review_text(lambda name: get_text_value(fields.get(name, ''))),
            'summary': summary,
            'content': localized_content,
            'category': categories[0] if categories else '',
            'categories': categories,
            'tags': tags,
            'source_label': source_label,
            'source_url': source_url,
            'status': get_text_value(fields.get('处理状态', '')),
            'publish_status': get_text_value(fields.get('发布状态', '')),
            'error': get_text_value(fields.get('失败原因', '')),
            'author': get_text_value(fields.get('作者', '')),
            'published_at': get_text_value(fields.get('发布日期', '')),
        }
        if is_publishable(formatted_record):
            formatted_records.append(formatted_record)
            
    return formatted_records[::-1]


def should_use_lark_cli():
    if app.config.get('USE_LARK_CLI') == '1':
        return True
    return (
        not app.config.get('FEISHU_APP_ID')
        and bool(app.config.get('BASE_ID'))
        and bool(app.config.get('TABLE_ID'))
    )


def fetch_bitable_records_with_lark_cli():
    command = [
        'lark-cli',
        'base',
        '+record-list',
        '--base-token',
        app.config['BASE_ID'],
        '--table-id',
        app.config['TABLE_ID'],
        '--limit',
        '500'
    ]
    if app.config.get('VIEW_ID'):
        command.extend(['--view-id', app.config['VIEW_ID']])

    command_env = os.environ.copy()
    for proxy_key in (
        'HTTP_PROXY',
        'HTTPS_PROXY',
        'ALL_PROXY',
        'http_proxy',
        'https_proxy',
        'all_proxy',
    ):
        command_env.pop(proxy_key, None)
    command_env['NO_PROXY'] = 'open.feishu.cn,mcp.feishu.cn,accounts.feishu.cn,localhost,127.0.0.1,::1'
    command_env['no_proxy'] = command_env['NO_PROXY']

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=command_env,
            timeout=40
        )
        payload = json.loads(result.stdout)
    except Exception as e:
        print(f"Error fetching records with lark-cli: {e}")
        return []

    data = payload.get('data', {})
    fields = data.get('fields', [])
    rows = data.get('data', [])
    record_ids = data.get('record_id_list', [])

    def as_text(value):
        if isinstance(value, list):
            return ''.join(as_text(item) for item in value)
        if isinstance(value, dict):
            return value.get('text') or value.get('link') or json.dumps(value, ensure_ascii=False)
        if value is None:
            return ''
        return str(value)

    def as_terms(value):
        if isinstance(value, list):
            return normalize_terms([as_text(item) for item in value])
        text = as_text(value).strip()
        return [text] if text else []

    formatted_records = []
    for index, row in enumerate(rows):
        field_map = {
            fields[i]: row[i]
            for i in range(min(len(fields), len(row)))
        }
        record_id = record_ids[index] if index < len(record_ids) else f'lark_{index}'
        categories = as_terms(field_map.get('分类'))
        tags = as_terms(field_map.get('标签'))
        summary = clean_digest_text(first_useful_text(
            as_text(field_map.get('概要内容输出')),
            as_text(field_map.get('概要内容提炼.输出结果'))
        ))
        source_label, source_url = parse_source_link(as_text(field_map.get('文章链接')))
        content = localize_markdown_images(
            first_useful_text(
                as_text(field_map.get('全文')),
                summary
            ),
            record_id,
        )
        quote = clean_digest_text(first_useful_text(
            as_text(field_map.get('金句输出')),
            as_text(field_map.get('金句提炼.输出结果'))
        ))
        formatted_record = {
            'id': record_id,
            'title': clean_title(as_text(field_map.get('标题'))),
            'quote': quote,
            'review': get_review_text(lambda name: as_text(field_map.get(name))),
            'summary': summary,
            'content': content,
            'category': categories[0] if categories else '',
            'categories': categories,
            'tags': tags,
            'source_label': source_label,
            'source_url': source_url,
            'status': as_text(field_map.get('处理状态')),
            'publish_status': as_text(field_map.get('发布状态')),
            'error': as_text(field_map.get('失败原因')),
            'author': as_text(field_map.get('作者')),
            'published_at': as_text(field_map.get('发布日期')),
        }
        if is_publishable(formatted_record):
            formatted_records.append(formatted_record)

    return formatted_records


@app.template_filter('markdown')
def markdown_filter(text):
    if not text:
        return ""
    rendered, _ = render_markdown_content(text)
    return markupsafe.Markup(rendered)


@app.template_filter('markdown_with_ids')
def markdown_with_ids_filter(text):
    """Render markdown and add id attributes to headings for TOC linking."""
    if not text:
        return ""
    rendered, _ = render_markdown_content(text)
    return markupsafe.Markup(rendered)


@app.route('/media/image-proxy')
def image_proxy():
    image_url = (request.args.get('url') or '').strip()
    if not image_url:
        return Response('Missing image url', status=400, mimetype='text/plain')

    if not (image_url.startswith('http://') or image_url.startswith('https://')):
        return Response('Unsupported image url', status=400, mimetype='text/plain')

    try:
        response = requests.get(
            image_url,
            headers={
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://mp.weixin.qq.com/'
            },
            timeout=15,
            stream=True
        )
        response.raise_for_status()
        content = response.content
    except Exception as exc:
        print(f"Error proxying image {image_url}: {exc}")
        return Response('Failed to fetch image', status=502, mimetype='text/plain')

    content_type = (response.headers.get('Content-Type') or '').lower()
    if not content_type.startswith('image/'):
        return Response('Invalid image content', status=415, mimetype='text/plain')

    return Response(
        content,
        headers={
            'Content-Type': content_type or 'image/octet-stream',
            'Cache-Control': 'public, max-age=3600'
        }
    )


@app.route('/')
def index():
    records = fetch_bitable_records()
    
    # Enrich records with computed fields
    all_categories = set()
    tag_counts = {}
    search_index = []
    for record in records:
        content = record.get('content', '')
        summary = record.get('summary') or content
        # Preview: first 200 chars
        if len(summary) > 200:
            record['preview'] = summary[:200] + '...'
        else:
            record['preview'] = summary
        # Reading time
        record['reading_time'] = estimate_reading_time(content)
        record['url'] = url_for('detail', record_id=record['id'])
        # Collect all categories
        for cat in record.get('categories', []):
            all_categories.add(cat)
        for tag in record.get('tags', []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        search_index.append({
            'id': record.get('id', ''),
            'title': record.get('title', ''),
            'quote': record.get('quote', ''),
            'summary': record.get('summary', '')[:500],
            'preview': record.get('preview', ''),
            'categories': record.get('categories', []),
            'tags': record.get('tags', []),
            'url': record.get('url', '')
        })
    
    return render_template(
        'index.html',
        articles=records,
        total_count=len(records),
        all_categories=sort_categories(all_categories),
        all_tags=[tag for tag, _ in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))],
        search_index=search_index
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
