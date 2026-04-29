import shutil
from flask_frozen import Freezer
from app import app, fetch_bitable_records, ARTICLE_IMAGE_DIR

# Force relative URLs so it works in GitHub Pages sub-directories
app.config['FREEZER_RELATIVE_URLS'] = True

freezer = Freezer(app)

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
