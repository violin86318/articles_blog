import shutil
from flask_frozen import Freezer
from pathlib import Path
from app import app, ARTICLE_IMAGE_DIR, fetch_bitable_records

# Force relative URLs so it works in GitHub Pages sub-directories
app.config['FREEZER_RELATIVE_URLS'] = True
app.config['FREEZER_SKIP_EXISTING'] = False
app.config['FREEZER_IGNORE_404_NOT_FOUND'] = True

# Avoid freezing proxy/helper endpoints without required params (like /media/image-proxy),
# which are no-argument routes but are only valid when runtime query is provided.
freezer = Freezer(app, with_no_argument_rules=False)


def sync_frozen_assets():
    # Even if static file discovery misses runtime generated images, copy them into build output.
    source_dir = ARTICLE_IMAGE_DIR
    root_path = Path(app.root_path)
    destination_dir = root_path / 'build' / 'static' / 'article-images'
    if source_dir.exists():
        destination_dir.parent.mkdir(parents=True, exist_ok=True)
        if destination_dir.exists():
            shutil.rmtree(destination_dir)
        shutil.copytree(source_dir, destination_dir)

@freezer.register_generator
def index():
    yield '/'


@freezer.register_generator
def detail():
    # Tell Freezer how to generate all dynamic article pages
    records = fetch_bitable_records()
    for record in records:
        yield {'record_id': record['id']}

if __name__ == '__main__':
    if ARTICLE_IMAGE_DIR.exists():
        shutil.rmtree(ARTICLE_IMAGE_DIR)
    ARTICLE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    freezer.freeze()
    sync_frozen_assets()
